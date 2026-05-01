#!/usr/bin/env python3
"""Smoke-test case_workflow_ledger.py."""

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


def write(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def main() -> int:
    failures: list[str] = []
    with tempfile.TemporaryDirectory(prefix="hyptest_ledger_", dir=temp_parent()) as tmpdir:
        tmp = Path(tmpdir)
        case = "ai_arch_ledger_smoke_case"
        preflight = {
            "case_name": case,
            "repo_root": str(tmp / "repo"),
            "test_point_file": str(tmp / "test_point.md"),
            "platform": "spike",
            "spec_profile": "nhv5_1_ap",
            "ok": True,
            "cache": {"hit": True},
            "commands": {
                "similar_cases": {"payload": {"cache": {"hit": True}}},
                "repo_evidence_index": {"payload": {"cache": {"hit": False}}},
            },
            "timing": {"total_seconds": 1.0, "by_step": {"similar_cases": 0.7}},
        }
        postcheck = {
            "repo_root": str(tmp / "repo"),
            "test_point_file": str(tmp / "test_point.md"),
            "platform": "spike",
            "spec_profile": "nhv5_1_ap",
            "ok": True,
            "cases": [
                {
                    "case": case,
                    "definition_unique": True,
                    "register_status": "enabled",
                    "artifacts": {"elf": "case.ELF"},
                    "test_point_mentions": [{"line": 1, "text": case}],
                }
            ],
            "commands": {"writeback_check": {"ok": True}},
            "timing": {"total_seconds": 0.2, "by_step": {"writeback_check": 0.1}},
        }
        gate = {
            "case": case,
            "repo_root": str(tmp / "repo"),
            "test_point_file": str(tmp / "test_point.md"),
            "platform": "spike",
            "spec_profile": "nhv5_1_ap",
            "ok": True,
            "commands": {
                "compile": {"ok": True},
                "run": {"ok": True},
                "postcheck": {"ok": True, "payload": postcheck},
            },
            "evidence_requirements": {"ok": True, "requirements": {"artifact_elf": True, "latest_log": True}},
            "timing": {"total_seconds": 0.5, "by_step": {"compile": 0.1, "run": 0.2, "postcheck": 0.2}},
        }
        preflight_path = tmp / "preflight.json"
        gate_path = tmp / "gate.json"
        write(preflight_path, preflight)
        write(gate_path, gate)
        completed = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_DIR / "case_workflow_ledger.py"),
                "--case",
                case,
                "--preflight-json",
                str(preflight_path),
                "--gate-json",
                str(gate_path),
                "--manual-edit-seconds",
                "2.5",
                "--json",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            failures.append(f"case_workflow_ledger returned {completed.returncode}: {completed.stderr or completed.stdout}")
            payload = {}
        else:
            try:
                payload = json.loads(completed.stdout)
            except json.JSONDecodeError as exc:
                failures.append(f"case_workflow_ledger did not emit JSON: {exc}")
                payload = {}
        if payload:
            if payload.get("case") != case:
                failures.append("ledger did not preserve case name")
            if payload.get("cache", {}).get("preflight_pack", {}).get("hit") is not True:
                failures.append("ledger missing preflight cache signal")
            if payload.get("rework_signals"):
                failures.append("ledger should have no rework signals for clean fixture")
            total = payload.get("timing", {}).get("total_observed_seconds")
            if total is None or total < 4.0:
                failures.append("ledger total should include preflight, gate, postcheck and manual edit time")
            if not any(step.get("name") == "manual_edit" for step in payload.get("timing", {}).get("steps", [])):
                failures.append("ledger should include manual_edit step")

    if failures:
        print("FAIL case workflow ledger eval")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("PASS case workflow ledger eval")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
