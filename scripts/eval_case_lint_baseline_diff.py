#!/usr/bin/env python3
"""Regression checks for case_lint_baseline_diff.py."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parent


def temp_parent() -> Path:
    path = SKILL_ROOT / ".hyptest_skill_tmp"
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_baseline(path: Path, keys: list[str]) -> None:
    path.write_text(json.dumps({"issue_keys": keys}, indent=2), encoding="utf-8")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="hyptest_baseline_diff_", dir=temp_parent()) as tmpdir:
        tmp = Path(tmpdir)
        old = tmp / "old.json"
        new_same = tmp / "new_same.json"
        new_added = tmp / "new_added.json"
        write_baseline(old, ["a", "b"])
        write_baseline(new_same, ["a", "b"])
        write_baseline(new_added, ["a", "b", "c"])
        same = subprocess.run(
            [sys.executable, str(SCRIPT_DIR / "case_lint_baseline_diff.py"), "--old", str(old), "--new", str(new_same)],
            capture_output=True,
            text=True,
            check=False,
        )
        added = subprocess.run(
            [sys.executable, str(SCRIPT_DIR / "case_lint_baseline_diff.py"), "--old", str(old), "--new", str(new_added)],
            capture_output=True,
            text=True,
            check=False,
        )
    if same.returncode != 0 or added.returncode == 0:
        print("FAIL case lint baseline diff eval")
        print(same.stdout)
        print(added.stdout)
        return 1
    print("PASS case lint baseline diff eval")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
