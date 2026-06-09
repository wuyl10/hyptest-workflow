#!/usr/bin/env python3
"""
Remove generated helper files created by hyptest-workflow skill scripts.
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from workflow_paths import (
    workflow_cache_dir,
    workflow_memory_dir,
    workflow_report_dir,
    workflow_tmp_dir,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Clean hyptest-workflow generated helper files.")
    parser.add_argument("--repo-root", help="Optional hyptest repo root to clean workflow generated state.")
    parser.add_argument(
        "--only",
        choices=("all", "cache", "reports", "tmp"),
        default="all",
        help="Limit repo workflow cleanup to one generated area. Default removes cache, reports, and tmp.",
    )
    parser.add_argument(
        "--skill-only",
        action="store_true",
        help="Only clean generated files under the skill installation; skip --repo-root cleanup.",
    )
    parser.add_argument(
        "--repo-only",
        action="store_true",
        help="Only clean generated files under --repo-root; skip skill installation cleanup.",
    )
    parser.add_argument(
        "--include-memory",
        action="store_true",
        help="Also remove workflow memory. By default memory is preserved.",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON report.")
    return parser.parse_args()


def remove_path(path: Path, removed: list[str]) -> None:
    if not path.exists():
        return
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
    else:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
    removed.append(str(path))


def remove_selected_generated(root: Path, only: str, removed: list[str]) -> None:
    if only in ("all", "tmp"):
        remove_path(workflow_tmp_dir(root), removed)
        remove_path(root / ".tmp", removed)
    if only in ("all", "cache"):
        remove_path(workflow_cache_dir(root), removed)
    if only in ("all", "reports"):
        remove_path(workflow_report_dir(root), removed)


def main() -> int:
    args = parse_args()
    if args.skill_only and args.repo_only:
        raise SystemExit("--skill-only and --repo-only cannot be used together")
    if args.repo_only and not args.repo_root:
        raise SystemExit("--repo-only requires --repo-root")

    skill_root = Path(__file__).resolve().parent.parent
    removed: list[str] = []

    if not args.repo_only:
        remove_selected_generated(skill_root, args.only, removed)
        for path in skill_root.rglob("__pycache__"):
            remove_path(path, removed)

    if args.repo_root and not args.skill_only:
        repo_root = Path(args.repo_root).expanduser().resolve()
        remove_selected_generated(repo_root, args.only, removed)
        if args.include_memory:
            remove_path(workflow_memory_dir(repo_root), removed)

    if args.json:
        import json

        print(json.dumps({"removed": removed}, ensure_ascii=False, indent=2))
    else:
        print(f"removed: {len(removed)}")
        for path in removed:
            print(f"  {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
