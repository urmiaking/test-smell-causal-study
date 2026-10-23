"""Discover Java test files in a particular immutable checkout."""
from __future__ import annotations

import re
from pathlib import Path


def is_test_file(relative: str) -> bool:
    path = relative.replace("\\", "/").lower()
    name = path.rsplit("/", 1)[-1]
    return path.endswith(".java") and (
        "/src/test/" in "/" + path
        or "/test/" in "/" + path
        or name.endswith("test.java")
        or name.endswith("tests.java")
    )


def production_file(root: Path, test_file: Path) -> Path | None:
    rel = test_file.relative_to(root).as_posix()
    mapping = rel.replace("/src/test/java/", "/src/main/java/", 1)
    if mapping == rel and rel.startswith("src/test/java/"):
        mapping = "src/main/java/" + rel[len("src/test/java/"):]
    if mapping == rel:
        return None
    potential = Path(mapping)
    stem = potential.stem
    for name in ([stem[:-4] + ".java"] if stem.endswith("Test") else []) + [potential.name]:
        candidate = root / potential.parent / name
        if candidate.exists() and candidate.is_file():
            return candidate
    return None


def discover(root: Path, repository_id: str, sha: str) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for path in sorted(root.rglob("*.java")):
        if any(part in {"target", "build", ".git", ".gradle"} for part in path.relative_to(root).parts):
            continue
        relative = path.relative_to(root).as_posix()
        if not is_test_file(relative):
            continue
        src = path.read_text(encoding="utf-8", errors="replace")
        prod = production_file(root, path)
        rows.append({
            "repository_id": repository_id,
            "snapshot_sha": sha,
            "test_file": relative,
            "production_file": prod.relative_to(root).as_posix() if prod else "",
            "test_loc": sum(1 for line in src.splitlines() if line.strip()),
            "assert_count": len(re.findall(r"\bassert\w*\s*\(", src)),
        })
    return rows
