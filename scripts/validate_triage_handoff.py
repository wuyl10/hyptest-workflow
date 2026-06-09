#!/usr/bin/env python3
"""Validate workflow-to-triage handoff JSON against the bundled contract."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from skill_config import TRIAGE_HANDOFF_SCHEMA, load_json_file


PY_TYPES = {
    "array": list,
    "boolean": bool,
    "null": type(None),
    "object": dict,
    "string": str,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate hyptest triage handoff JSON.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--handoff-json", help="Path to handoff JSON file.")
    source.add_argument("--stdin", action="store_true", help="Read handoff JSON from stdin.")
    parser.add_argument("--json", action="store_true", help="Emit JSON report.")
    return parser.parse_args()


def read_payload(args: argparse.Namespace) -> dict[str, Any]:
    raw = sys.stdin.read() if args.stdin else Path(args.handoff_json).expanduser().read_text(encoding="utf-8")
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("handoff payload must be a JSON object")
    return payload


def value_type_ok(value: Any, allowed: list[str]) -> bool:
    return any(isinstance(value, PY_TYPES[name]) for name in allowed if name in PY_TYPES)


def validate_case_names(payload: dict[str, Any], issues: list[str]) -> None:
    case_name = payload.get("case_name")
    case_names = payload.get("case_names")
    if case_names is None:
        return
    if not isinstance(case_names, list):
        return
    seen: set[str] = set()
    normalized: list[str] = []
    for index, item in enumerate(case_names):
        if not isinstance(item, str) or not item.strip():
            issues.append(f"case_names[{index}] must be a non-empty string")
            continue
        stripped = item.strip()
        if stripped in seen:
            issues.append(f"case_names contains duplicate `{stripped}`")
        seen.add(stripped)
        normalized.append(stripped)
    if case_name is not None:
        if not isinstance(case_name, str) or not case_name.strip():
            issues.append("case_name must be a non-empty string or null")
        elif case_names:
            stripped_case = case_name.strip()
            if normalized and normalized[0] != stripped_case:
                issues.append("case_name must match case_names[0]")
            if stripped_case not in seen:
                issues.append("case_name must be included in case_names")


def validate(payload: dict[str, Any]) -> dict[str, object]:
    schema = load_json_file(TRIAGE_HANDOFF_SCHEMA)
    required = [str(item) for item in schema.get("required_fields", [])]
    field_types = schema.get("field_types", {})
    issues: list[str] = []

    for field in required:
        if field not in payload:
            issues.append(f"missing field `{field}`")

    if isinstance(field_types, dict):
        for field, allowed_raw in field_types.items():
            if field not in payload:
                continue
            allowed = [str(item) for item in allowed_raw] if isinstance(allowed_raw, list) else []
            if allowed and not value_type_ok(payload[field], allowed):
                issues.append(f"field `{field}` has invalid type; expected one of {', '.join(allowed)}")

    validate_case_names(payload, issues)

    runner_context = payload.get("runner_context")
    if runner_context is not None:
        if not isinstance(runner_context, dict):
            issues.append("field `runner_context` must be object")
        else:
            bool_fields = [
                str(field)
                for field in schema.get("runner_context_boolean_fields", [])
            ]
            for field in bool_fields:
                if field not in runner_context:
                    issues.append(f"runner_context.{field} is required")
                elif not isinstance(runner_context[field], bool):
                    issues.append(f"runner_context.{field} must be boolean")
            official_spike = bool(runner_context.get("official_spike"))
            linknan_platform = bool(runner_context.get("linknan_platform"))
            linknan_difftest = bool(runner_context.get("linknan_difftest"))
            difftest_disabled = bool(runner_context.get("difftest_disabled"))
            runner_conflict = bool(runner_context.get("runner_conflict"))
            runner_ambiguous = bool(runner_context.get("runner_ambiguous"))
            linknan_no_diff = bool(runner_context.get("linknan_no_diff"))
            if runner_conflict != (official_spike and linknan_platform):
                issues.append("runner_context.runner_conflict must equal official_spike && linknan_platform")
            if runner_ambiguous != (not (official_spike or linknan_platform or linknan_difftest)):
                issues.append("runner_context.runner_ambiguous must reflect no runner evidence")
            if linknan_no_diff and not (linknan_platform and difftest_disabled and not linknan_difftest):
                issues.append(
                    "runner_context.linknan_no_diff implies linknan_platform && difftest_disabled && !linknan_difftest"
                )

    log_markers = payload.get("log_markers")
    if log_markers is not None:
        if not isinstance(log_markers, dict):
            issues.append("field `log_markers` must be object")
        else:
            bool_fields = [
                str(field)
                for field in schema.get("log_marker_boolean_fields", [])
            ]
            for field in bool_fields:
                if field not in log_markers:
                    issues.append(f"log_markers.{field} is required")
                elif not isinstance(log_markers[field], bool):
                    issues.append(f"log_markers.{field} must be boolean")

    runner_request = payload.get("runner_request")
    if runner_request is not None:
        if not isinstance(runner_request, dict):
            issues.append("field `runner_request` must be object or null")
        else:
            allowed_runner_modes = {"spike-gate", "linknan-difftest", "linknan-no-diff"}
            allowed_platforms = {"spike", "linknan"}
            allowed_difftest_modes = {"not-applicable", "enabled", "disabled"}
            mode = runner_request.get("runner_mode")
            compile_plat = runner_request.get("compile_plat")
            run_platform = runner_request.get("run_platform")
            difftest_mode = runner_request.get("difftest_mode")
            if mode not in allowed_runner_modes:
                issues.append("runner_request.runner_mode must be spike-gate|linknan-difftest|linknan-no-diff")
            if compile_plat not in allowed_platforms:
                issues.append("runner_request.compile_plat must be spike|linknan")
            if run_platform not in allowed_platforms:
                issues.append("runner_request.run_platform must be spike|linknan")
            if difftest_mode not in allowed_difftest_modes:
                issues.append("runner_request.difftest_mode must be not-applicable|enabled|disabled")
            if not isinstance(runner_request.get("include_commented"), bool):
                issues.append("runner_request.include_commented must be boolean")
            if not isinstance(runner_request.get("cleanup_allowed"), bool):
                issues.append("runner_request.cleanup_allowed must be boolean")
            if mode == "spike-gate" and (
                compile_plat != "spike"
                or run_platform != "spike"
                or difftest_mode != "not-applicable"
            ):
                issues.append("spike-gate runner_request must use spike/spike/not-applicable")
            if mode == "linknan-difftest" and (
                compile_plat != "linknan"
                or run_platform != "linknan"
                or difftest_mode != "enabled"
            ):
                issues.append("linknan-difftest runner_request must use linknan/linknan/enabled")
            if mode == "linknan-no-diff" and (
                compile_plat != "linknan"
                or run_platform != "linknan"
                or difftest_mode != "disabled"
            ):
                issues.append("linknan-no-diff runner_request must use linknan/linknan/disabled")

    return {
        "ok": not issues,
        "schema": str(TRIAGE_HANDOFF_SCHEMA),
        "issues": issues,
    }


def main() -> int:
    args = parse_args()
    try:
        payload = read_payload(args)
        report = validate(payload)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        report = {"ok": False, "schema": str(TRIAGE_HANDOFF_SCHEMA), "issues": [str(exc)]}

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(("PASS" if report["ok"] else "FAIL") + " triage handoff schema")
        for issue in report["issues"]:
            print(f"  - {issue}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
