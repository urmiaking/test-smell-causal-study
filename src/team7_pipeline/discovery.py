"""Discover actual Java test candidates and annotate likely test frameworks."""
from __future__ import annotations

import re
from pathlib import Path


def is_test_file(relative: str, source: str | None = None) -> bool:
    path = relative.replace("\\", "/").lower()
    name = path.rsplit("/", 1)[-1]
    if not path.endswith(".java"):
        return False
    is_in_test_tree = "/src/test/" in "/" + path or "/test/" in "/" + path
    is_named_test = name.endswith(("test.java", "tests.java")) or name.startswith("test")
    annotated = bool(source and re.search(r"@\s*(?:Test|ParameterizedTest|RepeatedTest|TestFactory)\b", source))
    return (is_in_test_tree and (is_named_test or annotated)) or (
        is_named_test and annotated
    )


def test_framework(source: str) -> str:
    has_jupiter = bool(re.search(r"org\.junit\.jupiter|org\.junit\.platform", source))
    has_junit4 = bool(re.search(r"org\.junit\.(?:Test|Before|After|Assert|Rule|runner|rules)\b", source))
    if has_jupiter and has_junit4:
        return "mixed_junit4_junit5"
    if has_jupiter:
        return "junit5"
    if has_junit4:
        return "junit4"
    if "org.testng" in source:
        return "testng"
    return "unknown"


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
        if not relative.lower().endswith(".java"):
            continue
        src = path.read_text(encoding="utf-8", errors="replace")
        if not is_test_file(relative, src):
            continue
        prod = production_file(root, path)
        rows.append({
            "repository_id": repository_id,
            "snapshot_sha": sha,
            "test_file": relative,
            "production_file": prod.relative_to(root).as_posix() if prod else "",
            "test_framework": test_framework(src),
            "test_loc": sum(1 for line in src.splitlines() if line.strip()),
            "assert_count": len(re.findall(r"\bassert\w*\s*\(", src)),
        })
    return rows
