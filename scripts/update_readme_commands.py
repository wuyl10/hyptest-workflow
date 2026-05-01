#!/usr/bin/env python3
"""Refresh the generated command section in references/command_index.md."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parent
COMMAND_INDEX = SKILL_ROOT / "references" / "command_index.md"
BEGIN = "<!-- BEGIN GENERATED COMMANDS -->"
END = "<!-- END GENERATED COMMANDS -->"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Refresh README generated command block.")
    return parser.parse_args()


def main() -> int:
    parse_args()
    text = COMMAND_INDEX.read_text(encoding="utf-8")
    if BEGIN not in text or END not in text:
        print(f"references/command_index.md missing {BEGIN}/{END} markers", file=sys.stderr)
        return 2
    completed = subprocess.run(
        [sys.executable, str(SCRIPT_DIR / "list_skill_commands.py"), "--markdown"],
        cwd=str(SKILL_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        print(completed.stderr or completed.stdout, file=sys.stderr)
        return completed.returncode
    generated = completed.stdout.rstrip() + "\n"
    before, rest = text.split(BEGIN, 1)
    _old, after = rest.split(END, 1)
    COMMAND_INDEX.write_text(f"{before}{BEGIN}\n{generated}{END}{after}", encoding="utf-8")
    print("PASS update command index")
    return 0


if __name__ == "__main__":
    sys.exit(main())
