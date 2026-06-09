#!/usr/bin/env python3
"""End-to-end smoke for workflow handoff consumed by failure-triage contract."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from skill_config import JOINT_HANDOFF_CONTRACT, default_spec_profile, load_json_file


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parent
TRIAGE_SKILL = SKILL_ROOT.parent / "hyptest-failure-triage"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate workflow-to-triage handoff contract.")
    parser.add_argument("--json", action="store_true", help="Emit JSON report.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    profile = default_spec_profile()
    log = (
        "ai_arch_trigger_case FAILED\n"
        "assert_site=ai_arch_trigger_breakpoint_cases.c:6021\n"
        "assert_expr=excpt.triggered && excpt.cause == CAUSE_LOAD_PAGE_FAULT\n"
        "excpt.triggered = 0\n"
    )
    handoff = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_DIR / "make_triage_handoff.py"),
            "--log",
            log,
            "--platform",
            "linknan",
            "--spec-profile",
            profile,
            "--json",
        ],
        cwd=str(SKILL_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    failures: list[str] = []
    payload: dict[str, object] = {}
    contract = load_json_file(JOINT_HANDOFF_CONTRACT)
    required_fields = [
        str(field) for field in contract.get("required_shared_fields", [])
    ]
    triage_required_terms = [
        str(term) for term in contract.get("triage_skill_required_terms", [])
    ]
    if handoff.returncode != 0:
        failures.append(handoff.stderr or handoff.stdout)
    else:
        payload = json.loads(handoff.stdout)
        validate = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_DIR / "validate_triage_handoff.py"),
                "--stdin",
            ],
            input=json.dumps(payload, ensure_ascii=False),
            cwd=str(SKILL_ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        if validate.returncode != 0:
            failures.append(validate.stderr or validate.stdout)
        triage_skill = TRIAGE_SKILL / "SKILL.md"
        if not triage_skill.is_file():
            failures.append(f"missing triage skill: {triage_skill}")
        else:
            triage_text = triage_skill.read_text(encoding="utf-8", errors="ignore")
            for field in required_fields:
                if field not in payload:
                    failures.append(f"handoff missing {field}")
            if "runner_context" not in payload:
                failures.append("handoff missing runner_context")
            for term in triage_required_terms:
                if term not in triage_text:
                    failures.append(f"triage skill does not mention {term}")

    report = {
        "ok": not failures,
        "contract": str(JOINT_HANDOFF_CONTRACT),
        "failures": failures,
        "handoff_case": payload.get("case_name") if payload else None,
    }
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(("PASS" if report["ok"] else "FAIL") + " joint handoff eval")
        for failure in failures:
            print(f"  - {failure}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
