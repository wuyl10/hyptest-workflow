#!/usr/bin/env python3
"""
Remove generated helper files created by hyptest-workflow skill scripts.
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Clean hyptest-workflow generated helper files.")
    parser.add_argument("--repo-root", help="Optional hyptest repo root to clean .hyptest_skill_cache.")
    parser.add_argument("--json", action="store_true", help="Emit JSON report.")
    return parser.parse_args()


def remove_path(path: Path, removed: list[str]) -> None:
    if not path.exists():
        return
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()
    removed.append(str(path))


def main() -> int:
    args = parse_args()
    skill_root = Path(__file__).resolve().parent.parent
    removed: list[str] = []
    remove_path(skill_root / ".hyptest_skill_tmp", removed)
    remove_path(skill_root / ".hyptest_skill_cache", removed)
    remove_path(skill_root / ".hyptest_skill_reports", removed)
    for path in skill_root.rglob("__pycache__"):
        remove_path(path, removed)
    if args.repo_root:
        repo_root = Path(args.repo_root).expanduser().resolve()
        remove_path(repo_root / ".hyptest_skill_cache", removed)
        remove_path(repo_root / ".hyptest_skill_tmp", removed)
        remove_path(repo_root / ".hyptest_skill_reports", removed)

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
