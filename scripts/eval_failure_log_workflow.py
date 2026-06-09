#!/usr/bin/env python3
"""Evaluate failure-log classification fixtures for workflow triage."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
FIXTURE = SCRIPT_DIR.parent / "assets/evals/failure_log_workflow_eval.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate failure-log workflow fixtures.")
    parser.add_argument("--fixture", default=str(FIXTURE), help="Fixture JSON path.")
    parser.add_argument("--json", action="store_true", help="Emit JSON report.")
    return parser.parse_args()


def contains_all(haystack: object, needles: list[str]) -> bool:
    text = json.dumps(haystack, ensure_ascii=False).lower()
    return all(needle.lower() in text for needle in needles)


def contains_any(haystack: object, needles: list[str]) -> bool:
    text = json.dumps(haystack, ensure_ascii=False).lower()
    return any(needle.lower() in text for needle in needles)


def contains_none(haystack: object, needles: list[str]) -> bool:
    text = json.dumps(haystack, ensure_ascii=False).lower()
    return all(needle.lower() not in text for needle in needles)


def check_expected_values(
    actual: object,
    expected: object,
    *,
    label: str,
    failures: list[str],
) -> None:
    if not isinstance(expected, dict):
        return
    if not isinstance(actual, dict):
        failures.append(f"{label} should be an object")
        return
    for key, expected_value in expected.items():
        if actual.get(key) != expected_value:
            failures.append(f"{label}.{key} mismatch")


def main() -> int:
    args = parse_args()
    fixture = Path(args.fixture).expanduser().resolve()
    cases = json.loads(fixture.read_text(encoding="utf-8"))
    failures: list[str] = []
    results: list[dict[str, object]] = []

    for item in cases:
        completed = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_DIR / "classify_failure_log.py"),
                "--log",
                item["log"],
                "--json",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            failures.append(f"{item['id']}: classifier failed: {completed.stderr or completed.stdout}")
            continue
        payload = json.loads(completed.stdout)
        expected = item["expected"]
        case_failures: list[str] = []
        if not contains_all(payload.get("scenario", []), expected.get("scenario_terms", [])):
            case_failures.append("missing expected scenario terms")
        if not contains_none(payload.get("scenario", []), expected.get("forbidden_scenario_terms", [])):
            case_failures.append("forbidden scenario terms present")
        if not contains_all(payload.get("error_points", []), expected.get("error_terms", [])):
            case_failures.append("missing expected error terms")
        reason_code_any = expected.get("reason_code_any", [])
        if reason_code_any and not contains_any(
            payload.get("reason_code_candidates", []),
            reason_code_any,
        ):
            case_failures.append("missing expected reason_code candidate")
        if not contains_all(
            payload.get("reason_code_candidates", []),
            expected.get("reason_code_all", []),
        ):
            case_failures.append("missing required reason_code candidate")
        if not contains_all(payload.get("next_actions", []), expected.get("next_action_terms", [])):
            case_failures.append("missing expected next-action terms")
        if not contains_all(payload.get("runner_context", {}), expected.get("runner_context_terms", [])):
            case_failures.append("missing expected runner-context terms")
        if not contains_none(payload.get("runner_context", {}), expected.get("forbidden_runner_context_terms", [])):
            case_failures.append("forbidden runner-context terms present")
        check_expected_values(
            payload.get("runner_context", {}),
            expected.get("runner_context_values", {}),
            label="runner_context",
            failures=case_failures,
        )
        if not contains_none(payload.get("reason_code_candidates", []), expected.get("forbidden_reason_codes", [])):
            case_failures.append("forbidden reason_code candidate present")
        if not contains_none(payload.get("error_points", []), expected.get("forbidden_error_terms", [])):
            case_failures.append("forbidden error terms present")
        if expected.get("assert_site") and payload.get("assert_site") != expected.get("assert_site"):
            case_failures.append("assert_site mismatch")
        if expected.get("assert_expr") and payload.get("assert_expr") != expected.get("assert_expr"):
            case_failures.append("assert_expr mismatch")
        if expected.get("case_name") and payload.get("case_name") != expected.get("case_name"):
            case_failures.append("case_name mismatch")
        if not contains_all(payload.get("case_names", []), expected.get("case_names", [])):
            case_failures.append("missing expected case_names")
        if expected.get("case_name_count") is not None and len(payload.get("case_names", [])) != expected.get("case_name_count"):
            case_failures.append("case_name_count mismatch")
        if expected.get("spec_profile") and payload.get("spec_profile") != expected.get("spec_profile"):
            case_failures.append("spec_profile mismatch")
        expected_exception = expected.get("exception_observed", {})
        if isinstance(expected_exception, dict):
            observed = payload.get("exception_observed", {})
            for key, expected_value in expected_exception.items():
                if observed.get(key) != expected_value:
                    case_failures.append(f"exception_observed.{key} mismatch")
        check_expected_values(
            payload.get("log_markers", {}),
            expected.get("log_marker_values", {}),
            label="log_markers",
            failures=case_failures,
        )
        if case_failures:
            failures.append(f"{item['id']}: {', '.join(case_failures)}")
        results.append({"id": item["id"], "ok": not case_failures, "payload": payload})

    report = {
        "ok": not failures,
        "fixture": str(fixture),
        "case_count": len(cases),
        "failures": failures,
        "results": results,
    }
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(("PASS" if report["ok"] else "FAIL") + " failure log workflow eval")
        for failure in failures:
            print(f"  - {failure}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
