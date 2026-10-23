import json
from pathlib import Path

import pytest

from team7_pipeline.sampling import select_repositories


class FakeGitHub:
    def __init__(self):
        self.requests = 0

    def get(self, endpoint, params=None):
        self.requests += 1
        if endpoint == "/search/repositories":
            return {"total_count": 2, "items": [
                {"full_name": "org/alpha", "html_url": "https://github.com/org/alpha",
                 "stargazers_count": 42, "created_at": "2020-01-01T00:00:00Z",
                 "pushed_at": "2025-09-01T00:00:00Z", "fork": False, "archived": False,
                 "language": "Java", "clone_url": "https://github.com/org/alpha.git",
                 "default_branch": "main"},
                {"full_name": "org/beta", "html_url": "https://github.com/org/beta",
                 "stargazers_count": 55, "created_at": "2020-01-01T00:00:00Z",
                 "pushed_at": "2025-09-01T00:00:00Z", "fork": False, "archived": False,
                 "language": "Java", "clone_url": "https://github.com/org/beta.git",
                 "default_branch": "main"},
            ]}
        if endpoint.endswith("/commits"):
            return [{"sha": ("a" if params["until"].startswith("2024") else "b") * 40}]
        if "/compare/" in endpoint:
            return {"status": "ahead", "ahead_by": 12}
        raise ValueError(endpoint)


def test_sampler_audit_pinned_dates_and_nonoverwrite(tmp_path: Path):
    output = tmp_path / "configs/study.json"
    fake = FakeGitHub()
    result = select_repositories(
        output, query="topic:testing", count=2, baseline_date="2024-01-01",
        followup_date="2025-01-01", seed=8, max_candidates=2, github=fake
    )
    assert result["complete_sample"]
    config = json.loads(output.read_text(encoding="utf-8"))
    audit = json.loads((output.parent / "study.sampling-audit.json").read_text(encoding="utf-8"))
    assert len(config["repositories"]) == 2
    assert len(audit["candidate_records"]) == 2
    assert all(r["snapshot_ref"] == "a" * 40 and r["followup_ref"] == "b" * 40 for r in config["repositories"])
    assert config["sampling_protocol"]["seed"] == 8
    with pytest.raises(FileExistsError):
        select_repositories(output, query="topic:testing", count=2,
                            baseline_date="2024-01-01", followup_date="2025-01-01", github=fake)


def test_sampler_refuses_invalid_date_window(tmp_path: Path):
    with pytest.raises(ValueError, match="earlier"):
        select_repositories(tmp_path / "out.json", query="x", count=1,
                            baseline_date="2025-01-01", followup_date="2025-01-01", github=FakeGitHub())
