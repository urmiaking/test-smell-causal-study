"""Fault-isolated tsDetect runner.

Legacy tsDetect may throw on one Java file and abort the entire CSV batch.
Bisect failed batches, retain their logs, and mark unmeasured test files rather
than fabricating negative smell labels or discarding the repository.
"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from .detector import run_tsdetect as run_single_batch, sha256


FAILURE_FIELDS = ["test_file", "attempt", "error"]


def run_tsdetect(
    jar: Path, checkout: Path, repository_id: str, tests: list[dict[str, Any]],
    result_dir: Path, timeout_seconds: int = 180, batch_size: int = 25,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not jar.is_file():
        raise FileNotFoundError(f"tsDetect JAR missing: {jar}")
    if batch_size < 1:
        raise ValueError("batch_size must be at least one")
    result_dir.mkdir(parents=True, exist_ok=True)
    if not tests:
        return [], {"status": "no_tests", "jar_sha256": sha256(jar), "failed_test_files": []}

    # Preserve one complete input manifest in addition to per-attempt raw inputs.
    with (result_dir / "tsdetect_input.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        for row in tests:
            writer.writerow([
                repository_id,
                str(checkout / str(row["test_file"])),
                str(checkout / str(row["production_file"])) if row["production_file"] else "",
            ])

    successes: list[dict[str, Any]] = []
    success_files: set[str] = set()
    failed_files: set[str] = set()
    failures: list[dict[str, Any]] = []
    batch_paths: list[Path] = []
    unmatched_rows = 0
    invalid = 0
    not_applicable = 0
    attempt_id = 0

    def execute(chunk: list[dict[str, Any]]) -> None:
        nonlocal attempt_id, unmatched_rows, invalid, not_applicable
        attempt_id += 1
        attempt_name = f"attempt-{attempt_id:04d}"
        attempt_dir = result_dir / "batches" / attempt_name
        try:
            records, info = run_single_batch(
                jar, checkout, repository_id, chunk, attempt_dir, timeout_seconds,
            )
            if not records:
                raise RuntimeError("No smell observations produced")
            batch_paths.append(attempt_dir / "tsdetect_raw.csv")
            unmatched_rows += info["unmatched_output_rows"]
            invalid += info["invalid_smell_values"]
            not_applicable += info["not_applicable_smell_values"]
            successes.extend(records)
            discovered = {str(r["test_file"]) for r in records}
            success_files.update(discovered)
            # A returned batch may contain fewer test files than requested.
            missing = [r for r in chunk if str(r["test_file"]) not in discovered]
            for missing_row in missing:
                failed_files.add(str(missing_row["test_file"]))
                failures.append({
                    "test_file": missing_row["test_file"],
                    "attempt": attempt_name,
                    "error": "No usable result row returned by tsDetect",
                })
        except Exception as exc:
            if len(chunk) > 1:
                pivot = len(chunk) // 2
                execute(chunk[:pivot])
                execute(chunk[pivot:])
            else:
                name = str(chunk[0]["test_file"])
                failed_files.add(name)
                failures.append({
                    "test_file": name,
                    "attempt": attempt_name,
                    "error": str(exc)[:500],
                })

    for start in range(0, len(tests), batch_size):
        execute(tests[start:start + batch_size])

    # Merge raw, successful output CSVs while preserving their original field names.
    # Failed attempts remain separately inspectable under raw/.../batches/.
    if batch_paths:
        combined = result_dir / "tsdetect_raw.csv"
        with combined.open("w", encoding="utf-8", newline="") as target:
            writer = csv.writer(target)
            header = None
            for path in batch_paths:
                with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as source:
                    reader = csv.reader(source)
                    actual_header = next(reader, None)
                    if actual_header is None:
                        continue
                    if header is None:
                        header = actual_header
                        writer.writerow(header)
                    elif actual_header != header:
                        raise ValueError("tsDetect CSV schema changed between batches")
                    writer.writerows(reader)

    with (result_dir / "tsdetect_file_failures.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FAILURE_FIELDS)
        writer.writeheader()
        writer.writerows(failures)

    measured = sum(s["smell_status"] == "measured" for s in successes)
    stats = {
        "jar_sha256": sha256(jar),
        "status": "complete",
        "test_files_requested": len(tests),
        "test_files_with_results": len(success_files),
        "failed_test_files": sorted(failed_files),
        "failure_count": len(failures),
        "number_of_attempts": attempt_id,
        "smell_rows": len(successes),
        "measured_smell_values": measured,
        "not_applicable_smell_values": not_applicable,
        "invalid_smell_values": invalid,
        "unmatched_output_rows": unmatched_rows,
        "raw_batch_count": len(batch_paths),
    }
    if not successes:
        stats["status"] = "failed"
    elif failures or unmatched_rows or invalid:
        stats["status"] = "partial"
    elif not_applicable:
        stats["status"] = "complete_with_na"
    return successes, stats
