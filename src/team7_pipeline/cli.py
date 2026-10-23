"""Command line for durable collection, audited sampling and inter-role validation."""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

from . import __version__
from .contract import compare, validate
from .pipeline import run
from .sampling import select_repositories


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="team7", description="Team 7 observational test smell pipeline")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor", help="Inspect runtime prerequisites")

    runner = sub.add_parser("run", help="Run a study batch with atomic per-repo checkpoints")
    runner.add_argument("--config", type=Path, required=True)
    runner.add_argument("--skip-detector", action="store_true", help="Record missing smell data, never false")
    runner.add_argument("--resume", action="store_true", help="Resume partial run without recomputing saved repos")
    runner.add_argument("--retry-failed", action="store_true", help="With --resume, reattempt failed repo shards; back up old checkpoint")
    runner.add_argument("--max-repositories", type=int, help="Intentionally stop after this many new repositories")

    sampler = sub.add_parser("sample", help="Select auditable dated Java repository snapshots using GitHub public REST API")
    sampler.add_argument("--query", required=True, help="GitHub repository search query, excluding language/filter boilerplate")
    sampler.add_argument("--count", type=int, required=True)
    sampler.add_argument("--baseline-date", required=True, help="YYYY-MM-DD UTC")
    sampler.add_argument("--followup-date", required=True, help="YYYY-MM-DD UTC (later than baseline)")
    sampler.add_argument("--output", type=Path, required=True)
    sampler.add_argument("--seed", type=int, default=7)
    sampler.add_argument("--min-stars", type=int, default=20)
    sampler.add_argument("--max-candidates", type=int, default=60)
    sampler.add_argument("--max-pages", type=int, default=3)

    validator = sub.add_parser("validate", help="Validate baseline/test/smell/outcome joins, optionally PIT attribution")
    validator.add_argument("--results", type=Path, required=True)
    validator.add_argument("--pit", type=Path)
    validator.add_argument("--export", type=Path, help="Write validated analysis+PIT join to a fresh file")
    verifier = sub.add_parser("compare", help="Compare deterministic CSV data from two independent runs")
    verifier.add_argument("--left", type=Path, required=True)
    verifier.add_argument("--right", type=Path, required=True)

    args = parser.parse_args(argv)
    if args.command == "doctor":
        status = {}
        for executable in ("git", "java", "python", "mvn"):
            location = shutil.which(executable)
            status[executable] = location or "NOT FOUND"
            if location and executable in ("git", "java"):
                p = subprocess.run(
                    [executable, "--version"] if executable == "git" else [executable, "-version"],
                    capture_output=True, text=True, timeout=15, check=False,
                )
                status[executable + "_version"] = (p.stdout or p.stderr).splitlines()[0]
        status["python_version"] = sys.version.split()[0]
        print(json.dumps(status, indent=2))
        return 0
    try:
        if args.command == "run":
            result = run(args.config, skip_detector=args.skip_detector, resume=args.resume,
                         retry_failed=args.retry_failed, max_repositories=args.max_repositories)
            code = 1 if result["failed"] else 0
        elif args.command == "sample":
            result = select_repositories(args.output, query=args.query, count=args.count,
                                          baseline_date=args.baseline_date, followup_date=args.followup_date,
                                          seed=args.seed, min_stars=args.min_stars,
                                          max_candidates=args.max_candidates, max_pages=args.max_pages)
            code = 0 if result["complete_sample"] else 1
        elif args.command == "validate":
            result = validate(args.results, args.pit, args.export)
            code = 0
        else:
            result = compare(args.left, args.right)
            code = 0 if result["equal"] else 1
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
