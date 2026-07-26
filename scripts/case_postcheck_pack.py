#!/usr/bin/env python3
"""Collect post-edit evidence for a hyptest case without running simulators."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from skill_config import default_spec_profile, resolve_path
from writeback_register import load_registration_status


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parent
CASE_DEF_RE_TEMPLATE = r"^\s*(?:static\s+)?bool\s+{name}\s*\("


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect lint/writeback/register/artifact/log evidence after editing a case."
    )
    parser.add_argument("--repo-root", required=True, help="Path to hyptest repo root.")
    parser.add_argument("--test-point-file", required=True, help="Path to test_point markdown file.")
    parser.add_argument("--case", action="append", required=True, help="Case name; can be repeated.")
    parser.add_argument("--platform", default="spike", choices=["spike", "linknan"], help="Target platform.")
    default_profile = default_spec_profile()
    parser.add_argument(
        "--spec-profile",
        default=default_profile,
        help=f"Spec profile name/path. Defaults to {default_profile} from the profile registry.",
    )
    parser.add_argument(
        "--skip-lint",
        action="store_true",
        help="Skip changed case source lint.",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON report.")
    parser.add_argument("--md-out", help="Write Markdown report to this path.")
    parser.add_argument("--json-out", help="Write JSON report to this path.")
    return parser.parse_args()


def run_json(command: list[str], *, cwd: Path = SKILL_ROOT) -> dict[str, Any]:
    started = time.monotonic()
    completed = subprocess.run(
        command,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )
    duration_seconds = round(time.monotonic() - started, 3)
    try:
        payload = json.loads(completed.stdout) if completed.stdout.strip() else {}
    except json.JSONDecodeError:
        payload = {}
    return {
        "ok": completed.returncode == 0,
        "returncode": completed.returncode,
        "duration_seconds": duration_seconds,
        "command": " ".join(command),
        "stdout_summary": summarize_text(completed.stdout),
        "stderr_summary": summarize_text(completed.stderr),
        "payload": compact_payload(Path(command[1]).name if len(command) > 1 else "", payload),
    }


def summarize_text(text: str, limit: int = 1200) -> str:
    stripped = text.strip()
    if len(stripped) <= limit:
        return stripped
    return stripped[:limit].rstrip() + "\n..."


def compact_payload(script_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    if not payload:
        return {}
    if script_name == "check_case_lint.py":
        issues: list[dict[str, Any]] = []
        for result in payload.get("results", []):
            for issue in result.get("issues", []):
                if not issue.get("baseline_ignored"):
                    issues.append(issue)
                if len(issues) >= 20:
                    break
            if len(issues) >= 20:
                break
        return {
            "ok": payload.get("ok"),
            "checked_file_count": payload.get("checked_file_count"),
            "changed_only": payload.get("changed_only"),
            "active_issue_count": payload.get("active_issue_count"),
            "error_count": payload.get("error_count"),
            "warning_count": payload.get("warning_count"),
            "effective_error_count": payload.get("effective_error_count"),
            "first_active_issues": issues,
        }
    if script_name == "check_writeback_format.py":
        compact_results = []
        for item in payload.get("results", []):
            compact_results.append(
                {
                    "file": item.get("file"),
                    "entry_count": item.get("entry_count"),
                    "ok": item.get("ok"),
                    "issues": item.get("issues", [])[:20],
                    "warnings": item.get("warnings", [])[:20],
                }
            )
        return {
            "checked_file_count": payload.get("checked_file_count"),
            "ok_file_count": payload.get("ok_file_count"),
            "warning_count": payload.get("warning_count"),
            "results": compact_results,
        }
    return payload


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore") if path.is_file() else ""


def find_case_definitions(repo_root: Path, case_name: str) -> list[dict[str, Any]]:
    pattern = re.compile(CASE_DEF_RE_TEMPLATE.format(name=re.escape(case_name)), re.MULTILINE)
    results: list[dict[str, Any]] = []
    for rel_root in ("ai_test_cases", "manual_test_cases"):
        root = repo_root / rel_root
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.c")):
            text = read_text(path)
            for match in pattern.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                results.append(
                    {
                        "path": str(path.relative_to(repo_root)),
                        "line": line,
                    }
                )
    return results


def latest_logs(repo_root: Path, platform: str, case_name: str, limit: int = 5) -> list[dict[str, Any]]:
    base = repo_root / ".tmp" / "result_log" / platform
    if not base.is_dir():
        base = repo_root / ".tmp" / "result_log"
    if not base.is_dir():
        return []
    fast_candidates: list[Path] = []
    seen: set[Path] = set()
    for pattern in (f"{case_name}*.log", f"*{case_name}*.log"):
        for path in base.glob(pattern):
            if path.is_file() and path not in seen:
                fast_candidates.append(path)
                seen.add(path)

    if fast_candidates:
        logs = fast_candidates
        search_strategy = "fast-glob"
    else:
        logs = [
            path
            for path in base.rglob("*.log")
            if case_name in path.name or case_name in str(path)
        ]
        search_strategy = "fallback-rglob"
    logs.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    return [
        {
            "path": str(path.relative_to(repo_root)),
            "size": path.stat().st_size,
            "mtime": int(path.stat().st_mtime),
            "search_strategy": search_strategy,
            "summary": log_summary(path),
        }
        for path in logs[:limit]
    ]


def log_summary(path: Path) -> dict[str, bool]:
    text = read_text(path)[-8000:]
    upper = text.upper()
    return {
        "has_pass": "PASS" in upper or "HIT GOOD TRAP" in upper,
        "has_fail": "FAIL" in upper or "BAD TRAP" in upper,
        "has_timeout": "TIMEOUT" in upper or "NO COMMIT" in upper or "STUCK" in upper,
    }


def artifact_status(repo_root: Path, platform: str, case_name: str) -> dict[str, Any]:
    base = repo_root / "case_elf_asm" / platform
    candidates = {
        "elf": [base / f"{case_name}.ELF", base / f"{case_name}.elf"],
        "asm": [base / f"{case_name}.asm", base / f"{case_name}.S", base / f"{case_name}.s"],
    }
    result: dict[str, Any] = {}
    for key, paths in candidates.items():
        existing = [path for path in paths if path.is_file()]
        result[key] = str(existing[0].relative_to(repo_root)) if existing else None
    result["ok"] = bool(result.get("elf"))
    return result


def case_writeback_mentions(test_point_file: Path, case_name: str) -> list[dict[str, Any]]:
    text = read_text(test_point_file)
    mentions: list[dict[str, Any]] = []
    for index, line in enumerate(text.splitlines(), 1):
        if case_name in line:
            mentions.append({"line": index, "text": line.rstrip()})
    return mentions


def run_commands_parallel(commands: dict[str, list[str]]) -> dict[str, Any]:
    if not commands:
        return {}
    results: dict[str, Any] = {}
    with ThreadPoolExecutor(max_workers=max(1, min(len(commands), 4))) as executor:
        future_to_name = {
            executor.submit(run_json, command): name
            for name, command in commands.items()
        }
        for future in as_completed(future_to_name):
            name = future_to_name[future]
            results[name] = future.result()
    return {name: results[name] for name in commands}


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    started = time.monotonic()
    repo_root = resolve_path(args.repo_root)
    test_point_file = resolve_path(args.test_point_file)
    register_status = load_registration_status(repo_root)

    report: dict[str, Any] = {
        "repo_root": str(repo_root),
        "test_point_file": str(test_point_file),
        "platform": args.platform,
        "spec_profile": args.spec_profile,
        "cases": [],
        "commands": {},
    }

    lint_files: list[str] = []
    for case_name in args.case:
        definitions = find_case_definitions(repo_root, case_name)
        for definition in definitions:
            path = str(definition["path"])
            if path not in lint_files:
                lint_files.append(path)
        report["cases"].append(
            {
                "case": case_name,
                "definitions": definitions,
                "definition_unique": len(definitions) == 1,
                "register_status": register_status.get(case_name, "unregistered"),
                "artifacts": artifact_status(repo_root, args.platform, case_name),
                "latest_logs": latest_logs(repo_root, args.platform, case_name),
                "test_point_mentions": case_writeback_mentions(test_point_file, case_name),
            }
        )

    commands: dict[str, list[str]] = {}
    if not args.skip_lint:
        lint_cmd = [
            sys.executable,
            str(SCRIPT_DIR / "check_case_lint.py"),
            "--repo-root",
            str(repo_root),
            "--strict-case-end",
            "--warnings-as-errors",
            "--json",
        ]
        if lint_files:
            for path in lint_files:
                lint_cmd.extend(["--file", str(repo_root / path)])
        else:
            lint_cmd.append("--changed-only")
        commands["case_lint"] = lint_cmd

    commands["writeback_check"] = [
        sys.executable,
        str(SCRIPT_DIR / "check_writeback_format.py"),
        "--repo-root",
        str(repo_root),
        "--file",
        str(test_point_file),
        "--check-register",
        "--check-reason-code",
        "--spec-profile",
        args.spec_profile,
        "--json",
    ]
    report["commands"] = run_commands_parallel(commands)

    if lint_files and "case_lint" in report["commands"]:
        lint_result = report["commands"]["case_lint"]
        lint_payload = lint_result.get("payload", {})
        checked_file_count = lint_payload.get("checked_file_count")
        lint_result["expected_file_count"] = len(lint_files)
        if checked_file_count != len(lint_files):
            lint_result["ok"] = False
            lint_result["validation_error"] = (
                f"case lint checked {checked_file_count} files; expected {len(lint_files)}"
            )

    command_ok = all(item.get("ok") for item in report["commands"].values())
    cases_ok = all(
        case["definition_unique"]
        and case["register_status"] in {"enabled", "commented"}
        and bool(case["test_point_mentions"])
        for case in report["cases"]
    )
    report["ok"] = bool(command_ok and cases_ok)
    report["timing"] = build_timing(report["commands"], started)
    report["next_steps"] = [
        "If artifacts.elf is missing, run compile_elf.py for the target platform and case.",
        "If latest_logs is empty and the case is not compile-only, run get_result.py for the target platform and case.",
        "If writeback_check fails, fix test_point lightweight mapping or test_register.c status before final delivery.",
    ]
    return report


def build_timing(commands: dict[str, Any], started: float) -> dict[str, Any]:
    by_step = {
        name: item.get("duration_seconds")
        for name, item in commands.items()
        if item.get("duration_seconds") is not None
    }
    slowest = sorted(
        by_step.items(),
        key=lambda item: float(item[1] or 0),
        reverse=True,
    )[:5]
    return {
        "total_seconds": round(time.monotonic() - started, 3),
        "by_step": by_step,
        "slowest_steps": [{"name": name, "seconds": seconds} for name, seconds in slowest],
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# hyptest case postcheck pack",
        "",
        f"- HYPTEST_HOME: `{report['repo_root']}`",
        f"- test_point_file: `{report['test_point_file']}`",
        f"- platform: `{report['platform']}`",
        f"- spec_profile: `{report['spec_profile']}`",
        f"- overall: `{'PASS' if report['ok'] else 'FAIL'}`",
        "",
        "## Checks",
        "",
    ]
    for name, item in report["commands"].items():
        lines.append(f"- {'PASS' if item.get('ok') else 'FAIL'} `{name}`: `{item.get('command', '')}`")
    lines.extend(["", "## Timing", ""])
    timing = report.get("timing", {})
    lines.append(f"- total_seconds: `{timing.get('total_seconds', '-')}`")
    by_step = timing.get("by_step") or {}
    if by_step:
        lines.append("- by_step:")
        for name, seconds in by_step.items():
            lines.append(f"  - {name}: `{seconds}` seconds")
    slowest = timing.get("slowest_steps", [])
    if slowest:
        lines.append("- slowest_steps:")
    for item in timing.get("slowest_steps", []):
        lines.append(f"  - {item['name']}: `{item['seconds']}` seconds")
    lines.extend(["", "## Cases", ""])
    for case in report["cases"]:
        lines.append(f"### `{case['case']}`")
        lines.append(f"- definition_unique: `{case['definition_unique']}`")
        for definition in case["definitions"]:
            lines.append(f"  - `{definition['path']}:{definition['line']}`")
        lines.append(f"- register_status: `{case['register_status']}`")
        artifacts = case["artifacts"]
        lines.append(f"- artifact ELF: `{artifacts.get('elf') or 'missing'}`")
        lines.append(f"- artifact ASM: `{artifacts.get('asm') or 'missing'}`")
        if case["latest_logs"]:
            lines.append("- latest logs:")
            for log in case["latest_logs"]:
                summary = log.get("summary", {})
                lines.append(
                    f"  - `{log['path']}` pass={summary.get('has_pass')} fail={summary.get('has_fail')} timeout={summary.get('has_timeout')}"
                )
        else:
            lines.append("- latest logs: `none`")
        if case["test_point_mentions"]:
            lines.append("- test_point mentions:")
            for mention in case["test_point_mentions"]:
                lines.append(f"  - line {mention['line']}: `{mention['text']}`")
        else:
            lines.append("- test_point mentions: `none`")
        lines.append("")
    lines.extend(["## Next Steps", ""])
    for step in report.get("next_steps", []):
        lines.append(f"- {step}")
    lines.append("")
    return "\n".join(lines)


def write_outputs(report: dict[str, Any], args: argparse.Namespace) -> None:
    if args.json_out:
        path = Path(args.json_out).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.md_out:
        path = Path(args.md_out).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render_markdown(report), encoding="utf-8")


def main() -> int:
    args = parse_args()
    report = build_report(args)
    write_outputs(report, args)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(report))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
