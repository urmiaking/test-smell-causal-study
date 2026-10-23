import subprocess
from pathlib import Path

import pytest

from team7_pipeline.gitutils import acquire_repository


def git(repo: Path, *args: str) -> str:
    p = subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True)
    return p.stdout.strip()


def test_cached_origin_must_match_source(tmp_path: Path):
    repo = tmp_path / "cache" / "testrepo"
    repo.mkdir(parents=True)
    git(repo, "init", "-b", "main")
    git(repo, "remote", "add", "origin", "https://github.com/org/original.git")
    assert acquire_repository("https://github.com/org/original", tmp_path / "cache", "testrepo") == repo
    with pytest.raises(RuntimeError, match="source mismatch"):
        acquire_repository("https://github.com/org/different.git", tmp_path / "cache", "testrepo")
