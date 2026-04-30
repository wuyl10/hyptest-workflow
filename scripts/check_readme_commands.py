#!/usr/bin/env python3
"""Check that README generated command block matches list_skill_commands.py."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parent
README = SKILL_ROOT / "README.md"
BEGIN = "<!-- BEGIN GENERATED COMMANDS -->"
END = "<!-- END GENERATED COMMANDS -->"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check README generated command block.")
    return parser.parse_args()


def main() -> int:
    parse_args()
    text = README.read_text(encoding="utf-8")
    if BEGIN not in text or END not in text:
        print("FAIL README command block markers missing")
        return 1
    completed = subprocess.run(
        [sys.executable, str(SCRIPT_DIR / "list_skill_commands.py"), "--markdown"],
        cwd=str(SKILL_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        print(completed.stderr or completed.stdout)
        return completed.returncode
    generated = completed.stdout.rstrip() + "\n"
    _before, rest = text.split(BEGIN, 1)
    current, _after = rest.split(END, 1)
    current = current.lstrip("\n").rstrip() + "\n"
    if current != generated:
        print("FAIL README generated command block is stale; run scripts/update_readme_commands.py")
        return 1
    print("PASS README commands")
    return 0


if __name__ == "__main__":
    sys.exit(main())
