#!/usr/bin/env python3
"""Check that generic skill surfaces stay portable across spec profiles."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from skill_config import default_spec_profile, recommended_checks


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate spec profile portability guards.")
    return parser.parse_args()


def run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=str(SKILL_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )


def main() -> int:
    parse_args()
    profile = default_spec_profile()
    failures: list[str] = []

    generic_commands = "\n".join(recommended_checks())
    if profile in generic_commands:
        failures.append("recommended_checks() should omit the concrete default profile")

    resolved_commands = "\n".join(recommended_checks(show_resolved_profile=True))
    if profile not in resolved_commands:
        failures.append("recommended_checks(show_resolved_profile=True) should include the registry default")

    summary = run([sys.executable, "scripts/skill_summary.py", "--json"])
    if summary.returncode != 0:
        failures.append(summary.stderr or summary.stdout)
    else:
        payload = json.loads(summary.stdout)
        if profile in "\n".join(payload.get("recommended_checks", [])):
            failures.append("skill_summary default recommended checks should be profile-generic")

    resolved_summary = run(
        [sys.executable, "scripts/skill_summary.py", "--show-resolved-profile", "--json"]
    )
    if resolved_summary.returncode != 0:
        failures.append(resolved_summary.stderr or resolved_summary.stdout)
    else:
        payload = json.loads(resolved_summary.stdout)
        if profile not in "\n".join(payload.get("recommended_checks", [])):
            failures.append("skill_summary --show-resolved-profile should include registry default")

    registry = run(
        [
            sys.executable,
            "scripts/check_spec_profile_registry.py",
            "--policy",
            "generic-docs",
            "--json",
        ]
    )
    if registry.returncode != 0:
        failures.append("generic-docs profile policy should pass: " + (registry.stdout or registry.stderr))

    command_list = run([sys.executable, "scripts/list_skill_commands.py", "--markdown"])
    if command_list.returncode != 0:
        failures.append(command_list.stderr or command_list.stdout)
    elif profile in command_list.stdout:
        failures.append("list_skill_commands.py --markdown should use <spec_profile>, not concrete default")

    if failures:
        print("FAIL profile portability eval")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("PASS profile portability eval")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
