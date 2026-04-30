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
