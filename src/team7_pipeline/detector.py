"""Run tsDetect CLI safely and normalize observed/missing smell values."""
from __future__ import annotations

import csv
import hashlib
import re
import shutil
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _file_key(value: str) -> str:
    return str(Path(value.strip().strip('"')).resolve()).replace("\\", "/").casefold()


def _find_file_column(fields: list[str]) -> str:
    keys = [x.lower().replace(" ", "").replace("_", "") for x in fields]
    for expected in ("pathtotestfile", "testfilepath", "testfile", "testclass"):
        if expected in keys:
            return fields[keys.index(expected)]
    if len(fields) >= 2:
        return fields[1]
    raise ValueError("Unknown tsDetect output header (test file column)")


def _classify(value: str) -> tuple[bool | None, str]:
    """Preserve missing values; legacy tsDetect v2.2 emits numeric counts and blanks."""
    v = value.strip().lower()
    if v in {"", "na", "n/a", "null", "nan"}:
        return None, "not_applicable"
    if v in {"true", "false"}:
        return v == "true", "measured"
    if re.fullmatch(r"\d+", v):
        return int(v) > 0, "measured"  # count=144 is positive, not invalid
    return None, "invalid"


def parse_tsdetect(raw: Path, tests: list[dict[str, Any]], checkout: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Produce one row for each (test file, smell), never substitute false for N/A."""
    absolute = {_file_key(str(checkout / str(t["test_file"]))): t for t in tests}
    relative = {str(t["test_file"]).replace("\\", "/").casefold(): t for t in tests}
    parsed: list[dict[str, Any]] = []
    unmatched: list[str] = []
    found_files: set[str] = set()
    not_applicable = 0
    invalid = 0
    with raw.open("r", encoding="utf-8-sig", errors="replace", newline="") as f:
        reader = csv.DictReader(f)
        fields = reader.fieldnames or []
        if not fields:
            raise ValueError("tsDetect output has no header")
        column = _find_file_column(fields)
        start = fields.index("NumberOfMethods") + 1 if "NumberOfMethods" in fields else 3
        smell_fields = fields[start:]
        if not smell_fields:
            raise ValueError("tsDetect returned no smell columns")
        for record in reader:
            source = (record.get(column) or "").strip()
            test = absolute.get(_file_key(source))
            if test is None:
                test = relative.get(source.replace("\\", "/").casefold())
            if test is None:
                unmatched.append(source)
                continue
            test_file = str(test["test_file"])
            if test_file in found_files:
                raise ValueError(f"Duplicate tsDetect row for: {test_file}")
            found_files.add(test_file)
            for smell_type in smell_fields:
                raw_value = (record.get(smell_type) or "").strip()
                present, state = _classify(raw_value)
                not_applicable += state == "not_applicable"
                invalid += state == "invalid"
                parsed.append({
                    "repository_id": test["repository_id"],
                    "snapshot_sha": test["snapshot_sha"],
                    "test_file": test_file,
                    "smell_type": smell_type.strip(),
                    "smell_present": present if present is not None else "",
                    "smell_status": state,
                    "smell_raw_value": raw_value,
                })
    missing = sorted(set(relative) - {x.casefold() for x in found_files})
    stats = {
        "matched_test_files": len(found_files),
        "unmatched_output_rows": len(unmatched),
        "unmatched_examples": unmatched[:5],
        "smell_rows": len(parsed),
        "measured_smell_values": len(parsed) - not_applicable - invalid,
        "not_applicable_smell_values": not_applicable,
        "invalid_smell_values": invalid,
        "missing_test_files": missing,
    }
    return parsed, stats


def run_tsdetect(
    jar: Path, checkout: Path, repository_id: str, tests: list[dict[str, Any]],
    result_dir: Path, timeout_seconds: int = 180,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not jar.is_file():
        raise FileNotFoundError(f"tsDetect JAR missing: {jar}")
    if not tests:
        return [], {"status": "no_tests", "jar_sha256": sha256(jar)}
    result_dir.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="team7-tsdetect-") as temp:
        work = Path(temp)
        local_jar = work / "TestSmellDetector.jar"
        shutil.copy2(jar, local_jar)
        input_csv = work / "input.csv"
        with input_csv.open("w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            # IMPORTANT: verified CLI release v2.2 requires NO HEADER despite web usage examples.
            for t in tests:
                w.writerow([
                    repository_id,
                    str(checkout / str(t["test_file"])),
                    str(checkout / str(t["production_file"])) if t["production_file"] else "",
                ])
        shutil.copy2(input_csv, result_dir / "tsdetect_input.csv")
        proc = subprocess.run(
            ["java", "-jar", str(local_jar), str(input_csv)],
            cwd=work, capture_output=True, text=True, errors="replace",
            timeout=timeout_seconds, check=False,
        )
        (result_dir / "tsdetect_stdout.log").write_text(proc.stdout, encoding="utf-8")
        (result_dir / "tsdetect_stderr.log").write_text(proc.stderr, encoding="utf-8")
        if proc.returncode:
            raise RuntimeError(f"tsDetect failed with exit code {proc.returncode}: {proc.stderr[:350]}")
        candidates = [p for p in work.rglob("*.csv") if p.resolve() != input_csv.resolve()]
        if len(candidates) != 1:
            raise RuntimeError(f"Expected one tsDetect CSV, found {len(candidates)}; inspect detector logs")
        raw = result_dir / "tsdetect_raw.csv"
        shutil.copy2(candidates[0], raw)
        smells, stats = parse_tsdetect(raw, tests, checkout)
        stats.update({"jar_sha256": sha256(jar), "java_exit_code": proc.returncode})
        stats["status"] = "partial" if (
            stats["unmatched_output_rows"] or stats["missing_test_files"] or stats["invalid_smell_values"]
        ) else ("complete_with_na" if stats["not_applicable_smell_values"] else "complete")
        if not smells:
            raise RuntimeError("No parseable test-smell observations; inspect raw output")
        return smells, stats
