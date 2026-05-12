#!/usr/bin/env python3
"""Smoke-test workflow_timeline.py prompt-to-final phase timing."""

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


def run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT_DIR / "workflow_timeline.py"), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def main() -> int:
    failures: list[str] = []
    with tempfile.TemporaryDirectory(prefix="hyptest_timeline_", dir=temp_parent()) as tmpdir:
        repo = Path(tmpdir) / "repo"
        repo.mkdir()
        timeline_id = "ai_arch_timeline_smoke"
        json_out = Path(tmpdir) / "timeline.json"
        md_out = Path(tmpdir) / "timeline.md"

        steps = [
            [
                "start",
                "--repo-root",
                str(repo),
                "--timeline-id",
                timeline_id,
                "--case",
                "ai_arch_timeline_case",
                "--test-point-file",
                "test_point/timeline.md",
                "--platform",
                "spike",
                "--spec-profile",
                "nhv5_1_ap",
                "--phase",
                "prompt_intake",
                "--prompt-received-at",
                "2025-12-31T23:59:50Z",
                "--at",
                "2026-01-01T00:00:00Z",
            ],
            [
                "enter",
                "--repo-root",
                str(repo),
                "--timeline",
                timeline_id,
                "--phase",
                "repo_analysis",
                "--at",
                "2026-01-01T00:00:10Z",
            ],
            [
                "cmd-start",
                "--repo-root",
                str(repo),
                "--timeline",
                timeline_id,
                "--name",
                "rg_source_scan",
                "--cmd",
                "rg AtomicsUnit",
                "--span-id",
                "scan_span",
                "--at",
                "2026-01-01T00:00:12Z",
            ],
            [
                "cmd-end",
                "--repo-root",
                str(repo),
                "--timeline",
                timeline_id,
                "--span-id",
                "scan_span",
                "--status",
                "pass",
                "--return-code",
                "0",
                "--at",
                "2026-01-01T00:00:22Z",
            ],
            [
                "enter",
                "--repo-root",
                str(repo),
                "--timeline",
                timeline_id,
                "--phase",
                "edit_case",
                "--at",
                "2026-01-01T00:00:40Z",
            ],
            [
                "cmd-start",
                "--repo-root",
                str(repo),
                "--timeline",
                timeline_id,
                "--name",
                "parallel_review_a",
                "--phase",
                "edit_case",
                "--cmd",
                "review a",
                "--span-id",
                "parallel_a",
                "--at",
                "2026-01-01T00:00:42Z",
            ],
            [
                "cmd-start",
                "--repo-root",
                str(repo),
                "--timeline",
                timeline_id,
                "--name",
                "parallel_review_b",
                "--phase",
                "edit_case",
                "--cmd",
                "review b",
                "--span-id",
                "parallel_b",
                "--at",
                "2026-01-01T00:00:45Z",
            ],
            [
                "cmd-end",
                "--repo-root",
                str(repo),
                "--timeline",
                timeline_id,
                "--span-id",
                "parallel_a",
                "--status",
                "pass",
                "--return-code",
                "0",
                "--at",
                "2026-01-01T00:00:52Z",
            ],
            [
                "cmd-end",
                "--repo-root",
                str(repo),
                "--timeline",
                timeline_id,
                "--span-id",
                "parallel_b",
                "--status",
                "pass",
                "--return-code",
                "0",
                "--at",
                "2026-01-01T00:00:55Z",
            ],
            [
                "finish",
                "--repo-root",
                str(repo),
                "--timeline",
                timeline_id,
                "--at",
                "2026-01-01T00:01:00Z",
                "--json-out",
                str(json_out),
                "--md-out",
                str(md_out),
                "--json",
            ],
        ]

        completed = None
        for command in steps:
            completed = run(command)
            if completed.returncode != 0:
                failures.append(
                    f"workflow_timeline.py {' '.join(command[:2])} failed rc={completed.returncode}: "
                    f"{completed.stderr or completed.stdout}"
                )
                break

        if completed and completed.returncode == 0:
            try:
                payload = json.loads(completed.stdout)
            except json.JSONDecodeError as exc:
                failures.append(f"finish output is not JSON: {exc}")
                payload = {}
            if payload:
                timing = payload.get("timing", {})
                if timing.get("total_seconds") != 60.0:
                    failures.append("timeline total_seconds should span start to finish")
                if timing.get("pre_start_model_seconds") != 10.0:
                    failures.append("timeline should expose externally supplied pre-start model time")
                if timing.get("prompt_to_finish_seconds") != 70.0:
                    failures.append("timeline should expose prompt-to-finish time when prompt boundary is supplied")
                by_phase = timing.get("by_phase", {})
                if by_phase.get("prompt_intake") != 10.0:
                    failures.append("prompt_intake phase should be 10 seconds")
                if by_phase.get("repo_analysis") != 30.0:
                    failures.append("repo_analysis phase should be 30 seconds")
                if by_phase.get("edit_case") != 20.0:
                    failures.append("edit_case phase should be 20 seconds")
                commands = timing.get("commands", [])
                if len(commands) != 3:
                    failures.append("timeline should record three command spans")
                else:
                    command = commands[0]
                    if command.get("name") != "rg_source_scan":
                        failures.append("command span should preserve name")
                    if command.get("phase") != "repo_analysis":
                        failures.append("command span should be attributed to active phase")
                    if command.get("seconds") != 10.0:
                        failures.append("command span should measure cmd-start to cmd-end duration")
                    if command.get("return_code") != 0 or command.get("status") != "pass":
                        failures.append("command span should preserve status and return code")
                phases = {
                    item.get("name"): item
                    for item in timing.get("phases", [])
                    if isinstance(item, dict)
                }
                repo_phase = phases.get("repo_analysis", {})
                if repo_phase.get("command_seconds") != 10.0:
                    failures.append("repo_analysis should include 10 seconds of command time")
                if repo_phase.get("unattributed_seconds") != 20.0:
                    failures.append("repo_analysis should expose non-command time as unattributed")
                if repo_phase.get("before_first_command_seconds") != 2.0:
                    failures.append("repo_analysis should expose before-first-command gap")
                if repo_phase.get("after_last_command_seconds") != 18.0:
                    failures.append("repo_analysis should expose after-last-command gap")
                if repo_phase.get("command_window_seconds") != 10.0:
                    failures.append("repo_analysis should expose command window")
                edit_phase = phases.get("edit_case", {})
                if edit_phase.get("command_seconds") != 13.0:
                    failures.append("edit_case overlapping commands should be merged as 13 seconds of wall time")
                if edit_phase.get("command_span_seconds") != 20.0:
                    failures.append("edit_case should also preserve raw command span seconds")
                if timing.get("total_command_seconds") != 23.0:
                    failures.append("timeline should aggregate merged phase command wall seconds")
                if timing.get("total_command_span_seconds") != 30.0:
                    failures.append("timeline should aggregate raw command span seconds")
                if timing.get("total_unattributed_seconds") != 37.0:
                    failures.append("timeline should aggregate total unattributed seconds")
                hints = timing.get("optimization_hints", {})
                if not hints:
                    failures.append("timeline should include optimization_hints")
                else:
                    if hints.get("command_seconds") != 23.0:
                        failures.append("optimization_hints should expose command_seconds")
                    if hints.get("total_unattributed_seconds") != 37.0:
                        failures.append("optimization_hints should expose unattributed total")
                    if hints.get("no_command_phase_seconds") != 10.0:
                        failures.append("optimization_hints should sum no-command phases")
                    if hints.get("late_phase_exit_seconds") != 0.0:
                        failures.append("optimization_hints should not flag short post-command gaps")
                    if hints.get("other_unattributed_seconds") != 27.0:
                        failures.append("optimization_hints should expose remaining unattributed time")
                    if not hints.get("no_command_phase_candidates"):
                        failures.append("optimization_hints should list long no-command phases")
                    if not hints.get("slow_command_candidates"):
                        failures.append("optimization_hints should list slow command candidates")
                    if not hints.get("recommended_actions"):
                        failures.append("optimization_hints should include recommended actions")
                if payload.get("case") != "ai_arch_timeline_case":
                    failures.append("timeline should preserve case metadata")
                if payload.get("status") != "finished":
                    failures.append("timeline should be finished after finish command")
        if not json_out.is_file():
            failures.append("finish should write JSON report")
        if not md_out.is_file():
            failures.append("finish should write Markdown report")
        elif "## Optimization Hints" not in md_out.read_text(encoding="utf-8"):
            failures.append("Markdown report should render Optimization Hints")

    if failures:
        print("FAIL workflow timeline eval")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("PASS workflow timeline eval")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
