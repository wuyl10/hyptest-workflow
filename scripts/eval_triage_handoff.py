#!/usr/bin/env python3
"""Regression checks for make_triage_handoff.py."""

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


def main() -> int:
    log = (
        "ai_arch_trigger_case FAILED\n"
        "assert_site=ai_arch_trigger.c:12\n"
        "assert_expr=excpt.triggered\n"
        "excpt.triggered = 0\n"
        "excpt.cause = 0xf\n"
    )
    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_DIR / "make_triage_handoff.py"),
            "--log",
            log,
            "--platform",
            "spike",
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        print("FAIL triage handoff eval")
        print(completed.stderr or completed.stdout)
        return 1
    payload = json.loads(completed.stdout)
    failures: list[str] = []
    for key in [
        "case_name",
        "platform",
        "spec_profile",
        "scenario",
        "assert_site",
        "assert_expr",
        "excpt_dump",
        "log_markers",
        "error_points",
        "reason_code_candidates",
        "reason_code_details",
        "next_single_run",
        "waveform_needed",
        "log_paths",
    ]:
        if key not in payload:
            failures.append(f"missing key {key}")
    if payload.get("assert_site") != "ai_arch_trigger.c:12":
        failures.append("assert_site mismatch")
    if payload.get("excpt_dump", {}).get("cause") != "0xf":
        failures.append("excpt cause missing")
    if not payload.get("log_markers", {}).get("has_failed"):
        failures.append("log_markers.has_failed should be true")
    if "D-BLOCK-RUN-UNEXPLAINED" not in payload.get("reason_code_candidates", []):
        failures.append("reason_code candidate missing")
    details = payload.get("reason_code_details", [])
    if not details or details[0].get("default_decision") != "blocked":
        failures.append("reason_code details should include catalog metadata")
    with tempfile.TemporaryDirectory(prefix="hyptest_handoff_eval_", dir=temp_parent()) as tmpdir:
        handoff_path = Path(tmpdir) / "handoff.json"
        handoff_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        schema_check = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_DIR / "validate_triage_handoff.py"),
                "--handoff-json",
                str(handoff_path),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if schema_check.returncode != 0:
            failures.append("validate_triage_handoff should accept generated payload")
    if failures:
        print("FAIL triage handoff eval")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("PASS triage handoff eval")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
