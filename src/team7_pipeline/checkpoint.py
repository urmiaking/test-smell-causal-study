"""Atomic per-repository checkpoint storage; existing evidence is never silently discarded."""
from __future__ import annotations

import gzip
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, suffix=".tmp", delete=False) as f:
        name = f.name
        json.dump(value, f, indent=2, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    try:
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def save_shard(path: Path, value: dict[str, Any]) -> str:
    """Write a gzip JSON shard atomically, return its SHA-256 for integrity checks."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("wb", dir=path.parent, suffix=".tmp", delete=False) as f:
        name = f.name
        with gzip.GzipFile(fileobj=f, mode="wb", mtime=0) as z:
            z.write(json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8"))
        f.flush()
        os.fsync(f.fileno())
    try:
        digest = hashlib.sha256(Path(name).read_bytes()).hexdigest()
        os.replace(name, path)
        return digest
    finally:
        Path(name).unlink(missing_ok=True)


def load_shard(path: Path, expected_sha: str) -> dict[str, Any]:
    if not path.is_file():
        raise RuntimeError(f"Missing checkpoint shard: {path}")
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected_sha:
        raise RuntimeError(f"Checkpoint checksum mismatch: {path}")
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return json.load(f)
