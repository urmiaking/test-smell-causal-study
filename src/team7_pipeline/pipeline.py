"""End-to-end, reproducible developer-side collection for the Team 7 pilot."""
from __future__ import annotations

import csv
import json
import platform
import re
import subprocess
import sys
import traceback
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path
from typing import Any

from .detector_batch import run_tsdetect
from .discovery import discover
from .gitutils import acquire_repository, commit_sha, ensure_ancestor, snapshot_checkout
from .miner import mine_history

TEST_FIELDS = ["repository_id", "snapshot_sha", "test_file", "production_file", "test_framework", "test_loc", "assert_count", "detector_status"]
SMELL_FIELDS = ["repository_id", "snapshot_sha", "test_file", "smell_type", "smell_present", "smell_status", "smell_raw_value"]
EVENT_FIELDS = ["repository_id", "snapshot_sha", "followup_sha", "test_file", "commit_sha", "commit_date", "author_name", "potential_bugfix_message"]
OUTCOME_FIELDS = ["repository_id", "snapshot_sha", "followup_sha", "test_file", "followup_test_file", "change_commits", "potential_bugfix_commits", "followup_commits_all_repo", "followup_observed"]
ANALYSIS_FIELDS = TEST_FIELDS + ["followup_sha", "followup_test_file", "change_commits", "potential_bugfix_commits", "followup_commits_all_repo", "followup_observed"]
STATUS_FIELDS = ["repository_id", "status", "snapshot_sha", "followup_sha", "test_count", "smell_rows", "error"]


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_csv(path: Path, fields: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def resolve(value: str, config_dir: Path) -> Path:
    candidate = Path(value).expanduser()
    return (candidate if candidate.is_absolute() else config_dir / candidate).resolve()


def run(config_path: Path, skip_detector: bool = False) -> dict[str, Any]:
    config_path = config_path.resolve()
    config = json.loads(config_path.read_text(encoding="utf-8-sig"))
    base = config_path.parent
    run_id = str(config["run_id"])
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,79}", run_id):
        raise ValueError("run_id must consist of 1..80 safe filename characters")
    output = resolve(config["output_dir"], base)
    if (output / "manifest.json").exists():
        raise FileExistsError(f"Run already completed: {output}. Use a NEW run_id / output_dir to preserve raw evidence.")
    cache = resolve(config.get("cache_dir", "../data/repos"), base)
    raw_jar = config.get("detector_jar")
    jar = resolve(raw_jar, base) if raw_jar else None
    if not skip_detector and (jar is None or not jar.is_file()):
        raise FileNotFoundError(f"Provide a valid detector_jar path or explicitly use --skip-detector. Found: {jar}")
    timeout = int(config.get("detector_timeout_seconds", 180))
    if timeout <= 0:
        raise ValueError("detector_timeout_seconds must be > 0")
    repositories = config.get("repositories") or []
    if not repositories:
        raise ValueError("At least one repository must be configured.")
    ids = [r["id"] for r in repositories]
    if len(set(ids)) != len(ids) or any(not re.fullmatch(r"[A-Za-z0-9_-]+", id_) for id_ in ids):
        raise ValueError("Repository ids must be unique and contain only letters, digits, _ or -")

    output.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, Any] = {
        "run_id": run_id, "started_utc": now(), "config_file": str(config_path),
        "python": sys.version, "platform": platform.platform(),
        "pydriller": version("PyDriller"),
        "git": subprocess.run(["git", "--version"], text=True, capture_output=True).stdout.strip(),
        "skip_detector": skip_detector, "repositories": [],
        "cpu_count": __import__("os").cpu_count(),
        "pip_freeze": subprocess.run([sys.executable, "-m", "pip", "freeze"], capture_output=True, text=True, timeout=45).stdout.splitlines(),
        "pipeline_git_sha": subprocess.run(["git", "-C", str(Path(__file__).resolve().parents[2]), "rev-parse", "HEAD"], capture_output=True, text=True, timeout=20).stdout.strip(),
        "pipeline_git_dirty": bool(subprocess.run(["git", "-C", str(Path(__file__).resolve().parents[2]), "status", "--porcelain"], capture_output=True, text=True, timeout=20).stdout.strip()),
    }
    rows_tests: list[dict[str, Any]] = []
    rows_smells: list[dict[str, Any]] = []
    rows_events: list[dict[str, Any]] = []
    rows_outcomes: list[dict[str, Any]] = []
    statuses: list[dict[str, Any]] = []

    for entry in repositories:
        repository_id = entry["id"]
        state: dict[str, Any] = {
            "repository_id": repository_id, "status": "failed", "snapshot_sha": "",
            "followup_sha": "", "test_count": 0, "smell_rows": 0, "error": "",
        }
        repo_info: dict[str, Any] = {"repository_id": repository_id, "started_utc": now()}
        try:
            configured_source = entry["source"]
            source = configured_source if configured_source.startswith("https://") else str(resolve(configured_source, base))
            repo = acquire_repository(source, cache, repository_id)
            snapshot = commit_sha(repo, entry.get("snapshot_ref", "HEAD"))
            followup = commit_sha(repo, entry.get("followup_ref", "HEAD"))
            ensure_ancestor(repo, snapshot, followup)
            state["snapshot_sha"] = snapshot
            state["followup_sha"] = followup
            repo_info.update({"source": source, "snapshot_ref": entry.get("snapshot_ref", "HEAD"), "followup_ref": entry.get("followup_ref", "HEAD"), "snapshot_sha": snapshot, "followup_sha": followup})
            with snapshot_checkout(repo, snapshot) as checkout:
                tests = discover(checkout, repository_id, snapshot)
                state["test_count"] = len(tests)
                repo_info["framework_counts"] = {framework: sum(t["test_framework"] == framework for t in tests) for framework in sorted({str(t["test_framework"]) for t in tests})}
                events, outcomes = mine_history(repo, repository_id, snapshot, followup, [str(t["test_file"]) for t in tests])
                for test in tests:
                    test["detector_status"] = "failed"
                rows_tests.extend(tests)
                rows_events.extend(events)
                rows_outcomes.extend(outcomes)
                if skip_detector:
                    smells = []
                    detect_info = {"status": "skipped_explicitly"}
                else:
                    assert jar is not None
                    smells, detect_info = run_tsdetect(
                        jar, checkout, repository_id, tests, output / "raw" / repository_id, timeout,
                    )
                status = detect_info["status"]
                measured_files = {str(s["test_file"]) for s in smells}
                failed_files = set(detect_info.get("failed_test_files", []))
                for test in tests:
                    name = str(test["test_file"])
                    test["detector_status"] = ("skipped_explicitly" if skip_detector else ("measured" if name in measured_files else ("failed" if name in failed_files else "not_measured")))
                repo_info["detector"] = detect_info
                rows_smells.extend(smells)
                state["smell_rows"] = len(smells)
                state["status"] = "complete" if status == "complete" else ("no_smells_measured" if skip_detector else status)
        except Exception as exc:
            state["error"] = str(exc)[:500]
            repo_info["traceback"] = traceback.format_exc()
            # Failed repository outputs must not be silently represented as zeroes.
        repo_info["finished_utc"] = now()
        repo_info["status"] = state["status"]
        manifest["repositories"].append(repo_info)
        statuses.append(state)

    outcome_map = {(v["repository_id"], v["snapshot_sha"], v["test_file"]): v for v in rows_outcomes}
    analysis = [
        {**t, **{key: value for key, value in outcome_map[(t["repository_id"], t["snapshot_sha"], t["test_file"])].items() if key not in {"repository_id", "snapshot_sha", "test_file"}}}
        for t in rows_tests
    ]
    write_csv(output / "tests.csv", TEST_FIELDS, rows_tests)
    write_csv(output / "smells.csv", SMELL_FIELDS, rows_smells)
    write_csv(output / "commit_events.csv", EVENT_FIELDS, rows_events)
    write_csv(output / "outcomes.csv", OUTCOME_FIELDS, rows_outcomes)
    write_csv(output / "analysis_ready.csv", ANALYSIS_FIELDS, analysis)
    write_csv(output / "repository_status.csv", STATUS_FIELDS, statuses)
    manifest["finished_utc"] = now()
    manifest["counts"] = {
        "repositories": len(statuses), "failed": sum(s["status"] == "failed" for s in statuses),
        "tests": len(rows_tests), "smell_observations": len(rows_smells),
        "commit_events": len(rows_events),
        "measured_smell_values": sum(s["smell_status"] == "measured" for s in rows_smells),
        "missing_smell_values": sum(s["smell_status"] != "measured" for s in rows_smells),
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"output": str(output), **manifest["counts"], "status": statuses}
