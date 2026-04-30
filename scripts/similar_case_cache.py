#!/usr/bin/env python3
"""
Cache helpers for find_similar_cases.py.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Callable, Dict, List, Tuple


CACHE_VERSION = 1


def source_fingerprint(repo_root: Path) -> Dict[str, object]:
    paths: List[Path] = []
    for rel in ("ai_test_cases", "manual_test_cases"):
        root = repo_root / rel
        if root.is_dir():
            paths.extend(sorted(root.rglob("*.c")))
    register_path = repo_root / "test_register.c"
    if register_path.is_file():
        paths.append(register_path)

    digest = hashlib.sha256()
    entries: List[Dict[str, object]] = []
    for path in sorted(paths):
        rel = str(path.relative_to(repo_root))
        stat = path.stat()
        entry = {
            "path": rel,
            "mtime_ns": stat.st_mtime_ns,
            "size": stat.st_size,
        }
        entries.append(entry)
        digest.update(rel.encode("utf-8"))
        digest.update(str(stat.st_mtime_ns).encode("ascii"))
        digest.update(str(stat.st_size).encode("ascii"))

    return {
        "version": CACHE_VERSION,
        "digest": digest.hexdigest(),
        "entries": entries,
    }


def cache_path(repo_root: Path, cache_dir_arg: str | None) -> Path:
    if cache_dir_arg:
        return Path(cache_dir_arg).expanduser().resolve() / "find_similar_cases_index.json"
    return repo_root / ".hyptest_skill_cache" / "find_similar_cases_index.json"


def load_with_cache(
    repo_root: Path,
    *,
    use_cache: bool,
    cache_dir_arg: str | None,
    builder: Callable[[Path], List[Dict[str, str]]],
) -> Tuple[List[Dict[str, str]], Dict[str, object]]:
    if not use_cache:
        started = time.monotonic()
        cases = builder(repo_root)
        return cases, {
            "enabled": False,
            "hit": False,
            "path": None,
            "build_seconds": round(time.monotonic() - started, 3),
        }

    fingerprint = source_fingerprint(repo_root)
    path = cache_path(repo_root, cache_dir_arg)
    if path.is_file():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if payload.get("fingerprint") == fingerprint:
                return payload["cases"], {
                    "enabled": True,
                    "hit": True,
                    "path": str(path),
                    "build_seconds": 0.0,
                }
        except (json.JSONDecodeError, OSError, KeyError, TypeError):
            pass

    started = time.monotonic()
    cases = builder(repo_root)
    cache_info: Dict[str, object] = {
        "enabled": True,
        "hit": False,
        "path": str(path),
        "build_seconds": round(time.monotonic() - started, 3),
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "fingerprint": fingerprint,
                    "cases": cases,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
    except OSError as exc:
        cache_info["write_error"] = str(exc)
    return cases, cache_info
