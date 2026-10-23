"""Temporal outcome mining; never measure future history at the treatment snapshot."""
from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from .gitutils import future_commits

FIX_PATTERN = re.compile(r"\b(fix(?:es|ed)?|bug(?:fix)?|defect|regression)\b", re.IGNORECASE)


def mine_history(
    repo: Path, repository_id: str, snapshot_sha: str, followup_sha: str,
    test_files: list[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return commit-file events and outcomes for each baseline test path.

    PyDriller supplies modified files and commit messages. A Git topo-order list
    restricts events to descendants of baseline up to followup, never earlier.
    """
    from pydriller import Repository

    sha_order = future_commits(repo, snapshot_sha, followup_sha)
    tracking = {name: name for name in test_files}  # current path -> baseline path
    events: list[dict[str, Any]] = []
    counts: dict[str, set[str]] = defaultdict(set)
    potential: dict[str, set[str]] = defaultdict(set)

    if sha_order:
        allowed = set(sha_order)
        commits = {c.hash: c for c in Repository(str(repo), only_commits=sha_order).traverse_commits() if c.hash in allowed}
        for sha in sha_order:
            commit = commits.get(sha)
            if commit is None:
                raise RuntimeError(f"PyDriller did not return expected commit {sha}")
            matches = set()
            for changed in commit.modified_files:
                old = changed.old_path.replace("\\", "/") if changed.old_path else None
                new = changed.new_path.replace("\\", "/") if changed.new_path else None
                original = tracking.get(old) if old else None
                if original is None and new:
                    original = tracking.get(new)
                if original is None:
                    continue
                matches.add(original)
                if old and old != new:
                    tracking.pop(old, None)
                if new:
                    tracking[new] = original
                elif old:
                    tracking.pop(old, None)
            for baseline_path in sorted(matches):
                counts[baseline_path].add(sha)
                if FIX_PATTERN.search(commit.msg or ""):
                    potential[baseline_path].add(sha)
                events.append({
                    "repository_id": repository_id,
                    "snapshot_sha": snapshot_sha,
                    "followup_sha": followup_sha,
                    "test_file": baseline_path,
                    "commit_sha": sha,
                    "commit_date": commit.committer_date.isoformat(),
                    "author_name": commit.author.name,
                    "potential_bugfix_message": bool(FIX_PATTERN.search(commit.msg or "")),
                })

    final_paths = {baseline: "" for baseline in test_files}
    for current, baseline in tracking.items():
        final_paths[baseline] = current
    outcome = [{
        "repository_id": repository_id,
        "snapshot_sha": snapshot_sha,
        "followup_sha": followup_sha,
        "test_file": baseline,
        "followup_test_file": final_paths[baseline],
        "change_commits": len(counts[baseline]),
        "potential_bugfix_commits": len(potential[baseline]),
        "followup_commits_all_repo": len(sha_order),
        "followup_observed": snapshot_sha != followup_sha,
    } for baseline in sorted(test_files)]
    return events, outcome
