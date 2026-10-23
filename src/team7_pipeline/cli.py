"""Command-line interface. Each run produces an immutable manifest and raw evidence."""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

from . import __version__
from .pipeline import run


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="team7", description="Team 7 observational test smell data pipeline")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor", help="Report local prerequisites")
    runner = sub.add_parser("run", help="Run a configured pilot against pinned Java Git repositories")
    runner.add_argument("--config", required=True, type=Path)
    runner.add_argument("--skip-detector", action="store_true", help="Explicitly omit tsDetect; leave smell data EMPTY, not false")
    args = parser.parse_args(argv)
    if args.command == "doctor":
        status = {}
        for executable in ("git", "java", "python", "mvn"):
            executable_path = shutil.which(executable)
            status[executable] = executable_path or "NOT FOUND"
            if executable_path and executable in {"git", "java"}:
                probe = subprocess.run(
                    [executable, "--version"] if executable == "git" else [executable, "-version"],
                    capture_output=True, text=True, timeout=15, check=False,
                )
                status[executable + "_version"] = (probe.stdout or probe.stderr).splitlines()[0]
        status["python_version"] = sys.version.split()[0]
        print(json.dumps(status, indent=2))
        return 0
    try:
        summary = run(args.config, skip_detector=args.skip_detector)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 1 if summary["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
