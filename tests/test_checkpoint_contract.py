import csv
import json
import subprocess
from pathlib import Path

import pytest

from team7_pipeline.contract import compare, validate
from team7_pipeline.pipeline import run


def git(path: Path, *args: str) -> str:
    p = subprocess.run(["git", "-C", str(path), *args], capture_output=True, text=True, check=True)
    return p.stdout.strip()


@pytest.fixture
def two_repos(tmp_path: Path) -> Path:
    entries = []
    for i in range(2):
        repo = tmp_path / f"repo-{i}"
        repo.mkdir()
        git(repo, "init", "-b", "main")
        git(repo, "config", "user.name", "Fixture")
        git(repo, "config", "user.email", "research@invalid.local")
        file = repo / f"src/test/java/Some{i}Test.java"
        file.parent.mkdir(parents=True)
        file.write_text(f"import org.junit.Test; class Some{i}Test {{ @Test public void testX() {{}} }}\n")
        git(repo, "add", ".")
        git(repo, "commit", "-m", "baseline")
        base = git(repo, "rev-parse", "HEAD")
        file.write_text(f"import org.junit.Test; class Some{i}Test {{ @Test public void testX() {{ int x = {i}; }} }}\n")
        git(repo, "commit", "-am", "fix tests")
        end = git(repo, "rev-parse", "HEAD")
        entries.append({"id": f"fixture{i}", "source": str(repo), "snapshot_ref": base, "followup_ref": end})
    config = tmp_path / "pilot.json"
    config.write_text(json.dumps({"run_id": "checkpoint-test", "output_dir": "dataset", "repositories": entries}))
    return config


def test_multi_repo_resume_and_no_recompute(two_repos: Path, tmp_path: Path, monkeypatch):
    first = run(two_repos, skip_detector=True, max_repositories=1)
    assert first["pending"] == 1
    assert first["repositories"] == 1
    assert not (tmp_path / "dataset/manifest.json").exists()
    state_path = tmp_path / "dataset/run_state.json"
    state = json.loads(state_path.read_text())
    sha_before = state["shards"]["fixture0"]
    shard_path = tmp_path / "dataset/.checkpoints/fixture0.json.gz"
    mtime = shard_path.stat().st_mtime_ns
    with pytest.raises(FileExistsError):
        run(two_repos, skip_detector=True)
    original = json.loads(two_repos.read_text())
    original["detector_timeout_seconds"] = 300
    two_repos.write_text(json.dumps(original))
    with pytest.raises(ValueError, match="config, detector"):
        run(two_repos, skip_detector=True, resume=True)
    del original["detector_timeout_seconds"]
    two_repos.write_text(json.dumps(original))
    result = run(two_repos, skip_detector=True, resume=True)
    assert result["pending"] == 0
    assert result["repositories"] == 2
    assert result["tests"] == 2
    assert shard_path.stat().st_mtime_ns == mtime
    assert json.loads(state_path.read_text())["shards"]["fixture0"] == sha_before
    assert (tmp_path / "dataset/manifest.json").exists()
    assert validate(tmp_path / "dataset")["valid"]
    with pytest.raises(FileExistsError):
        run(two_repos, skip_detector=True, resume=True)


def test_contract_pit_attribution_and_compare(two_repos: Path, tmp_path: Path):
    run(two_repos, skip_detector=True)
    a = tmp_path / "dataset"
    config_b = tmp_path / "pilot2.json"
    payload = json.loads(two_repos.read_text())
    payload["output_dir"] = "dataset-2"
    payload["run_id"] = "checkpoint-test-two"
    config_b.write_text(json.dumps(payload))
    run(config_b, skip_detector=True)
    b = tmp_path / "dataset-2"
    assert compare(a, b)["equal"]
    key = next(csv.DictReader((a / "tests.csv").open(encoding="utf-8")))
    pit = tmp_path / "pit.csv"
    with pit.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["repository_id", "snapshot_sha", "test_file", "mutation_score", "attribution_method", "measurement_status"])
        writer.writeheader()
        writer.writerow({**{k: key[k] for k in ("repository_id", "snapshot_sha", "test_file")},
                         "mutation_score": "0.6", "attribution_method": "project_level", "measurement_status": "measured"})
    with pytest.raises(ValueError, match="attribution"):
        validate(a, pit)
    rows = list(csv.DictReader(pit.open(encoding="utf-8")))
    rows[0]["attribution_method"] = "isolated_test_file"
    with pit.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    exported = tmp_path / "joined.csv"
    report = validate(a, pit, exported)
    assert report["pit"]["measured"] == 1
    assert exported.exists()
    row = next(csv.DictReader(exported.open(encoding="utf-8")))
    assert row["measurement_status"] in {"measured", "not_measured"}
    with pytest.raises(FileExistsError):
        validate(a, pit, exported)


def test_corrupt_shard_rejected(two_repos: Path, tmp_path: Path):
    run(two_repos, skip_detector=True, max_repositories=1)
    shard = tmp_path / "dataset/.checkpoints/fixture0.json.gz"
    shard.write_bytes(b"tampered")
    with pytest.raises(RuntimeError, match="checksum"):
        run(two_repos, skip_detector=True, resume=True)
