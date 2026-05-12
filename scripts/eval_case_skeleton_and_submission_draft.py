#!/usr/bin/env python3
"""Smoke-test make_case_skeleton.py and submission-card final draft output."""

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


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def run_json(command: list[str], failures: list[str], label: str, *, expect_rc: int = 0) -> dict[str, object]:
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != expect_rc:
        failures.append(f"{label} returned {completed.returncode}, expected {expect_rc}: {completed.stderr or completed.stdout}")
        return {}
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        failures.append(f"{label} did not emit JSON: {exc}")
        return {}


def main() -> int:
    failures: list[str] = []
    with tempfile.TemporaryDirectory(prefix="hyptest_skeleton_draft_", dir=temp_parent()) as tmpdir:
        tmp = Path(tmpdir)
        case = "ai_arch_skeleton_smoke_case"
        preflight = {
            "case_name": case,
            "spec_profile": "nhv5_1_ap",
            "test_point_file": str(tmp / "test_point.md"),
            "target_test_point_excerpt": "page fault tval cause check",
            "commands": {
                "similar_cases": {
                    "payload": {
                        "focus_terms": ["page", "fault", "tval"],
                        "top_results": [
                            {
                                "case_name": "ai_arch_reference_case",
                                "file": "ai_test_cases/ref.c",
                                "line": 12,
                                "register_status": "enabled",
                            }
                        ],
                    }
                }
            },
        }
        preflight_path = tmp / "preflight.json"
        write(preflight_path, json.dumps(preflight))
        skeleton_payload = run_json(
            [
                sys.executable,
                str(SCRIPT_DIR / "make_case_skeleton.py"),
                "--case",
                case,
                "--preflight-json",
                str(preflight_path),
                "--test-point-id",
                "P1A",
                "--json",
            ],
            failures,
            "make_case_skeleton",
        )
        if skeleton_payload:
            skeleton = skeleton_payload.get("skeleton", "")
            if f"bool {case}()" not in skeleton:
                failures.append("skeleton missing case function")
            if "TEST_SETUP_EXCEPT();" not in skeleton:
                failures.append("skeleton should infer TEST_SETUP_EXCEPT for exception-like preflight")
            if 'TEST_ASSERT("TODO: observable behavior", false);' not in skeleton:
                failures.append("skeleton should keep an intentionally failing TODO assertion")
            if "decision_note" not in skeleton_payload:
                failures.append("skeleton payload should include decision boundary")

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
                    "definitions": [{"path": "ai_test_cases/skeleton.c", "line": 1}],
                    "register_status": "enabled",
                    "artifacts": {"elf": f"case_elf_asm/spike/{case}.ELF", "asm": f"case_elf_asm/spike/{case}.asm"},
                    "latest_logs": [{"path": f".tmp/result_log/spike/{case}.log", "summary": {"has_pass": True}}],
                    "test_point_mentions": [{"line": 10, "text": f"- `{case}`（default，已启用）"}],
                }
            ],
        }
        gate = {
            "case": case,
            "repo_root": str(tmp / "repo"),
            "test_point_file": str(tmp / "test_point.md"),
            "platform": "spike",
            "spec_profile": "nhv5_1_ap",
            "ok": True,
            "commands": {
                "compile": {"ok": True, "returncode": 0, "command": "compile", "duration_seconds": 0.1},
                "run": {"ok": True, "returncode": 0, "command": "run", "duration_seconds": 0.2},
                "postcheck": {"ok": True, "payload": postcheck},
            },
            "skipped": {},
            "evidence_requirements": {"ok": True, "requirements": {"artifact_elf": True, "latest_log": True}},
        }
        gate_path = tmp / "gate.json"
        write(gate_path, json.dumps(gate))
        card_payload = run_json(
            [
                sys.executable,
                str(SCRIPT_DIR / "make_case_submission_card.py"),
                "--preflight-json",
                str(preflight_path),
                "--gate-json",
                str(gate_path),
                "--emit-final-draft",
                "--json",
            ],
            failures,
            "make_case_submission_card_draft",
        )
        if card_payload:
            draft = card_payload.get("final_summary_draft", {})
            if not draft:
                failures.append("submission card should include final_summary_draft")
            if "decision_final must be filled" not in draft.get("decision_placeholder", ""):
                failures.append("final draft should leave final decision to workflow")
            if draft.get("compile_result", {}).get("status") != "PASS":
                failures.append("final draft should summarize compile pass")

    if failures:
        print("FAIL case skeleton/submission draft eval")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("PASS case skeleton/submission draft eval")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
