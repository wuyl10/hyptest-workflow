#!/usr/bin/env python3
"""
One-shot health check for hyptest-workflow usage.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from skill_config import default_spec_profile


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parent

STEP_CATEGORIES = {
    "resolve_spec_profile": "profile_health",
    "check_spec_profile": "profile_health",
    "check_spec_profile_registry": "profile_health",
    "check_docs_links": "skill_health",
    "check_skill_consistency": "skill_health",
    "check_cross_skill_consistency": "skill_health",
    "check_reason_codes": "skill_health",
    "eval_reason_code_suggestions": "skill_health",
    "eval_listed_commands_help": "skill_health",
    "check_resource_index": "skill_health",
    "check_hyptest_cli_contract": "repo_health",
    "check_get_result_log_contract": "repo_health",
    "check_hyptest_repo_migration": "repo_health",
    "repo_snapshot": "repo_health",
    "check_env": "env_health",
    "check_case_lint": "case_health",
    "check_case_lint_baseline": "case_health",
    "self_check_quick": "self_check_health",
}

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run hyptest-workflow doctor checks.")
    parser.add_argument("--repo-root", help="Optional hyptest repo root.")
    parser.add_argument("--platform", choices=["spike", "linknan", "all"], help="Platform env to check.")
    parser.add_argument(
        "--spec-profile",
        default=default_spec_profile(),
        help=f"Spec profile name or path. Defaults to {default_spec_profile()} from the profile registry.",
    )
    parser.add_argument(
        "--pre-submit",
        action="store_true",
        help="Run the recommended repo pre-submit checks: repo migration, CLI contract, and lint baseline.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Run stricter skill-maintenance checks in addition to normal doctor checks.",
    )
    parser.add_argument("--case-lint", action="store_true", help="Also run check_case_lint.py on repo sources.")
    parser.add_argument(
        "--case-lint-baseline",
        action="store_true",
        help="Run check_case_lint.py with the bundled historical baseline and warnings-as-errors.",
    )
    parser.add_argument(
        "--check-repo-migration",
        action="store_true",
        help="Also check hyptest repo for removed layout/platform/path logic.",
    )
    parser.add_argument("--skip-self-check", action="store_true", help="Skip self_check.py --quick.")
    parser.add_argument("--json", action="store_true", help="Emit JSON report.")
    return parser.parse_args()


def run_step(name: str, command: list[str]) -> dict[str, object]:
    completed = subprocess.run(
        command,
        cwd=str(SKILL_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "name": name,
        "category": STEP_CATEGORIES.get(name, "skill_error"),
        "ok": completed.returncode == 0,
        "rc": completed.returncode,
        "command": command,
        "stdout_tail": completed.stdout[-4000:],
        "stderr_tail": completed.stderr[-4000:],
    }


def summarize_categories(steps: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    summary: dict[str, dict[str, object]] = {}
    for step in steps:
        category = str(step.get("category", "skill_health"))
        bucket = summary.setdefault(
            category,
            {
                "ok": True,
                "pass_count": 0,
                "fail_count": 0,
                "warning_count": 0,
                "steps": [],
            },
        )
        bucket["steps"].append(step["name"])
        if step["ok"]:
            bucket["pass_count"] += 1
            continue
        if step.get("fatal", True):
            bucket["ok"] = False
            bucket["fail_count"] += 1
        else:
            bucket["warning_count"] += 1
    return summary


def main() -> int:
    args = parse_args()
    steps: list[dict[str, object]] = []

    steps.append(
        run_step(
            "resolve_spec_profile",
            [sys.executable, "scripts/resolve_spec_profile.py", "--spec-profile", args.spec_profile],
        )
    )
    steps.append(
        run_step(
            "check_spec_profile",
            [
                sys.executable,
                "scripts/check_spec_profile.py",
                "--spec-profile",
                args.spec_profile,
                "--strict",
            ],
        )
    )
    steps.append(
        run_step(
            "check_spec_profile_registry",
            [sys.executable, "scripts/check_spec_profile_registry.py"],
        )
    )
    steps.append(run_step("check_docs_links", [sys.executable, "scripts/check_docs_links.py"]))
    steps.append(
        run_step("check_skill_consistency", [sys.executable, "scripts/check_skill_consistency.py"])
    )
    steps.append(
        run_step(
            "check_cross_skill_consistency",
            [sys.executable, "scripts/check_cross_skill_consistency.py"],
        )
    )
    steps.append(run_step("check_reason_codes", [sys.executable, "scripts/check_reason_codes.py"]))
    if args.strict or args.pre_submit:
        steps.append(
            run_step("check_resource_index", [sys.executable, "scripts/check_resource_index.py"])
        )
        steps.append(
            run_step(
                "eval_reason_code_suggestions",
                [sys.executable, "scripts/eval_reason_code_suggestions.py"],
            )
        )
        steps.append(
            run_step(
                "eval_listed_commands_help",
                [sys.executable, "scripts/eval_listed_commands_help.py"],
            )
        )

    run_repo_contract = bool(args.repo_root and (args.check_repo_migration or args.pre_submit))
    run_lint_baseline = bool(args.repo_root and (args.case_lint_baseline or args.pre_submit))

    if run_repo_contract:
        steps.append(
            run_step(
                "check_hyptest_cli_contract",
                [
                    sys.executable,
                    "scripts/check_hyptest_cli_contract.py",
                    "--repo-root",
                    str(Path(args.repo_root).expanduser()),
                ],
            )
        )
        steps.append(
            run_step(
                "check_get_result_log_contract",
                [
                    sys.executable,
                    "scripts/check_get_result_log_contract.py",
                    "--repo-root",
                    str(Path(args.repo_root).expanduser()),
                ],
            )
        )
        steps.append(
            run_step(
                "check_hyptest_repo_migration",
                [
                    sys.executable,
                    "scripts/check_hyptest_repo_migration.py",
                    "--repo-root",
                    str(Path(args.repo_root).expanduser()),
                ],
            )
        )
        steps.append(
            run_step(
                "repo_snapshot",
                [
                    sys.executable,
                    "scripts/repo_snapshot.py",
                    "--repo-root",
                    str(Path(args.repo_root).expanduser()),
                ],
            )
        )

    if args.repo_root and args.platform:
        steps.append(
            run_step(
                "check_env",
                [
                    sys.executable,
                    "scripts/check_env.py",
                    "--repo-root",
                    str(Path(args.repo_root).expanduser()),
                    "--platform",
                    args.platform,
                    "--print-exports",
                ],
            )
        )

    if args.repo_root and args.case_lint:
        steps.append(
            run_step(
                "check_case_lint",
                [
                    sys.executable,
                    "scripts/check_case_lint.py",
                    "--repo-root",
                    str(Path(args.repo_root).expanduser()),
                ],
            )
        )

    if run_lint_baseline:
        steps.append(
            run_step(
                "check_case_lint_baseline",
                [
                    sys.executable,
                    "scripts/check_case_lint.py",
                    "--repo-root",
                    str(Path(args.repo_root).expanduser()),
                    "--baseline",
                    "assets/baselines/case_lint_baseline.json",
                    "--warnings-as-errors",
                ],
            )
        )

    if not args.skip_self_check:
        steps.append(
            run_step(
                "self_check_quick",
                [
                    sys.executable,
                    "scripts/self_check.py",
                    "--quick",
                    "--spec-profile",
                    args.spec_profile,
                    "--json",
                ],
            )
        )

    fatal_failures = [
        step
        for step in steps
        if not step["ok"] and step.get("fatal", True)
    ]
    warnings = [
        step
        for step in steps
        if not step["ok"] and not step.get("fatal", True)
    ]
    category_summary = summarize_categories(steps)
    ok = not fatal_failures
    payload = {
        "ok": ok,
        "spec_profile": args.spec_profile,
        "repo_root": args.repo_root,
        "platform": args.platform,
        "fatal_failure_count": len(fatal_failures),
        "warning_count": len(warnings),
        "category_summary": category_summary,
        "steps": steps,
    }

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(("PASS" if ok else "FAIL") + " hyptest-workflow doctor")
        if warnings:
            print(f"WARN {len(warnings)} non-fatal issue(s)")
        for category, summary in sorted(category_summary.items()):
            marker = "PASS" if summary["ok"] else "FAIL"
            print(
                f"{marker} [{category}] "
                f"pass={summary['pass_count']} fail={summary['fail_count']} warn={summary['warning_count']}"
            )
        for step in steps:
            marker = "PASS" if step["ok"] else ("WARN" if not step.get("fatal", True) else "FAIL")
            print(f"{marker} {step['name']} category={step.get('category')} rc={step['rc']}")
            if not step["ok"]:
                detail = str(step["stderr_tail"] or step["stdout_tail"]).strip()
                if detail:
                    print(detail)

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
