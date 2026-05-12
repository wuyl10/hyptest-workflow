#!/usr/bin/env python3
"""Smoke-test case_timing_summary.py contract."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parent


def temp_parent() -> Path:
    path = SKILL_ROOT / ".hyptest_workflow_skill" / "tmp" / "eval"
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True, check=False)


def main() -> int:
    failures: list[str] = []
    with tempfile.TemporaryDirectory(prefix="hyptest_timing_summary_", dir=temp_parent()) as tmpdir:
        tmp = Path(tmpdir)
        write_json(
            tmp / "case_preflight.json",
            {
                "target_test_point_excerpt": "x",
                "cache": {"hit": True},
                "timing": {
                    "total_seconds": 1.2,
                    "by_step": {"similar_cases": 0.8, "platform_env": 0.1},
                },
            },
        )
        write_json(
            tmp / "case_gate.json",
            {
                "case": "ai_arch_timing_case",
                "platform": "spike",
                "evidence_requirements": {"ok": True},
                "timing": {
                    "total_seconds": 3.4,
                    "by_step": {"compile": 1.0, "run": 2.0, "postcheck": 0.4},
                },
            },
        )
        write_json(
            tmp / "submission_card.json",
            {
                "preflight": {"cache": {"hit": False}},
                "gate": {},
                "timing": {"total_seconds": 0.2, "by_step": {}},
            },
        )
        completed = run(
            [
                sys.executable,
                str(SCRIPT_DIR / "case_timing_summary.py"),
                "--reports",
                str(tmp / "*.json"),
                "--json",
            ]
        )
        if completed.returncode != 0:
            failures.append(completed.stderr.strip() or completed.stdout.strip())
        else:
            payload = json.loads(completed.stdout)
            if payload.get("report_count") != 3:
                failures.append("timing summary should read all report JSON files")
            timing = payload.get("timing", {})
            if "case_gate.run" not in timing:
                failures.append("timing summary missing case_gate.run")
            if timing.get("case_preflight.similar_cases", {}).get("avg") != 0.8:
                failures.append("timing summary wrong average for preflight similar_cases")
            cache = payload.get("cache", {})
            if cache.get("seen") != 2 or cache.get("hit") != 1 or cache.get("miss") != 1:
                failures.append("timing summary cache counters are wrong")
            slowest = payload.get("slowest_reports", [])
            if not slowest or slowest[0].get("kind") != "case_gate":
                failures.append("timing summary should rank slowest reports")

    if failures:
        print("FAIL case timing summary eval")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("PASS case timing summary eval")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
