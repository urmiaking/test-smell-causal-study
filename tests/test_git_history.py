import subprocess
from pathlib import Path

from team7_pipeline.gitutils import commit_sha, ensure_ancestor, future_commits, snapshot_checkout
from team7_pipeline.miner import mine_history


def git(repo: Path, *args: str) -> str:
    process = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True)
    return process.stdout.strip()


def test_temporal_mining_and_snapshot(tmp_path: Path):
    git(tmp_path, "init", "-b", "main")
    git(tmp_path, "config", "user.name", "Test")
    git(tmp_path, "config", "user.email", "test@invalid.local")
    test = tmp_path / "src/test/java/FooTest.java"
    test.parent.mkdir(parents=True)
    test.write_text("class FooTest {}\n", encoding="utf-8")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-m", "initial baseline")
    baseline = commit_sha(tmp_path, "HEAD")
    test.write_text("class FooTest { int a = 1; }\n", encoding="utf-8")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-m", "fix bug in test")
    followup = commit_sha(tmp_path, "HEAD")
    assert len(future_commits(tmp_path, baseline, followup)) == 1
    ensure_ancestor(tmp_path, baseline, followup)
    with snapshot_checkout(tmp_path, baseline) as snapshot:
        assert "int a" not in (snapshot / "src/test/java/FooTest.java").read_text()
    events, outcome = mine_history(tmp_path, "repo", baseline, followup, ["src/test/java/FooTest.java"])
    assert len(events) == 1
    assert outcome[0]["change_commits"] == 1
    assert outcome[0]["potential_bugfix_commits"] == 1
    assert outcome[0]["followup_observed"] is True
