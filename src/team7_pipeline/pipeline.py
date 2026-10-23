"""Durable research collector: one immutable, checksummed checkpoint per repository.

A killed run can resume without recomputing earlier repositories. Aggregate CSVs are
rebuilt from checkpoints, never edited by hand. All failed/partial data is retained.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
import traceback
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path
from typing import Any

from .checkpoint import atomic_json, canonical_hash, load_shard, save_shard
from .detector import sha256
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
DATASETS = {"tests.csv": ("tests", TEST_FIELDS), "smells.csv": ("smells", SMELL_FIELDS),
            "commit_events.csv": ("events", EVENT_FIELDS), "outcomes.csv": ("outcomes", OUTCOME_FIELDS),
            "analysis_ready.csv": ("analysis", ANALYSIS_FIELDS),
            "repository_status.csv": ("status_row", STATUS_FIELDS)}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def resolve(value: str, config_dir: Path) -> Path:
    candidate = Path(value).expanduser()
    return (candidate if candidate.is_absolute() else config_dir / candidate).resolve()


def _environment() -> dict[str, Any]:
    root = Path(__file__).resolve().parents[2]
    def probe(*command: str) -> str:
        p = subprocess.run(list(command), capture_output=True, text=True, timeout=50, check=False)
        return (p.stdout or p.stderr).strip()
    return {
        "python": sys.version, "platform": platform.platform(), "cpu_count": os.cpu_count(),
        "pydriller": version("PyDriller"), "git": probe("git", "--version"),
        "java": probe("java", "-version").splitlines()[0],
        "pip_freeze": probe(sys.executable, "-m", "pip", "freeze").splitlines(),
        "pipeline_git_sha": probe("git", "-C", str(root), "rev-parse", "HEAD"),
        "pipeline_git_dirty": bool(probe("git", "-C", str(root), "status", "--porcelain")),
    }


def _fingerprint(config: dict[str, Any], skip_detector: bool, jar: Path | None) -> str:
    return canonical_hash({
        "config": config, "skip_detector": skip_detector,
        "detector_sha256": sha256(jar) if jar and not skip_detector else None,
        "schema_version": 2,
    })


def _validate_config(config: dict[str, Any]) -> None:
    run_id = str(config["run_id"])
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", run_id):
        raise ValueError("run_id must contain only safe filename characters")
    repos = config.get("repositories") or []
    if not repos:
        raise ValueError("At least one repository is required")
    ids = [r["id"] for r in repos]
    if len(set(ids)) != len(ids) or any(not re.fullmatch(r"[A-Za-z0-9_-]+", x) for x in ids):
        raise ValueError("Repository IDs must be unique and alphanumeric with underscores or hyphens")
    if int(config.get("detector_timeout_seconds", 180)) < 1:
        raise ValueError("detector_timeout_seconds must be positive")
    if int(config.get("batch_size", 25)) < 1:
        raise ValueError("batch_size must be positive")
    for item in repos:
        if not item.get("source") or not item.get("snapshot_ref") or not item.get("followup_ref"):
            raise ValueError(f"Repository {item['id']} must explicitly specify source and BOTH commit refs")
        if any(str(item[k]).startswith("-") for k in ("snapshot_ref", "followup_ref")):
            raise ValueError("Invalid commit refs")


def _process(entry: dict[str, Any], base: Path, cache: Path, jar: Path | None,
             output: Path, skip_detector: bool, timeout: int, batch_size: int) -> dict[str, Any]:
    repository_id = entry["id"]
    state = {"repository_id": repository_id, "status": "failed", "snapshot_sha": "",
             "followup_sha": "", "test_count": 0, "smell_rows": 0, "error": ""}
    info = {"repository_id": repository_id, "started_utc": now(),
            "sample_metadata": {k: v for k, v in entry.items()
                                if k not in {"id", "source", "snapshot_ref", "followup_ref"}}}
    rows: dict[str, list[dict[str, Any]]] = {"tests": [], "smells": [], "events": [], "outcomes": [], "analysis": []}
    try:
        source = str(entry["source"])
        source = source if source.startswith("https://") else str(resolve(source, base))
        repo = acquire_repository(source, cache, repository_id)
        snapshot = commit_sha(repo, entry["snapshot_ref"])
        followup = commit_sha(repo, entry["followup_ref"])
        ensure_ancestor(repo, snapshot, followup)
        state.update(snapshot_sha=snapshot, followup_sha=followup)
        info.update(source=source, snapshot_ref=entry["snapshot_ref"], followup_ref=entry["followup_ref"],
                    snapshot_sha=snapshot, followup_sha=followup)
        with snapshot_checkout(repo, snapshot) as checkout:
            tests = discover(checkout, repository_id, snapshot)
            state["test_count"] = len(tests)
            info["framework_counts"] = {name: sum(t["test_framework"] == name for t in tests)
                                         for name in sorted({str(t["test_framework"]) for t in tests})}
            rows["tests"] = tests
            events, outcomes = mine_history(repo, repository_id, snapshot, followup,
                                            [str(t["test_file"]) for t in tests])
            rows["events"] = events
            rows["outcomes"] = outcomes
            if skip_detector:
                smells: list[dict[str, Any]] = []
                detector = {"status": "skipped_explicitly", "failed_test_files": []}
            else:
                assert jar is not None
                smells, detector = run_tsdetect(jar, checkout, repository_id, tests,
                                                 output / "raw" / repository_id,
                                                 timeout, batch_size=batch_size)
            rows["smells"] = smells
            info["detector"] = detector
            measured_files = {str(s["test_file"]) for s in smells}
            failed_files = set(detector.get("failed_test_files", []))
            for test in tests:
                name = str(test["test_file"])
                test["detector_status"] = ("skipped_explicitly" if skip_detector else
                                           ("measured" if name in measured_files else
                                            ("failed" if name in failed_files else "not_measured")))
            outcome_by_key = {o["test_file"]: o for o in outcomes}
            rows["analysis"] = [
                {**t, **{k: v for k, v in outcome_by_key[str(t["test_file"])].items()
                        if k not in ("repository_id", "snapshot_sha", "test_file")}} for t in tests
            ]
            state["smell_rows"] = len(smells)
            detector_status = detector["status"]
            state["status"] = ("no_smells_measured" if skip_detector else detector_status)
            if not skip_detector and detector_status == "failed":
                state["error"] = "All tsDetect batches failed; inspect per-file failure logs."
    except Exception as exc:
        state["error"] = str(exc)[:600]
        state["status"] = "failed"
        info["traceback"] = traceback.format_exc()
        # Even on detector exceptions, collected test/history data survive.
        if rows["tests"]:
            for test in rows["tests"]:
                test.setdefault("detector_status", "failed")
            outcome_by_key = {o["test_file"]: o for o in rows["outcomes"]}
            rows["analysis"] = [
                {**t, **{k: v for k, v in outcome_by_key[str(t["test_file"])].items()
                        if k not in ("repository_id", "snapshot_sha", "test_file")}}
                for t in rows["tests"] if str(t["test_file"]) in outcome_by_key
            ]
    info["finished_utc"] = now()
    info["status"] = state["status"]
    rows["status_row"] = [state]
    return {"data": rows, "info": info}


def _aggregate(output: Path, repos: list[dict[str, Any]], entries: dict[str, str]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    writers: dict[str, tuple[Any, Any, Path]] = {}
    states: list[dict[str, Any]] = []
    counts = {"repositories": 0, "failed": 0, "partial": 0, "tests": 0,
              "smell_observations": 0, "commit_events": 0,
              "measured_smell_values": 0, "missing_smell_values": 0}
    infos: list[dict[str, Any]] = []
    try:
        for file, (_, fields) in DATASETS.items():
            tmp = output / (file + ".part")
            f = tmp.open("w", encoding="utf-8", newline="")
            writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            writers[file] = (f, writer, tmp)
        for entry in repos:
            ident = entry["id"]
            if ident not in entries:
                continue
            shard = load_shard(output / ".checkpoints" / (ident + ".json.gz"), entries[ident])
            data = shard["data"]
            for filename, (key, _) in DATASETS.items():
                writers[filename][1].writerows(data[key])
            st = data["status_row"][0]
            states.append(st)
            infos.append(shard["info"])
            counts["repositories"] += 1
            counts["failed"] += st["status"] == "failed"
            counts["partial"] += st["status"] == "partial"
            counts["tests"] += len(data["tests"])
            counts["smell_observations"] += len(data["smells"])
            counts["commit_events"] += len(data["events"])
            counts["measured_smell_values"] += sum(s["smell_status"] == "measured" for s in data["smells"])
            counts["missing_smell_values"] += sum(s["smell_status"] != "measured" for s in data["smells"])
    finally:
        for f, _, _ in writers.values():
            f.close()
    for filename, (_, _, tmp) in writers.items():
        os.replace(tmp, output / filename)
    return infos, counts


def run(config_path: Path, skip_detector: bool = False, resume: bool = False,
        retry_failed: bool = False, max_repositories: int | None = None) -> dict[str, Any]:
    config_path = config_path.resolve()
    config = json.loads(config_path.read_text(encoding="utf-8-sig"))
    _validate_config(config)
    base = config_path.parent
    output = resolve(config["output_dir"], base)
    cache = resolve(config.get("cache_dir", "../data/repos"), base)
    jar = resolve(config["detector_jar"], base) if config.get("detector_jar") else None
    if not skip_detector and (jar is None or not jar.is_file()):
        raise FileNotFoundError("Approved tsDetect jar missing (or use --skip-detector explicitly)")
    fingerprint = _fingerprint(config, skip_detector, jar)
    state_path = output / "run_state.json"
    manifest_path = output / "manifest.json"
    if max_repositories is not None and max_repositories < 1:
        raise ValueError("max_repositories must be positive")

    if output.exists() and not resume and (state_path.exists() or manifest_path.exists()):
        raise FileExistsError(f"Output already used: {output}. Use --resume or a new output path.")
    if resume:
        if not state_path.exists():
            raise FileNotFoundError("Cannot resume: run_state.json does not exist")
        run_state = json.loads(state_path.read_text(encoding="utf-8"))
        if run_state.get("fingerprint") != fingerprint:
            raise ValueError("Resume refused: config, detector SHA or skip-detector mode changed")
        if manifest_path.exists() and not retry_failed:
            raise FileExistsError("Finalized run is immutable; choose a new output for re-runs")
    else:
        if output.exists() and any(output.iterdir()):
            raise FileExistsError("Output directory is not empty; refusing to overwrite artifacts")
        output.mkdir(parents=True, exist_ok=True)
        run_state = {"schema_version": 2, "run_id": config["run_id"],
                     "fingerprint": fingerprint, "started_utc": now(), "shards": {},
                     "sampling_protocol": config.get("sampling_protocol", "NOT_REGISTERED")}
        atomic_json(state_path, run_state)
    if retry_failed and not resume:
        raise ValueError("--retry-failed requires --resume")

    todo: list[dict[str, Any]] = []
    for entry in config["repositories"]:
        ident = entry["id"]
        if ident not in run_state["shards"]:
            todo.append(entry)
        elif retry_failed:
            previous = load_shard(output / ".checkpoints" / (ident + ".json.gz"),
                                  run_state["shards"][ident])
            if previous["data"]["status_row"][0]["status"] == "failed":
                todo.append(entry)
    if max_repositories is not None:
        todo = todo[:max_repositories]
    for entry in todo:
        ident = entry["id"]
        if ident in run_state["shards"]:
            # Preserve raw JAR evidence BEFORE retrying, which otherwise rewrites raw/ID.
            import shutil
            previous_sha = run_state["shards"][ident]
            original_raw = output / "raw" / ident
            archived_raw = output / "raw_archive" / ident / previous_sha[:16]
            if original_raw.is_dir() and not archived_raw.exists():
                shutil.copytree(original_raw, archived_raw)
        shard = _process(entry, base, cache, jar, output, skip_detector,
                         int(config.get("detector_timeout_seconds", 180)),
                         int(config.get("batch_size", 25)))
        if ident in run_state["shards"]:
            shard["info"]["retried_from_checkpoint_sha256"] = run_state["shards"][ident]
            original = output / ".checkpoints" / (ident + ".json.gz")
            backup = output / ".checkpoints" / (ident + ".previous." + run_state["shards"][ident][:16] + ".json.gz")
            if not backup.exists():
                import shutil
                shutil.copy2(original, backup)
        checksum = save_shard(output / ".checkpoints" / (ident + ".json.gz"), shard)
        run_state["shards"][ident] = checksum
        run_state["updated_utc"] = now()
        atomic_json(state_path, run_state)

    infos, counts = _aggregate(output, config["repositories"], run_state["shards"])
    complete = counts["repositories"] == len(config["repositories"])
    if complete:
        if manifest_path.exists():
            backup = output / ("manifest.previous." + hashlib.sha256(manifest_path.read_bytes()).hexdigest()[:16] + ".json")
            if not backup.exists():
                backup.write_bytes(manifest_path.read_bytes())
        manifest = {"run_id": config["run_id"], "started_utc": run_state["started_utc"],
                    "finished_utc": now(), "config_file": str(config_path),
                    "config_fingerprint": fingerprint, "environment": _environment(),
                    "sampling_protocol": run_state["sampling_protocol"],
                    "skip_detector": skip_detector, "repositories": infos,
                    "checkpoint_sha256": run_state["shards"], "counts": counts}
        atomic_json(manifest_path, manifest)
    return {"output": str(output), **counts, "pending": len(config["repositories"]) - counts["repositories"],
            "resumable": not complete, "status": [info["status"] for info in infos]}
