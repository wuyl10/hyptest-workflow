#!/usr/bin/env python3
"""Check listed script commands point to scripts that expose --help."""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
from pathlib import Path

from list_skill_commands import COMMAND_GROUPS


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate listed command script help availability.")
    parser.add_argument("--json", action="store_true", help="Emit JSON report.")
    return parser.parse_args()


def extract_script(cmd: str) -> str | None:
    try:
        parts = shlex.split(cmd)
    except ValueError:
        return None
    for index, part in enumerate(parts):
        if part == "python3" and index + 1 < len(parts):
            script = parts[index + 1]
            if script.startswith("scripts/") and script.endswith(".py"):
                return script
    return None


def main() -> int:
    args = parse_args()
    failures: list[str] = []
    results: list[dict[str, object]] = []
    seen: set[str] = set()

    for group in COMMAND_GROUPS:
        for item in group.get("commands", []):
            name = str(item.get("name", "unnamed"))
            script = extract_script(str(item.get("cmd", "")))
            if not script or script in seen:
                continue
            seen.add(script)
            path = SKILL_ROOT / script
            if not path.is_file():
                failures.append(f"{name}: listed script missing: {script}")
                results.append({"name": name, "script": script, "ok": False})
                continue
            completed = subprocess.run(
                [sys.executable, str(path), "--help"],
                cwd=str(SKILL_ROOT),
                capture_output=True,
                text=True,
                check=False,
            )
            ok = completed.returncode == 0 and "usage:" in completed.stdout.lower()
            if not ok:
                failures.append(f"{name}: {script} --help failed rc={completed.returncode}")
            results.append({"name": name, "script": script, "ok": ok})

    report = {
        "ok": not failures,
        "checked_count": len(results),
        "failures": failures,
        "results": results,
    }
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(("PASS" if report["ok"] else "FAIL") + " listed commands help eval")
        for failure in failures:
            print(f"  - {failure}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
