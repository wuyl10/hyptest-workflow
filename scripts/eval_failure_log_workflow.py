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
        if not contains_all(payload.get("error_points", []), expected.get("error_terms", [])):
            case_failures.append("missing expected error terms")
        if not contains_any(
            payload.get("reason_code_candidates", []),
            expected.get("reason_code_any", []),
        ):
            case_failures.append("missing expected reason_code candidate")
        if not contains_all(payload.get("next_actions", []), expected.get("next_action_terms", [])):
            case_failures.append("missing expected next-action terms")
        if expected.get("assert_site") and payload.get("assert_site") != expected.get("assert_site"):
            case_failures.append("assert_site mismatch")
        if expected.get("assert_expr") and payload.get("assert_expr") != expected.get("assert_expr"):
            case_failures.append("assert_expr mismatch")
        expected_exception = expected.get("exception_observed", {})
        if isinstance(expected_exception, dict):
            observed = payload.get("exception_observed", {})
            for key, expected_value in expected_exception.items():
                if observed.get(key) != expected_value:
                    case_failures.append(f"exception_observed.{key} mismatch")
        marker_values = expected.get("log_marker_values", {})
        if isinstance(marker_values, dict):
            markers = payload.get("log_markers", {})
            for key, expected_value in marker_values.items():
                if markers.get(key) != expected_value:
                    case_failures.append(f"log_markers.{key} mismatch")
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
