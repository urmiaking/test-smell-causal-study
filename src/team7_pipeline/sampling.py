"""Auditable GitHub sampling: dated snapshots, explicit exclusions, fixed seed.

This is a convenience sampler, NOT an unbiased sample of all Java projects.
GitHub Search ranking / 1000-item cap / public visibility remain selection biases.
"""
from __future__ import annotations

import json
import os
import random
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .checkpoint import atomic_json


class GitHubAPI:
    def __init__(self, min_delay: float = 0.25):
        self.last = 0.0
        self.min_delay = min_delay
        self.requests = 0

    def get(self, endpoint: str, params: dict[str, Any] | None = None) -> dict | list:
        elapsed = time.monotonic() - self.last
        if elapsed < self.min_delay:
            time.sleep(self.min_delay - elapsed)
        url = "https://api.github.com" + endpoint
        if params:
            url += "?" + urlencode(params)
        token = os.environ.get("GITHUB_TOKEN")
        headers = {"Accept": "application/vnd.github+json", "User-Agent": "Test7-Research-Sampler",
                   "X-GitHub-Api-Version": "2022-11-28"}
        if token:
            headers["Authorization"] = "Bearer " + token
        self.last = time.monotonic()
        self.requests += 1
        try:
            with urlopen(Request(url, headers=headers), timeout=30) as r:
                return json.load(r)
        except HTTPError as exc:
            remaining = exc.headers.get("X-RateLimit-Remaining", "unknown")
            reset = exc.headers.get("X-RateLimit-Reset", "unknown")
            raise RuntimeError(
                f"GitHub API HTTP {exc.code}; remaining={remaining}; reset_epoch={reset}; endpoint={endpoint}. "
                "Do not silently retry rate limit; set GITHUB_TOKEN or re-run later."
            ) from exc
        except URLError as exc:
            raise RuntimeError(f"GitHub API unreachable for {endpoint}: {exc}") from exc


def select_repositories(
    output: Path, *, query: str, count: int, baseline_date: str, followup_date: str,
    seed: int = 7, min_stars: int = 20, max_candidates: int = 60,
    max_pages: int = 3, github: GitHubAPI | None = None,
) -> dict[str, Any]:
    """Create audited, runnable config with verified non-equal ancestor commits."""
    baseline = date.fromisoformat(baseline_date)
    followup = date.fromisoformat(followup_date)
    if baseline >= followup:
        raise ValueError("baseline_date must be earlier than followup_date")
    if count < 1 or max_candidates < count or max_pages < 1 or max_pages > 10:
        raise ValueError("Invalid count / candidate or page budget")
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite existing sample: {output}")
    api = github or GitHubAPI()
    started = datetime.now(timezone.utc).isoformat()
    search_query = f"{query} language:Java stars:>={min_stars} fork:false archived:false"
    discovered: dict[str, dict[str, Any]] = {}
    total_count = 0
    for page in range(1, max_pages + 1):
        response = api.get("/search/repositories", {
            "q": search_query, "sort": "stars", "order": "desc", "page": page, "per_page": 100
        })
        if not isinstance(response, dict):
            raise RuntimeError("Unexpected GitHub search response")
        total_count = int(response.get("total_count", 0))
        for item in response.get("items", []):
            full_name = item["full_name"]
            if full_name not in discovered:
                discovered[full_name] = {
                    "full_name": full_name, "url": item.get("html_url"),
                    "stars": item.get("stargazers_count"),
                    "created_at": item.get("created_at"), "pushed_at": item.get("pushed_at"),
                    "fork": item.get("fork"), "archived": item.get("archived"),
                    "language": item.get("language"), "clone_url": item.get("clone_url"),
                    "default_branch": item.get("default_branch"),
                }
        if len(discovered) >= max_candidates or len(response.get("items", [])) < 100:
            break
    candidates = sorted(discovered.values(), key=lambda c: c["full_name"])
    rng = random.Random(seed)
    rng.shuffle(candidates)
    candidates = candidates[:max_candidates]
    audit: list[dict[str, Any]] = []
    selected: list[dict[str, Any]] = []
    for candidate in candidates:
        if len(selected) >= count:
            audit.append({**candidate, "decision": "not_evaluated_quota_reached"})
            continue
        reason = ""
        refs: dict[str, Any] = {}
        name = candidate["full_name"]
        if candidate["fork"] or candidate["archived"] or candidate["language"] != "Java":
            reason = "excluded_metadata"
        else:
            try:
                for label, day in (("snapshot_sha", baseline), ("followup_sha", followup)):
                    commits = api.get(f"/repos/{name}/commits", {
                        "until": day.isoformat() + "T23:59:59Z",
                        "per_page": 1, "sha": candidate["default_branch"],
                    })
                    if not isinstance(commits, list) or not commits:
                        raise ValueError("No commit available before " + day.isoformat())
                    refs[label] = commits[0]["sha"]
                if refs["snapshot_sha"] == refs["followup_sha"]:
                    raise ValueError("No follow-up commits in requested date window")
                compare = api.get(f"/repos/{name}/compare/{refs['snapshot_sha']}...{refs['followup_sha']}")
                if not isinstance(compare, dict) or compare.get("status") not in {"ahead", "identical"}:
                    raise ValueError("Commit ancestry check not ahead")
                if int(compare.get("ahead_by", 0)) < 1:
                    raise ValueError("Empty follow-up window")
                refs["ahead_by"] = int(compare["ahead_by"])
            except (RuntimeError, ValueError, KeyError, TypeError) as exc:
                reason = str(exc)[:300]
        if reason:
            audit.append({**candidate, "decision": "excluded", "reason": reason, **refs})
        else:
            selected.append({
                "id": name.replace("/", "_"), "source": candidate["clone_url"],
                "snapshot_ref": refs["snapshot_sha"], "followup_ref": refs["followup_sha"],
                "github_full_name": name, "github_stars_at_sampling": candidate["stars"],
                "baseline_date_utc": baseline.isoformat(), "followup_date_utc": followup.isoformat(),
                "ahead_by": refs["ahead_by"],
            })
            audit.append({**candidate, "decision": "selected", **refs})
    config = {
        "_comment": "Generated from GitHub public search. SEE adjacent sampling audit for selection bias and exclusions.",
        "run_id": output.stem.replace(".", "-"),
        "output_dir": "../results/" + output.stem,
        "cache_dir": "../data/repos",
        "detector_jar": "../tools/TestSmellDetector.jar",
        "batch_size": 25,
        "detector_timeout_seconds": 180,
        "random_seed": seed,
        "sampling_protocol": {
            "type": "GitHubSearch_star_ranked_seeded_candidates",
            "query": search_query, "seed": seed, "baseline_date_utc": baseline.isoformat(),
            "followup_date_utc": followup.isoformat(), "discovered_at_utc": started,
            "caveats": "Search ranking, public-only sampling, GitHub API caps and candidate exclusions limit external validity."
        },
        "repositories": selected
    }
    audit_path = output.with_name(output.stem + ".sampling-audit.json")
    summary = {
        "generated_at_utc": started, "requested": count, "selected": len(selected),
        "github_reported_total": total_count, "search_query": search_query,
        "seed": seed, "requests": api.requests, "candidate_records": audit,
    }
    # An interrupted API retrieval must not write a misleading or incomplete config.
    output.parent.mkdir(parents=True, exist_ok=True)
    atomic_json(audit_path, summary)
    atomic_json(output, config)
    return {"config": str(output), "audit": str(audit_path), "selected": len(selected),
            "requested": count, "requests": api.requests, "complete_sample": len(selected) == count}
