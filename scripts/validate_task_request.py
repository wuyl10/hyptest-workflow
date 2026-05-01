#!/usr/bin/env python3
"""Validate a hyptest-workflow task request before editing or running cases."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

from skill_config import default_spec_profile, expand_path, resolve_path


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parent
VALID_PLATFORMS = {"spike", "linknan"}
TASK_MODES = {
    "new-case-only",
    "supplement-existing-point",
    "fix-case",
    "run-only",
    "triage-only",
    "writeback-only",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate hyptest-workflow task inputs.")
    parser.add_argument("--request-json", help="Path to a JSON request object.")
    parser.add_argument("--request-md", help="Path to a Markdown/text request with key: value lines.")
    parser.add_argument("--repo-root", help="Path to hyptest repo root.")
    parser.add_argument("--test-point-file", help="Path to test_point markdown file.")
    parser.add_argument("--platform", help="Target hyptest platform.")
    default_profile = default_spec_profile()
    parser.add_argument(
        "--spec-profile",
        default=default_profile,
        help=f"Spec profile name/path. Defaults to {default_profile} from the profile registry.",
    )
    parser.add_argument("--task-mode", choices=sorted(TASK_MODES), help="Requested task mode.")
    parser.add_argument("--case-name", help="Case name for fix/run/triage tasks.")
    parser.add_argument("--new-case-count", help="New case count or range, e.g. 1 or 1-3.")
    parser.add_argument("--coverage-scope", choices=["file", "repo"], help="Coverage scope.")
    parser.add_argument(
        "--failure-log",
        help="Path to failure log for triage-only or failure-driven tasks.",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON report.")
    return parser.parse_args()


def parse_request_md(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    key_map = {
        "repo_root": "repo_root",
        "repo-root": "repo_root",
        "test_point_file": "test_point_file",
        "test-point-file": "test_point_file",
        "platform": "platform",
        "spec_profile": "spec_profile",
        "spec-profile": "spec_profile",
        "task_mode": "task_mode",
        "task-mode": "task_mode",
        "case_name": "case_name",
        "case-name": "case_name",
        "new_case_count": "new_case_count",
        "new-case-count": "new_case_count",
        "coverage_scope": "coverage_scope",
        "coverage-scope": "coverage_scope",
        "failure_log": "failure_log",
        "failure-log": "failure_log",
    }
    for raw_line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.strip().strip("-").strip()
        match = re.match(r"([A-Za-z_][A-Za-z0-9_-]*)\s*[:=]\s*(.+)$", line)
        if not match:
            continue
        key = key_map.get(match.group(1).strip().lower())
        if key:
            values[key] = match.group(2).strip().strip("`")
    return values


def load_request_overrides(args: argparse.Namespace) -> dict[str, object]:
    if args.request_json and args.request_md:
        raise ValueError("use only one of --request-json or --request-md")
    if args.request_json:
        path = expand_path(args.request_json)
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("--request-json must contain a JSON object")
        return payload
    if args.request_md:
        return parse_request_md(expand_path(args.request_md))
    return {}


def pick(args: argparse.Namespace, overrides: dict[str, object], name: str, default: str | None = None) -> str | None:
    value = getattr(args, name)
    if value is not None:
        return value
    override = overrides.get(name)
    if override is None:
        return default
    return str(override)


def resolve_profile(spec_profile: str) -> tuple[bool, str]:
    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_DIR / "resolve_spec_profile.py"),
            "--spec-profile",
            spec_profile,
        ],
        cwd=str(SKILL_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    text = (completed.stdout or completed.stderr).strip()
    return completed.returncode == 0, text


def parse_count(value: str | None) -> bool:
    if not value:
        return False
    return bool(re.fullmatch(r"\d+(?:-\d+)?", value.strip()))


def add_issue(issues: list[dict[str, str]], message: str, suggested_fix: str = "") -> None:
    item = {"message": message}
    if suggested_fix:
        item["suggested_fix"] = suggested_fix
    issues.append(item)


def add_warning(warnings: list[dict[str, str]], message: str, suggested_fix: str = "") -> None:
    item = {"message": message}
    if suggested_fix:
        item["suggested_fix"] = suggested_fix
    warnings.append(item)


def messages(items: list[dict[str, str]]) -> list[str]:
    return [item["message"] for item in items]


def normalize_platform(platform_raw: str | None) -> str | None:
    if not platform_raw:
        return None
    platform = platform_raw.strip().lower()
    if platform == "xiangshan":
        return "linknan"
    return platform


def infer_coverage_scope(task_mode: str | None, explicit_scope: str | None) -> str | None:
    if explicit_scope:
        return explicit_scope
    if task_mode == "new-case-only":
        return "repo"
    if task_mode == "supplement-existing-point":
        return "file"
    return None


def build_next_commands(normalized: dict[str, object]) -> list[str]:
    profile = str(normalized.get("spec_profile") or default_spec_profile())
    repo_root = normalized.get("repo_root")
    test_point_file = normalized.get("test_point_file")
    platform = normalized.get("platform")
    task_mode = normalized.get("task_mode")
    case_name = normalized.get("case_name")
    failure_log = normalized.get("failure_log")
    commands = [
        f"python3 scripts/resolve_spec_profile.py --spec-profile {profile}",
    ]
    if repo_root:
        commands.append(f"python3 scripts/check_hyptest_cli_contract.py --repo-root {repo_root}")
    if repo_root and platform:
        task_mode_arg = f" --task-mode {task_mode}" if task_mode else ""
        commands.append(
            f"python3 scripts/check_env.py --repo-root {repo_root} --platform {platform}{task_mode_arg} --explain"
        )
    if repo_root and task_mode == "new-case-only":
        commands.append(
            f"python3 scripts/find_similar_cases.py --repo-root {repo_root} --query '<scenario terms>' --limit 5 --explain-score"
        )
    if repo_root and test_point_file and task_mode in {
        "new-case-only",
        "supplement-existing-point",
        "writeback-only",
    }:
        commands.append(
            f"python3 scripts/check_writeback_format.py --repo-root {repo_root} --file {test_point_file} --check-register --spec-profile {profile}"
        )
    if failure_log and platform:
        commands.append(
            f"python3 scripts/make_triage_handoff.py --log-file {failure_log} --platform {platform} --spec-profile {profile} --json"
        )
    elif task_mode == "triage-only" and case_name:
        commands.append(
            f"python3 scripts/classify_failure_log.py --log-file <log-for-{case_name}> --json"
        )
    return commands


def main() -> int:
    args = parse_args()
    try:
        overrides = load_request_overrides(args)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    issues: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []

    repo_root_raw = pick(args, overrides, "repo_root")
    test_point_file_raw = pick(args, overrides, "test_point_file")
    failure_log_raw = pick(args, overrides, "failure_log")
    platform_raw = pick(args, overrides, "platform")
    default_profile = default_spec_profile()
    spec_profile = pick(args, overrides, "spec_profile", default_profile) or default_profile
    task_mode = pick(args, overrides, "task_mode")
    case_name = pick(args, overrides, "case_name")
    new_case_count = pick(args, overrides, "new_case_count")
    coverage_scope = pick(args, overrides, "coverage_scope")

    repo_root = resolve_path(repo_root_raw) if repo_root_raw else None
    test_point_file = (
        resolve_path(test_point_file_raw) if test_point_file_raw else None
    )
    failure_log = resolve_path(failure_log_raw) if failure_log_raw else None

    profile_ok, profile_detail = resolve_profile(spec_profile)
    if not profile_ok:
        add_issue(
            issues,
            f"spec_profile not found or invalid: {spec_profile}: {profile_detail}",
            "use scripts/resolve_spec_profile.py --spec-profile <name> to list/verify the profile path",
        )

    if platform_raw:
        platform = platform_raw.strip().lower()
        if platform == "xiangshan":
            add_issue(
                issues,
                "platform=xiangshan is not a hyptest platform; use platform=linknan",
                "replace platform=xiangshan with platform=linknan",
            )
        elif platform not in VALID_PLATFORMS:
            add_issue(
                issues,
                f"unsupported platform `{platform_raw}`; expected spike or linknan",
                "set --platform spike or --platform linknan",
            )

    if repo_root:
        required = ["compile_elf.py", "get_result.py", "test_register.c"]
        for rel in required:
            if not (repo_root / rel).exists():
                add_issue(
                    issues,
                    f"repo_root missing `{rel}`: {repo_root}",
                    "set --repo-root to the riscv-hyp-tests-nhv5.1 repository root",
                )
    elif task_mode not in {None, "triage-only"}:
        add_issue(issues, "repo_root is required for this task_mode", "pass --repo-root <repo_root>")

    if test_point_file:
        if not test_point_file.is_file():
            add_issue(
                issues,
                f"test_point_file not found: {test_point_file}",
                "pass an existing file under <repo_root>/test_point/",
            )
        elif repo_root and repo_root not in test_point_file.parents and test_point_file != repo_root:
            add_warning(
                warnings,
                "test_point_file is outside repo_root; confirm this is intentional",
                "prefer a path under <repo_root>/test_point/",
            )

    if task_mode in {"new-case-only", "supplement-existing-point", "writeback-only"}:
        if not test_point_file:
            add_issue(
                issues,
                f"task_mode={task_mode} requires --test-point-file",
                "pass --test-point-file <repo_root>/test_point/<file>",
            )

    if task_mode == "new-case-only":
        if not parse_count(new_case_count):
            add_issue(
                issues,
                "task_mode=new-case-only requires --new-case-count like 1 or 1-3",
                "pass --new-case-count 1 or --new-case-count 1-3",
            )

    if task_mode in {"fix-case", "run-only"} and not case_name:
        add_warning(
            warnings,
            f"task_mode={task_mode} usually needs --case-name",
            "pass --case-name <case_name>",
        )

    if task_mode == "run-only" and not platform_raw:
        add_issue(issues, "task_mode=run-only requires --platform", "pass --platform spike or --platform linknan")

    if task_mode == "triage-only":
        if failure_log and not failure_log.is_file():
            add_issue(issues, f"failure_log not found: {failure_log}", "pass --failure-log <existing log path>")
        if not failure_log and not case_name:
            add_warning(
                warnings,
                "triage-only has no failure_log or case_name; evidence may be too thin",
                "pass --failure-log <log> or --case-name <case_name>",
            )

    inferred_coverage_scope = infer_coverage_scope(task_mode, coverage_scope)
    normalized = {
        "repo_root": str(repo_root) if repo_root else None,
        "test_point_file": str(test_point_file) if test_point_file else None,
        "failure_log": str(failure_log) if failure_log else None,
        "spec_profile": spec_profile,
        "spec_profile_path": profile_detail if profile_ok else None,
        "platform": normalize_platform(platform_raw),
        "task_mode": task_mode,
        "case_name": case_name,
        "new_case_count": new_case_count,
        "coverage_scope": inferred_coverage_scope,
    }
    payload = {
        "ok": not issues,
        "issues": messages(issues),
        "warnings": messages(warnings),
        "issue_details": issues,
        "warning_details": warnings,
        "normalized": normalized,
        "next_commands": build_next_commands(normalized),
        "resolved": {
            "repo_root": str(repo_root) if repo_root else None,
            "test_point_file": str(test_point_file) if test_point_file else None,
            "failure_log": str(failure_log) if failure_log else None,
            "spec_profile": spec_profile,
            "spec_profile_path": profile_detail if profile_ok else None,
            "platform": platform_raw,
            "task_mode": task_mode,
            "case_name": case_name,
            "new_case_count": new_case_count,
            "coverage_scope": inferred_coverage_scope,
        },
    }

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(("PASS" if payload["ok"] else "FAIL") + " task request")
        for issue in issues:
            print(f"  - issue: {issue['message']}")
            if issue.get("suggested_fix"):
                print(f"    fix: {issue['suggested_fix']}")
        for warning in warnings:
            print(f"  - warning: {warning['message']}")
            if warning.get("suggested_fix"):
                print(f"    fix: {warning['suggested_fix']}")
        if payload["next_commands"]:
            print("next commands:")
            for command in payload["next_commands"]:
                print(f"  {command}")
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
