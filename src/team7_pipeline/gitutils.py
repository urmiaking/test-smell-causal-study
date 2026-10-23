"""Controlled Git operations with immutable commit resolution and detached snapshots."""
from __future__ import annotations

import shutil
import subprocess
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory


def git(repo: Path, *args: str, timeout: int = 90) -> str:
    p = subprocess.run(
        ["git", "-C", str(repo), *args],
        text=True, capture_output=True, encoding="utf-8", errors="replace",
        timeout=timeout, check=False,
    )
    if p.returncode:
        raise RuntimeError(f"git {args[0]} failed ({p.returncode}): {p.stderr.strip()[:1000]}")
    return p.stdout.strip()


def acquire_repository(source: str, cache_dir: Path, repository_id: str) -> Path:
    if source.startswith("https://"):
        # Configured sources only; no execution of downloaded project scripts.
        dest = cache_dir / repository_id
        if not dest.is_dir():
            cache_dir.mkdir(parents=True, exist_ok=True)
            p = subprocess.run(
                ["git", "clone", "--quiet", source, str(dest)],
                text=True, capture_output=True, timeout=600, check=False,
            )
            if p.returncode:
                shutil.rmtree(dest, ignore_errors=True)
                raise RuntimeError(f"clone failed: {p.stderr.strip()[:1000]}")
        else:
            # Cached repositories are pinned at their *already available* refs; do not
            # silently fetch a different revision on repeated runs.
            git(dest, "rev-parse", "--is-inside-work-tree")
            actual_origin = git(dest, "remote", "get-url", "origin")
            def normalized_url(value: str) -> str:
                return value.strip().lower().rstrip("/").removesuffix(".git")
            if normalized_url(actual_origin) != normalized_url(source):
                raise RuntimeError(f"Cache source mismatch for {repository_id}: {actual_origin!r} != {source!r}")
        return dest
    path = Path(source).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"Local repository does not exist: {path}")
    git(path, "rev-parse", "--is-inside-work-tree")
    return path


def commit_sha(repo: Path, ref: str) -> str:
    if not ref or ref.startswith("-"):
        raise ValueError("Invalid Git reference")
    return git(repo, "rev-parse", "--verify", f"{ref}^{{commit}}")


def ensure_ancestor(repo: Path, baseline: str, followup: str) -> None:
    p = subprocess.run(
        ["git", "-C", str(repo), "merge-base", "--is-ancestor", baseline, followup],
        capture_output=True, timeout=60, check=False,
    )
    if p.returncode != 0:
        raise ValueError("snapshot_ref is not an ancestor of followup_ref")


def future_commits(repo: Path, baseline: str, followup: str) -> list[str]:
    if baseline == followup:
        return []
    ensure_ancestor(repo, baseline, followup)
    result = git(repo, "rev-list", "--reverse", "--ancestry-path", f"{baseline}..{followup}", timeout=180)
    return result.splitlines() if result else []


@contextmanager
def snapshot_checkout(repo: Path, sha: str):
    """Use detached git worktree, never modify the user's active checkout."""
    with TemporaryDirectory(prefix="team7-snapshot-") as temp:
        path = Path(temp) / "source"
        git(repo, "worktree", "add", "--detach", "--quiet", str(path), sha, timeout=180)
        try:
            yield path
        finally:
            git(repo, "worktree", "remove", "--force", str(path), timeout=180)
