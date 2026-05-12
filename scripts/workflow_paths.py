#!/usr/bin/env python3
"""Shared path policy for hyptest-workflow generated state."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from skill_config import resolve_path


DEFAULT_WORKFLOW_DIR = ".hyptest_workflow_skill"


def _env_path(name: str) -> Path | None:
    value = os.environ.get(name, "").strip()
    return resolve_path(value) if value else None


def workflow_root(repo_root: Path, override: str | None = None) -> Path:
    """Return the repo-local workflow root directory."""
    if override:
        return resolve_path(override)
    env_root = _env_path("HYPTEST_WORKFLOW_ROOT")
    if env_root:
        return env_root
    return repo_root / DEFAULT_WORKFLOW_DIR


def workflow_cache_dir(repo_root: Path, override: str | None = None) -> Path:
    """Return the default cache directory for rebuildable workflow state."""
    if override:
        return resolve_path(override)
    env_dir = _env_path("HYPTEST_CACHE_DIR")
    if env_dir:
        return env_dir
    return workflow_root(repo_root) / "cache"


def workflow_report_dir(repo_root: Path, override: str | None = None) -> Path:
    """Return the default report directory for workflow evidence files."""
    if override:
        return resolve_path(override)
    env_dir = _env_path("HYPTEST_REPORT_DIR")
    if env_dir:
        return env_dir
    return workflow_root(repo_root) / "reports"


def workflow_memory_dir(repo_root: Path, override: str | None = None) -> Path:
    """Return the append-only local memory directory."""
    if override:
        return resolve_path(override)
    env_dir = _env_path("HYPTEST_MEMORY_DIR")
    if env_dir:
        return env_dir
    return workflow_root(repo_root) / "memory"


def workflow_tmp_dir(repo_root: Path, override: str | None = None) -> Path:
    """Return the workflow temporary directory.

    HYPTEST_TMPDIR is intentionally not used here because it is forwarded to
    hyptest compile/run commands as the compiler/runtime temporary directory.
    """
    if override:
        return resolve_path(override)
    env_dir = _env_path("HYPTEST_WORKFLOW_TMPDIR")
    if env_dir:
        return env_dir
    return workflow_root(repo_root) / "tmp"


def cache_file(repo_root: Path, filename: str, cache_dir_arg: str | None = None) -> Path:
    return workflow_cache_dir(repo_root, cache_dir_arg) / filename


def describe_paths(repo_root: Path) -> dict[str, Any]:
    return {
        "repo_root": str(repo_root),
        "workflow_root": str(workflow_root(repo_root)),
        "cache_dir": str(workflow_cache_dir(repo_root)),
        "report_dir": str(workflow_report_dir(repo_root)),
        "memory_dir": str(workflow_memory_dir(repo_root)),
        "tmp_dir": str(workflow_tmp_dir(repo_root)),
        "env_overrides": {
            "HYPTEST_WORKFLOW_ROOT": os.environ.get("HYPTEST_WORKFLOW_ROOT", ""),
            "HYPTEST_CACHE_DIR": os.environ.get("HYPTEST_CACHE_DIR", ""),
            "HYPTEST_REPORT_DIR": os.environ.get("HYPTEST_REPORT_DIR", ""),
            "HYPTEST_MEMORY_DIR": os.environ.get("HYPTEST_MEMORY_DIR", ""),
            "HYPTEST_WORKFLOW_TMPDIR": os.environ.get("HYPTEST_WORKFLOW_TMPDIR", ""),
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Print hyptest-workflow generated path policy.")
    parser.add_argument("--repo-root", required=True, help="Path to hyptest repo root.")
    parser.add_argument("--json", action="store_true", help="Emit JSON.")
    return parser.parse_args()


def render_text(payload: dict[str, Any]) -> str:
    lines = [
        f"HYPTEST_HOME: {payload['repo_root']}",
        f"workflow_root: {payload['workflow_root']}",
        f"cache_dir: {payload['cache_dir']}",
        f"report_dir: {payload['report_dir']}",
        f"memory_dir: {payload['memory_dir']}",
        f"tmp_dir: {payload['tmp_dir']}",
    ]
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    repo_root = resolve_path(args.repo_root)
    payload = describe_paths(repo_root)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(render_text(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
