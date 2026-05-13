#!/usr/bin/env python3
"""Regression checks for query_spec_profile.py --nongate-summary."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent


def run_query(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT_DIR / "query_spec_profile.py"), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def main() -> int:
    failures: list[str] = []

    # 1. --nongate-summary --json emits ok=true and a nongate block.
    result = run_query("--spec-profile", "nhv5_1_ap", "--nongate-summary", "--json")
    if result.returncode != 0:
        failures.append(f"--nongate-summary --json should exit 0, got {result.returncode}")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        failures.append(f"--nongate-summary --json output is not valid JSON: {exc}")
        payload = {}
    if not payload.get("ok"):
        failures.append("--nongate-summary --json payload should have ok=true")
    nongate = payload.get("nongate", {})
    if not isinstance(nongate, dict):
        failures.append("--nongate-summary --json payload should contain a nongate block")
    else:
        if nongate.get("keyword_category_count", 0) <= 0:
            failures.append("nongate keyword_category_count should be > 0 for nhv5_1_ap")
        if nongate.get("nongate_pma_match_count", -1) < 0:
            failures.append("nongate_pma_match_count should be a non-negative integer")

    # 2. --match-module memblock should narrow categories without removing all.
    result = run_query(
        "--spec-profile", "nhv5_1_ap",
        "--nongate-summary", "--match-module", "memblock", "--json",
    )
    try:
        payload = json.loads(result.stdout)
        narrowed = payload.get("nongate", {}).get("keyword_category_count", 0)
    except json.JSONDecodeError:
        narrowed = 0
        failures.append("--match-module memblock output is not valid JSON")
    if narrowed <= 0:
        failures.append("--match-module memblock should still match at least one nongate category")

    # 3. --match-module with garbage should return 0 categories but still succeed.
    result = run_query(
        "--spec-profile", "nhv5_1_ap",
        "--nongate-summary", "--match-module", "totallyNotAModuleName", "--json",
    )
    try:
        payload = json.loads(result.stdout)
        zero_hit = payload.get("nongate", {}).get("keyword_category_count", -1)
    except json.JSONDecodeError:
        zero_hit = -1
        failures.append("--match-module garbage output is not valid JSON")
    if zero_hit != 0:
        failures.append(
            f"--match-module garbage should produce keyword_category_count=0, got {zero_hit}"
        )

    # 4. Text mode (no --json) should also succeed and print the summary header.
    result = run_query("--spec-profile", "nhv5_1_ap", "--nongate-summary")
    if result.returncode != 0:
        failures.append("--nongate-summary text mode should exit 0")
    if "nongate" not in result.stdout.lower():
        failures.append("--nongate-summary text mode should include the word `nongate`")

    if failures:
        print("FAIL query_spec_profile --nongate-summary eval")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("PASS query_spec_profile --nongate-summary eval")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
