import csv
import json
import subprocess
from pathlib import Path

from team7_pipeline.pipeline import run


def git(path: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(path), *args], check=True, capture_output=True, text=True)
    return result.stdout.strip()


def test_pipeline_end_to_end_no_detector_preserves_missing(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-b", "main")
    git(repo, "config", "user.name", "Fixture")
    git(repo, "config", "user.email", "fixture@invalid.local")
    source = repo / "src/test/java/AppTest.java"
    source.parent.mkdir(parents=True)
    source.write_text("class AppTest {}\n", encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "baseline")
    base = git(repo, "rev-parse", "HEAD")
    source.write_text("class AppTest { int n = 1; }\n", encoding="utf-8")
    git(repo, "commit", "-am", "test change")
    end = git(repo, "rev-parse", "HEAD")
    config = tmp_path / "pilot.json"
    config.write_text(json.dumps({
        "run_id": "smoke", "output_dir": "out", "repositories": [{
            "id": "fixture", "source": str(repo), "snapshot_ref": base, "followup_ref": end
        }]
    }), encoding="utf-8")
    result = run(config, skip_detector=True)
    assert result["failed"] == 0
    assert result["tests"] == 1
    assert result["smell_observations"] == 0
    with (tmp_path / "out/analysis_ready.csv").open(newline="", encoding="utf-8") as f:
        row = next(csv.DictReader(f))
    assert row["change_commits"] == "1"
    assert row["detector_status"] == "skipped_explicitly"
    with (tmp_path / "out/smells.csv").open(newline="", encoding="utf-8") as f:
        assert list(csv.DictReader(f)) == []
