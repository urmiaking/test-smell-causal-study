"""Machine-checked inter-role data contract and deterministic CSV comparison.

PIT attribution is an external experimental protocol, not produced by this CLI.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

from .pipeline import DATASETS, SMELL_FIELDS, TEST_FIELDS

KEY = ("repository_id", "snapshot_sha", "test_file")
PIT_FIELDS = KEY + ("mutation_score", "attribution_method", "measurement_status")
VALID_ATTRIBUTION = {"isolated_test_file", "verified_per_test_coverage"}
VALID_PIT_STATUS = {"measured", "not_measured", "failed", "not_attributable"}


def csv_rows(path: Path, required: tuple[str, ...] | list[str] = ()) -> list[dict[str, str]]:
    if not path.is_file():
        raise ValueError(f"Missing dataset: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fields = reader.fieldnames or []
        if not set(required).issubset(fields):
            raise ValueError(f"Missing required fields in {path.name}: {sorted(set(required)-set(fields))}")
        return list(reader)


def row_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return tuple(str(row[k]) for k in KEY)  # type: ignore[return-value]


def assert_unique(rows: list[dict[str, Any]], columns: tuple[str, ...], label: str) -> None:
    values = [tuple(str(r[col]) for col in columns) for r in rows]
    if len(set(values)) != len(values):
        raise ValueError(f"Duplicate {label} rows for key {columns}")


def validate(output: Path, pit_csv: Path | None = None, export: Path | None = None) -> dict[str, Any]:
    tests = csv_rows(output / "tests.csv", TEST_FIELDS)
    smells = csv_rows(output / "smells.csv", SMELL_FIELDS)
    outcomes = csv_rows(output / "outcomes.csv", list(KEY) + ["followup_sha", "change_commits", "followup_observed"])
    analysis = csv_rows(output / "analysis_ready.csv", list(KEY) + ["detector_status"])
    statuses = csv_rows(output / "repository_status.csv", ["repository_id", "status"])
    assert_unique(tests, KEY, "tests")
    assert_unique(outcomes, KEY, "outcomes")
    assert_unique(analysis, KEY, "analysis")
    assert_unique(statuses, ("repository_id",), "repository_status")
    assert_unique(smells, KEY + ("smell_type",), "smells")

    test_keys = {row_key(r) for r in tests}
    outcome_keys = {row_key(r) for r in outcomes}
    analysis_keys = {row_key(r) for r in analysis}
    if test_keys != outcome_keys or test_keys != analysis_keys:
        raise ValueError("Test/outcome/analysis keys differ; join is not lossless")
    if not all(row_key(r) in test_keys for r in smells):
        raise ValueError("Orphan smell observations referencing unknown baseline test")
    for row in smells:
        st = row["smell_status"]
        value = row["smell_present"].lower()
        if st == "measured" and value not in {"true", "false"}:
            raise ValueError("Measured smell must explicitly have true or false")
        if st != "measured" and value:
            raise ValueError("Unmeasured smell must NOT contain a boolean result")
    for row in outcomes:
        if not row["followup_sha"]:
            raise ValueError("Outcome missing follow-up commit SHA")
        if int(row["change_commits"]) < 0:
            raise ValueError("Negative file change count")
        if row["followup_observed"].lower() == "false" and row["change_commits"] != "0":
            raise ValueError("Nonzero follow-up change for an unobserved follow-up")
    measured_by_key = {row_key(r) for r in smells if r["smell_status"] == "measured"}
    for row in tests:
        if row["detector_status"] == "measured" and row_key(row) not in measured_by_key:
            raise ValueError("Test claimed detector success without any measured smell value")
    for row in analysis:
        if row_key(row) not in test_keys:
            raise ValueError("Analysis row not in baseline tests")
    pit_summary: dict[str, Any] | None = None
    if pit_csv is not None:
        pit_rows = csv_rows(pit_csv, list(PIT_FIELDS))
        assert_unique(pit_rows, KEY, "PIT")
        pit_map: dict[tuple[str, str, str], dict[str, str]] = {}
        for r in pit_rows:
            k = row_key(r)
            if k not in test_keys:
                raise ValueError("PIT record cannot join to immutable baseline test key")
            if r["measurement_status"] not in VALID_PIT_STATUS:
                raise ValueError("Unknown PIT measurement status")
            if r["measurement_status"] == "measured":
                if r["attribution_method"] not in VALID_ATTRIBUTION:
                    raise ValueError("PIT measurement lacks approved test-level attribution method")
                try:
                    score = float(r["mutation_score"])
                except ValueError as exc:
                    raise ValueError("Measured PIT score is not numeric") from exc
                if not math.isfinite(score) or not 0 <= score <= 1:
                    raise ValueError("PIT mutation score must be finite ratio [0, 1]")
            elif r["mutation_score"].strip():
                raise ValueError("Unmeasured PIT observation must have empty mutation score")
            pit_map[k] = r
        pit_summary = {"rows": len(pit_rows),
                       "measured": sum(r["measurement_status"] == "measured" for r in pit_rows),
                       "not_supplied": len(test_keys) - len(pit_rows)}
        if export:
            if export.exists():
                raise FileExistsError("Refusing to overwrite previously exported join")
            export.parent.mkdir(parents=True, exist_ok=True)
            with export.open("w", encoding="utf-8", newline="") as f:
                fields = list(analysis[0].keys()) if analysis else list(TEST_FIELDS)
                fields += ["mutation_score", "attribution_method", "measurement_status"]
                w = csv.DictWriter(f, fieldnames=fields)
                w.writeheader()
                for row in analysis:
                    pit = pit_map.get(row_key(row))
                    w.writerow({**row,
                                "mutation_score": pit["mutation_score"] if pit else "",
                                "attribution_method": pit["attribution_method"] if pit else "",
                                "measurement_status": pit["measurement_status"] if pit else "not_measured"})
    elif export is not None:
        raise ValueError("--export requires --pit")

    return {
        "valid": True, "baseline_tests": len(tests),
        "observed_smell_rows": len(smells),
        "measured_smell_rows": sum(r["smell_status"] == "measured" for r in smells),
        "test_files_with_measured_smells": len(measured_by_key),
        "outcomes": len(outcomes), "repositories": len(statuses),
        "repository_statuses": dict(Counter(r["status"] for r in statuses)),
        "pit": pit_summary, "export": str(export) if export else None,
        "limitations": "This validates syntax and joins, NOT causal identification, scientific sampling, PIT correctness or tsDetect accuracy."
    }


def compare(left: Path, right: Path) -> dict[str, Any]:
    """Compare all semantic CSV contents, ignoring run times, absolute paths and tool logs."""
    files: dict[str, Any] = {}
    mismatch = False
    for filename, (_, fields) in DATASETS.items():
        a = csv_rows(left / filename, fields)
        b = csv_rows(right / filename, fields)
        # Sort rows; timestamps in commit_events are source commit dates, not run timestamps.
        normalize = lambda rows: sorted(json.dumps(row, sort_keys=True, ensure_ascii=False)
                                        for row in rows)
        la, lb = normalize(a), normalize(b)
        same = la == lb
        mismatch |= not same
        files[filename] = {
            "equal": same, "left_rows": len(a), "right_rows": len(b),
            "left_sha256": hashlib.sha256(("\n".join(la)).encode("utf-8")).hexdigest(),
            "right_sha256": hashlib.sha256(("\n".join(lb)).encode("utf-8")).hexdigest(),
        }
    return {"equal": not mismatch, "files": files,
            "note": "Semantic deterministic CSV equivalence; independent-machine replication requires running on another machine."}
