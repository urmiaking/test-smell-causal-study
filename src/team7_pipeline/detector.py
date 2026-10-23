"""Run approved tsDetect CLI JAR against a pinned snapshot and normalize booleans."""
from __future__ import annotations

import csv
import hashlib
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


def parse_tsdetect(raw: Path, tests: list[dict[str, Any]], checkout: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Parse all boolean smell columns, preserving BOTH positives and negatives."""
    absolute = {_file_key(str(checkout / str(t["test_file"]))): t for t in tests}
    relative = {str(t["test_file"]).replace("\\", "/").casefold(): t for t in tests}
    parsed: list[dict[str, Any]] = []
    unmatched: list[str] = []
    found_files = set()
    with raw.open("r", encoding="utf-8-sig", errors="replace", newline="") as f:
        reader = csv.DictReader(f)
        fields = reader.fieldnames or []
        column = _find_file_column(fields)
        if not fields:
            raise ValueError("tsDetect output has no header")
        for record in reader:
            source = (record.get(column) or "").strip()
            test = absolute.get(_file_key(source))
            if test is None:
                test = relative.get(source.replace("\\", "/").casefold())
            if test is None:
                unmatched.append(source)
                continue
            found_files.add(str(test["test_file"]))
            for field in fields:
                if field == column:
                    continue
                val = (record.get(field) or "").strip().lower()
                if val not in {"true", "false"}:
                    continue
                parsed.append({
                    "repository_id": test["repository_id"],
                    "snapshot_sha": test["snapshot_sha"],
                    "test_file": test["test_file"],
                    "smell_type": field.strip(),
                    "smell_present": val == "true",
                })
    stats = {
        "matched_test_files": len(found_files),
        "unmatched_output_rows": len(unmatched),
        "unmatched_examples": unmatched[:5],
        "smell_observations": len(parsed),
        "missing_test_files": sorted(set(relative) - {s.casefold() for s in found_files}),
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
        shutil.copy2(jar, local_jar)  # output is documented as beside the JAR
        input_csv = work / "input.csv"
        with input_csv.open("w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["appName", "pathToTestFile", "pathToProductionFile"])
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
            raise RuntimeError(f"Expected one tsDetect CSV, found {len(candidates)}; see detector logs")
        raw = result_dir / "tsdetect_raw.csv"
        shutil.copy2(candidates[0], raw)
        smells, stats = parse_tsdetect(raw, tests, checkout)
        stats.update({"status": "complete", "jar_sha256": sha256(jar), "java_exit_code": proc.returncode})
        if stats["unmatched_output_rows"] or stats["missing_test_files"]:
            stats["status"] = "partial"
        if not smells:
            raise RuntimeError("No parseable boolean smell observations; inspect raw output")
        return smells, stats
