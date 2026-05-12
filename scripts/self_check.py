#!/usr/bin/env python3
"""
Run the common hyptest-workflow skill regression checks.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

from skill_config import default_spec_profile, manifest_scripts


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parent


def load_self_metrics() -> dict[str, object]:
    references = SKILL_ROOT / "references"
    scripts = SKILL_ROOT / "scripts"
    evals = SKILL_ROOT / "assets/evals"
    baseline = SKILL_ROOT / "assets/baselines/case_lint_baseline.json"
    baseline_count = 0
    if baseline.is_file():
        try:
            baseline_count = int(json.loads(baseline.read_text(encoding="utf-8")).get("issue_count", 0))
        except json.JSONDecodeError:
            baseline_count = 0
    return {
        "reference_count": len(list(references.rglob("*.md"))) if references.is_dir() else 0,
        "public_script_count": len(manifest_scripts(public_only=True)),
        "eval_asset_count": len(list(evals.glob("*.json"))) if evals.is_dir() else 0,
        "case_lint_baseline_issue_count": baseline_count,
        "spec_profiles": sorted(
            str(path.relative_to(SKILL_ROOT))
            for path in (references / "spec_profiles").glob("*.md")
        )
        if (references / "spec_profiles").is_dir()
        else [],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run hyptest-workflow skill self checks.")
    parser.add_argument(
        "--spec-profile",
        default=default_spec_profile(),
        help=f"Spec profile to validate. Defaults to {default_spec_profile()} from the profile registry.",
    )
    parser.add_argument(
        "--repo-root",
        help="Optional hyptest repo root for find_similar_cases eval and env checks.",
    )
    parser.add_argument(
        "--platform",
        choices=["spike", "linknan", "all"],
        help="Optional platform for check_env.py. Requires --repo-root.",
    )
    parser.add_argument(
        "--skip-similar-eval",
        action="store_true",
        help="Skip eval_find_similar_cases.py.",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--quick",
        action="store_true",
        help="Run fast checks only: py_compile, profile, env eval, writeback eval, cache eval.",
    )
    mode.add_argument(
        "--repo",
        action="store_true",
        help="Run skill checks plus repo-only checks that need --repo-root but no simulator env.",
    )
    mode.add_argument(
        "--platform-check",
        action="store_true",
        help="Run repo checks plus platform environment checks. Requires --repo-root and --platform.",
    )
    mode.add_argument(
        "--full",
        action="store_true",
        help="Run all checks. This is the default when --repo-root is provided.",
    )
    parser.add_argument(
        "--similar-timeout-seconds",
        type=float,
        default=120.0,
        help="Per-case timeout for eval_find_similar_cases.py.",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON summary.")
    parser.add_argument(
        "--json-out",
        help="Write the JSON summary to this path in addition to stdout when --json is set.",
    )
    parser.add_argument(
        "--md-out",
        help="Write a compact Markdown summary to this path.",
    )
    return parser.parse_args()


def tail(text: str, limit: int = 4000) -> str:
    if len(text) <= limit:
        return text
    return text[-limit:]


def run_step(label: str, command: list[str], *, cwd: Path = SKILL_ROOT, quiet: bool = False) -> dict[str, object]:
    if not quiet:
        print(f"RUN {label}")
    started_at = time.monotonic()
    completed = subprocess.run(
        command,
        cwd=str(cwd),
        text=True,
        check=False,
        capture_output=quiet,
    )
    duration_seconds = time.monotonic() - started_at
    ok = completed.returncode == 0
    result = {
        "name": label,
        "ok": ok,
        "rc": completed.returncode,
        "command": command,
        "duration_seconds": round(duration_seconds, 3),
    }
    if quiet:
        result["stdout_tail"] = tail(completed.stdout or "")
        result["stderr_tail"] = tail(completed.stderr or "")
        return result
    if completed.returncode == 0:
        print(f"PASS {label}")
    else:
        print(f"FAIL {label} rc={completed.returncode}")
    return result


def write_report_files(payload: dict[str, object], args: argparse.Namespace) -> None:
    if args.json_out:
        path = Path(args.json_out).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if args.md_out:
        path = Path(args.md_out).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            "# hyptest-workflow self_check",
            "",
            f"- status: {'PASS' if payload['ok'] else 'FAIL'}",
            f"- failure_count: {payload['failure_count']}",
            f"- spec_profile: {payload['spec_profile']}",
            f"- HYPTEST_HOME: {payload.get('repo_root') or '-'}",
            f"- platform: {payload.get('platform') or '-'}",
            f"- mode: {payload['mode']}",
            "",
            "## Metrics",
            "",
        ]
        metrics = payload.get("metrics", {})
        for key, value in metrics.items():
            if isinstance(value, list):
                lines.append(f"- {key}: {', '.join(value) if value else '-'}")
            else:
                lines.append(f"- {key}: {value}")
        lines.extend([
            "",
            "## Steps",
            "",
        ])
        for step in payload["steps"]:
            if step.get("skipped"):
                marker = "SKIP"
            else:
                marker = "PASS" if step.get("ok") else "FAIL"
            duration = step.get("duration_seconds")
            duration_text = f" ({duration:.3f}s)" if isinstance(duration, (int, float)) else ""
            lines.append(f"- {marker} `{step['name']}`{duration_text}")
            if not step.get("ok") and (step.get("stderr_tail") or step.get("stdout_tail")):
                detail = str(step.get("stderr_tail") or step.get("stdout_tail")).strip()
                if detail:
                    lines.append("")
                    lines.append("  ```text")
                    lines.extend(f"  {line}" for line in detail.splitlines()[-20:])
                    lines.append("  ```")
                    lines.append("")
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def selected_mode(args: argparse.Namespace) -> str:
    if args.quick:
        return "quick"
    if args.repo:
        return "repo"
    if args.platform_check:
        return "platform-check"
    if args.full:
        return "full"
    return "auto"


def main() -> int:
    args = parse_args()
    failures = 0
    if args.platform_check and (not args.repo_root or not args.platform):
        print("--platform-check requires --repo-root and --platform", file=sys.stderr)
        return 2
    run_repo_checks = bool(args.repo or args.platform_check or args.full or (args.repo_root and not args.quick))
    run_platform_checks = bool(args.platform_check or (args.full and args.repo_root and args.platform))
    run_similar_eval = (
        not args.skip_similar_eval
        and bool(args.full)
        and not args.platform_check
    )
    results: list[dict[str, object]] = []

    def record(label: str, command: list[str]) -> None:
        nonlocal failures
        result = run_step(label, command, quiet=args.json)
        results.append(result)
        if not result["ok"]:
            failures += 1

    manifest_rels = manifest_scripts(public_only=True)
    script_paths = [str(SKILL_ROOT / rel) for rel in manifest_rels]
    record("py_compile", [sys.executable, "-m", "py_compile", *script_paths])

    record(
        "check_spec_profile",
        [
            sys.executable,
            "scripts/check_spec_profile.py",
            "--spec-profile",
            args.spec_profile,
            "--strict",
        ],
    )
    record(
        "check_spec_profile_registry",
        [sys.executable, "scripts/check_spec_profile_registry.py", "--policy", "all"],
    )

    record("check_docs_links", [sys.executable, "scripts/check_docs_links.py"])
    record("check_skill_consistency", [sys.executable, "scripts/check_skill_consistency.py"])
    record("check_readme_commands", [sys.executable, "scripts/check_readme_commands.py"])
    record("check_resource_index", [sys.executable, "scripts/check_resource_index.py"])
    record(
        "check_script_manifest",
        [sys.executable, "scripts/update_script_manifest.py", "--check"],
    )
    record(
        "check_resource_index_generated",
        [sys.executable, "scripts/update_resource_index.py", "--check"],
    )
    record(
        "check_cross_skill_consistency",
        [sys.executable, "scripts/check_cross_skill_consistency.py"],
    )
    record("check_reason_codes", [sys.executable, "scripts/check_reason_codes.py"])
    record("eval_reason_code_suggestions", [sys.executable, "scripts/eval_reason_code_suggestions.py"])
    record("eval_check_case_lint", [sys.executable, "scripts/eval_check_case_lint.py"])
    record("eval_check_case_uniqueness", [sys.executable, "scripts/eval_check_case_uniqueness.py"])
    record("eval_case_lint_baseline_diff", [sys.executable, "scripts/eval_case_lint_baseline_diff.py"])
    record("eval_workflow_task_prompts", [sys.executable, "scripts/eval_workflow_task_prompts.py"])
    record("eval_workflow_transcripts", [sys.executable, "scripts/eval_workflow_transcripts.py"])
    record("eval_failure_log_workflow", [sys.executable, "scripts/eval_failure_log_workflow.py"])
    record("eval_get_result_log_contract", [sys.executable, "scripts/eval_get_result_log_contract.py"])
    record("eval_triage_handoff", [sys.executable, "scripts/eval_triage_handoff.py"])
    record("eval_joint_handoff", [sys.executable, "scripts/eval_joint_handoff.py"])
    record("eval_validate_task_request", [sys.executable, "scripts/eval_validate_task_request.py"])

    record("eval_spec_profile", [sys.executable, "scripts/eval_spec_profile.py"])
    record("eval_spec_profile_registry", [sys.executable, "scripts/eval_spec_profile_registry.py"])
    record("eval_profile_portability", [sys.executable, "scripts/eval_profile_portability.py"])
    record("eval_profile_decisions", [sys.executable, "scripts/eval_profile_decisions.py"])
    record("eval_check_env", [sys.executable, "scripts/eval_check_env.py"])
    record("eval_hyptest_cli_contract", [sys.executable, "scripts/eval_hyptest_cli_contract.py"])
    record("eval_case_generation_contract", [sys.executable, "scripts/eval_case_generation_contract.py"])
    record("eval_workflow_smoke", [sys.executable, "scripts/eval_workflow_smoke.py"])
    record("eval_workflow_paths_memory", [sys.executable, "scripts/eval_workflow_paths_memory.py"])
    record("eval_repo_evidence_index", [sys.executable, "scripts/eval_repo_evidence_index.py"])
    record("eval_case_pack_workflow", [sys.executable, "scripts/eval_case_pack_workflow.py"])
    record("eval_case_gate_pack", [sys.executable, "scripts/eval_case_gate_pack.py"])
    record("eval_case_batch_gate_pack", [sys.executable, "scripts/eval_case_batch_gate_pack.py"])
    record("eval_case_multi_platform_gate_pack", [sys.executable, "scripts/eval_case_multi_platform_gate_pack.py"])
    record("eval_case_submission_card", [sys.executable, "scripts/eval_case_submission_card.py"])
    record(
        "eval_case_skeleton_and_submission_draft",
        [sys.executable, "scripts/eval_case_skeleton_and_submission_draft.py"],
    )
    record("eval_case_workflow_ledger", [sys.executable, "scripts/eval_case_workflow_ledger.py"])
    record("eval_suggest_case_name", [sys.executable, "scripts/eval_suggest_case_name.py"])
    record("eval_case_timing_summary", [sys.executable, "scripts/eval_case_timing_summary.py"])
    record("eval_workflow_timeline", [sys.executable, "scripts/eval_workflow_timeline.py"])
    record("doctor_skip_self", [sys.executable, "scripts/doctor.py", "--skip-self-check", "--strict"])
    record("list_skill_commands_markdown", [sys.executable, "scripts/list_skill_commands.py", "--markdown"])
    record("eval_listed_commands_help", [sys.executable, "scripts/eval_listed_commands_help.py"])

    record(
        "eval_check_writeback_format",
        [sys.executable, "scripts/eval_check_writeback_format.py"],
    )

    record(
        "eval_find_similar_cache",
        [sys.executable, "scripts/eval_find_similar_cache.py"],
    )

    if run_repo_checks:
        if not args.repo_root:
            if not args.json:
                print("SKIP repo checks: --repo-root not provided")
            results.append({"name": "repo_checks", "ok": True, "skipped": True})
        else:
            record(
                "check_hyptest_cli_contract",
                [
                    sys.executable,
                    "scripts/check_hyptest_cli_contract.py",
                    "--repo-root",
                    args.repo_root,
                ],
            )
            record(
                "check_get_result_log_contract",
                [
                    sys.executable,
                    "scripts/check_get_result_log_contract.py",
                    "--repo-root",
                    args.repo_root,
                ],
            )
            record(
                "repo_snapshot",
                [
                    sys.executable,
                    "scripts/repo_snapshot.py",
                    "--repo-root",
                    args.repo_root,
                ],
            )
            record(
                "check_case_lint_baseline",
                [
                    sys.executable,
                    "scripts/check_case_lint.py",
                    "--repo-root",
                    args.repo_root,
                    "--baseline",
                    "assets/baselines/case_lint_baseline.json",
                    "--warnings-as-errors",
                ],
            )

    if run_platform_checks:
        record(
            "check_env",
            [
                sys.executable,
                "scripts/check_env.py",
                "--repo-root",
                args.repo_root,
                "--platform",
                args.platform,
            ],
        )
    elif args.repo_root and args.platform:
        record(
            "check_env",
            [
                sys.executable,
                "scripts/check_env.py",
                "--repo-root",
                args.repo_root,
                "--platform",
                args.platform,
            ],
        )

    if run_similar_eval:
        if not args.repo_root:
            if not args.json:
                print("SKIP eval_find_similar_cases: --repo-root not provided")
            results.append({"name": "eval_find_similar_cases", "ok": True, "skipped": True})
        else:
            record(
                "eval_find_similar_cases",
                [
                    sys.executable,
                    "scripts/eval_find_similar_cases.py",
                    "--repo-root",
                    args.repo_root,
                    "--case-timeout-seconds",
                    str(args.similar_timeout_seconds),
                ],
            )

    if args.json:
        payload = {
            "ok": failures == 0,
            "failure_count": failures,
            "spec_profile": args.spec_profile,
            "repo_root": args.repo_root,
            "platform": args.platform,
            "mode": selected_mode(args),
            "metrics": load_self_metrics(),
            "steps": results,
        }
        write_report_files(payload, args)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0 if failures == 0 else 1
    if args.json_out or args.md_out:
        payload = {
            "ok": failures == 0,
            "failure_count": failures,
            "spec_profile": args.spec_profile,
            "repo_root": args.repo_root,
            "platform": args.platform,
            "mode": selected_mode(args),
            "metrics": load_self_metrics(),
            "steps": results,
        }
        write_report_files(payload, args)
    if failures:
        print(f"summary: FAIL {failures} step(s)")
        return 1

    print("summary: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
