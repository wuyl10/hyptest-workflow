#!/usr/bin/env python3
"""Evaluate symptom text to reason_code suggestion coverage."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parent
FIXTURE = SKILL_ROOT / "assets/evals/reason_code_suggestion_eval.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate suggest_reason_code.py fixtures.")
    parser.add_argument("--fixture", default=str(FIXTURE), help="Fixture JSON path.")
    parser.add_argument("--json", action="store_true", help="Emit JSON report.")
    return parser.parse_args()


def suggest(symptom: str) -> dict[str, object]:
    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_DIR / "suggest_reason_code.py"),
            "--symptom",
            symptom,
            "--json",
        ],
        cwd=str(SKILL_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr or completed.stdout)
    payload = json.loads(completed.stdout)
    if not isinstance(payload, dict):
        raise RuntimeError("suggest_reason_code.py did not emit a JSON object")
    return payload


def main() -> int:
    args = parse_args()
    fixture = Path(args.fixture).expanduser().resolve()
    cases = json.loads(fixture.read_text(encoding="utf-8"))
    failures: list[str] = []
    results: list[dict[str, object]] = []

    for item in cases:
        case_id = str(item.get("id", "unnamed"))
        try:
            payload = suggest(str(item["symptom"]))
        except (KeyError, RuntimeError, json.JSONDecodeError) as exc:
            failures.append(f"{case_id}: {exc}")
            continue
        suggestions = payload.get("suggestions", [])
        codes = [
            str(row.get("code"))
            for row in suggestions
            if isinstance(row, dict) and row.get("code")
        ]
        case_failures: list[str] = []
        expected_top = str(item.get("expected_top_code", ""))
        if expected_top and (not codes or codes[0] != expected_top):
            case_failures.append(f"top expected {expected_top}, got {codes[0] if codes else '-'}")
        for expected in item.get("expected_codes", []):
            if str(expected) not in codes:
                case_failures.append(f"missing expected code {expected}")
        warning_codes = [
            str(row.get("code"))
            for row in payload.get("warnings", [])
            if isinstance(row, dict) and row.get("code")
        ]
        for expected in item.get("expected_warnings", []):
            if str(expected) not in warning_codes:
                case_failures.append(f"missing expected warning {expected}")
        for forbidden in item.get("forbidden_warnings", []):
            if str(forbidden) in warning_codes:
                case_failures.append(f"forbidden warning present {forbidden}")
        warning_text = " ".join(
            str(row.get("message", ""))
            for row in payload.get("warnings", [])
            if isinstance(row, dict)
        )
        for expected_text in item.get("expected_warning_text", []):
            if str(expected_text) not in warning_text:
                case_failures.append(f"missing expected warning text {expected_text}")
        if case_failures:
            failures.append(f"{case_id}: {', '.join(case_failures)}")
        results.append({"id": case_id, "ok": not case_failures, "codes": codes, "warnings": warning_codes})

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
        print(("PASS" if report["ok"] else "FAIL") + " reason_code suggestion eval")
        for failure in failures:
            print(f"  - {failure}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
