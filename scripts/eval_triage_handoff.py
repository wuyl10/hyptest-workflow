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
    partial_runner = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_DIR / "make_triage_handoff.py"),
            "--log",
            "ai_arch_pma_partial_runner_corner FAILED\n",
            "--include-commented",
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    early_failures: list[str] = []
    if partial_runner.returncode == 0:
        early_failures.append("partial runner args should require --runner-mode")
    if "require explicit --runner-mode" not in partial_runner.stderr:
        early_failures.append("partial runner args should explain missing --runner-mode")
    invalid_runner = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_DIR / "make_triage_handoff.py"),
            "--log",
            "ai_arch_pma_invalid_runner_corner DIFFTEST FAILED\n",
            "--runner-mode",
            "linknan-difftest",
            "--difftest-mode",
            "disabled",
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if invalid_runner.returncode == 0:
        early_failures.append("invalid runner combo should fail at generation time")
    if "linknan-difftest runner_request must use linknan/linknan/enabled" not in invalid_runner.stderr:
        early_failures.append("invalid runner combo should explain expected linknan-difftest mode")
    if early_failures:
        print("FAIL triage handoff eval")
        for failure in early_failures:
            print(f"  - {failure}")
        return 1

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
            "--waveform-path",
            "/tmp/example.fsdb",
            "--rtl-root",
            "$HYPTEST_LINKNAN_HOME/dependencies/nanhu/src/main",
            "--top-module",
            "SimTop",
            "--debug-target",
            "confirm exception request/response first-bad-cycle",
            "--runner-mode",
            "linknan-difftest",
            "--include-commented",
            "--runner-purpose",
            "reproduce PMA difftest mismatch",
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
        "case_names",
        "platform",
        "spec_profile",
        "scenario",
        "assert_site",
        "assert_expr",
        "excpt_dump",
        "log_markers",
        "runner_context",
        "error_points",
        "reason_code_candidates",
        "reason_code_details",
        "next_single_run",
        "runner_request",
        "waveform_needed",
        "waveform_context",
        "log_paths",
    ]:
        if key not in payload:
            failures.append(f"missing key {key}")
    if payload.get("assert_site") != "ai_arch_trigger.c:12":
        failures.append("assert_site mismatch")
    if payload.get("case_names") != ["ai_arch_trigger_case"]:
        failures.append("case_names mismatch")
    if payload.get("excpt_dump", {}).get("cause") != "0xf":
        failures.append("excpt cause missing")
    if not payload.get("log_markers", {}).get("has_failed"):
        failures.append("log_markers.has_failed should be true")
    for key in [
        "has_difftest_failed",
        "has_mismatch",
        "has_ref_dut_delta",
        "has_selfcheck_failed",
    ]:
        if key not in payload.get("log_markers", {}):
            failures.append(f"log_markers.{key} missing")
    runner_context = payload.get("runner_context", {})
    if not isinstance(runner_context, dict):
        failures.append("runner_context should be an object")
    else:
        for key in [
            "official_spike",
            "linknan_platform",
            "linknan_difftest",
            "difftest_disabled",
            "linknan_no_diff",
            "difftest_mode_conflict",
            "multi_run",
            "runner_conflict",
            "runner_ambiguous",
        ]:
            if key not in runner_context:
                failures.append(f"runner_context.{key} missing")
    if "D-BLOCK-RUN-UNEXPLAINED" not in payload.get("reason_code_candidates", []):
        failures.append("reason_code candidate missing")
    details = payload.get("reason_code_details", [])
    if not details or details[0].get("default_decision") != "blocked":
        failures.append("reason_code details should include catalog metadata")
    if payload.get("waveform_needed") is not True:
        failures.append("waveform_needed should be true when waveform context is provided")
    runner_request = payload.get("runner_request", {})
    if not isinstance(runner_request, dict):
        failures.append("runner_request should be an object when runner mode is provided")
    else:
        expected_runner = {
            "runner_mode": "linknan-difftest",
            "compile_plat": "linknan",
            "run_platform": "linknan",
            "difftest_mode": "enabled",
        }
        for key, expected in expected_runner.items():
            if runner_request.get(key) != expected:
                failures.append(f"runner_request.{key} mismatch")
        if runner_request.get("include_commented") is not True:
            failures.append("runner_request.include_commented should be true")
    waveform_context = payload.get("waveform_context", {})
    if not isinstance(waveform_context, dict):
        failures.append("waveform_context should be an object")
    elif waveform_context.get("debug_target") != "confirm exception request/response first-bad-cycle":
        failures.append("waveform_context.debug_target mismatch")
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
        invalid_payloads = [
            (
                "case_names_non_string",
                {**payload, "case_names": ["ai_arch_trigger_case", 7]},
                "case_names[1] must be a non-empty string",
            ),
            (
                "case_names_duplicate",
                {**payload, "case_names": ["ai_arch_trigger_case", "ai_arch_trigger_case"]},
                "case_names contains duplicate",
            ),
            (
                "case_name_not_first",
                {
                    **payload,
                    "case_name": "ai_arch_trigger_case",
                    "case_names": ["ai_other_case", "ai_arch_trigger_case"],
                },
                "case_name must match case_names[0]",
            ),
            (
                "case_name_missing_from_case_names",
                {**payload, "case_name": "ai_arch_trigger_case", "case_names": ["ai_other_case"]},
                "case_name must be included in case_names",
            ),
        ]
        for name, invalid_payload, expected_issue in invalid_payloads:
            invalid_path = Path(tmpdir) / f"{name}.json"
            invalid_path.write_text(json.dumps(invalid_payload, ensure_ascii=False), encoding="utf-8")
            invalid_check = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_DIR / "validate_triage_handoff.py"),
                    "--handoff-json",
                    str(invalid_path),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            if invalid_check.returncode == 0:
                failures.append(f"{name} should fail schema validation")
            if expected_issue not in invalid_check.stdout:
                failures.append(f"{name} should explain {expected_issue}")
    if failures:
        print("FAIL triage handoff eval")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("PASS triage handoff eval")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
