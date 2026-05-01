#!/usr/bin/env python3
"""Smoke-test make_case_submission_card.py evidence-only contract."""

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


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True, check=False)


def main() -> int:
    failures: list[str] = []
    with tempfile.TemporaryDirectory(prefix="hyptest_submission_card_", dir=temp_parent()) as tmpdir:
        tmp = Path(tmpdir)
        case_name = "ai_arch_submission_smoke_case"
        preflight_json = tmp / "preflight.json"
        gate_json = tmp / "gate.json"
        card_json = tmp / "card.json"
        card_md = tmp / "card.md"

        write_json(
            preflight_json,
            {
                "ok": True,
                "repo_root": "/repo",
                "test_point_file": "/repo/test_point/submission.md",
                "platform": "spike",
                "spec_profile": "nhv5_1_ap",
                "cache": {"enabled": True, "hit": True},
                "commands": {
                    "similar_cases": {
                        "payload": {
                            "retrieval_status": "ok",
                            "top_results": [
                                {
                                    "case_name": "ai_arch_old_case",
                                    "file": "ai_test_cases/old.c",
                                    "line": 12,
                                    "score": 31.0,
                                    "register_status": "enabled",
                                }
                            ],
                        }
                    }
                },
            },
        )
        write_json(
            gate_json,
            {
                "ok": True,
                "repo_root": "/repo",
                "test_point_file": "/repo/test_point/submission.md",
                "platform": "spike",
                "spec_profile": "nhv5_1_ap",
                "case": case_name,
                "commands": {
                    "compile": {"ok": True, "returncode": 0, "duration_seconds": 1.0, "command": "compile"},
                    "run": {"ok": True, "returncode": 0, "duration_seconds": 2.0, "command": "run"},
                    "postcheck": {
                        "ok": True,
                        "returncode": 0,
                        "duration_seconds": 0.5,
                        "command": "postcheck",
                        "payload": {
                            "ok": True,
                            "cases": [
                                {
                                    "case": case_name,
                                    "definition_unique": True,
                                    "definitions": [{"path": "ai_test_cases/submission.c", "line": 4}],
                                    "register_status": "enabled",
                                    "artifacts": {
                                        "elf": f"case_elf_asm/spike/{case_name}.ELF",
                                        "asm": f"case_elf_asm/spike/{case_name}.asm",
                                    },
                                    "latest_logs": [
                                        {
                                            "path": f"result_log/spike/{case_name}.log",
                                            "summary": {
                                                "has_pass": True,
                                                "has_fail": False,
                                                "has_timeout": False,
                                            },
                                        }
                                    ],
                                    "test_point_mentions": [
                                        {"line": 9, "text": f"- `{case_name}`（default，已启用）"}
                                    ],
                                }
                            ],
                        },
                    },
                },
                "evidence_requirements": {
                    "ok": True,
                    "requirements": {"artifact_elf": True, "latest_log": True},
                },
                "timing": {"total_seconds": 3.5, "by_step": {"compile": 1.0, "run": 2.0}},
            },
        )

        completed = run(
            [
                sys.executable,
                str(SCRIPT_DIR / "make_case_submission_card.py"),
                "--preflight-json",
                str(preflight_json),
                "--gate-json",
                str(gate_json),
                "--json-out",
                str(card_json),
                "--md-out",
                str(card_md),
                "--json",
            ]
        )
        if completed.returncode != 0:
            failures.append(completed.stderr.strip() or completed.stdout.strip())
        else:
            payload = json.loads(completed.stdout)
            if not payload.get("ready_for_human_tiering"):
                failures.append("submission card should be ready for human tiering")
            if "decision" in payload and payload.get("decision"):
                failures.append("submission card must not make a tiering decision")
            if not payload.get("decision_note"):
                failures.append("submission card missing decision boundary note")
            if not payload.get("preflight", {}).get("similar_cases"):
                failures.append("submission card missing similar-case evidence")
            if not card_json.is_file() or not card_md.is_file():
                failures.append("submission card did not write requested outputs")

    if failures:
        print("FAIL case submission card eval")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("PASS case submission card eval")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
