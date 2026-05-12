#!/usr/bin/env python3
"""Run a single hyptest case gate and collect evidence."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from skill_config import (
    apply_env_overrides,
    default_spec_profile,
    env_override_args,
    resolve_path,
    runtime_env_overrides,
)


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compile/run one hyptest case, then collect postcheck evidence."
    )
    parser.add_argument("--repo-root", required=True, help="Path to hyptest repo root.")
    parser.add_argument("--test-point-file", required=True, help="Path to test_point markdown file.")
    parser.add_argument("--case", required=True, help="Case name to gate.")
    parser.add_argument("--platform", default="spike", choices=["spike", "linknan"], help="Target platform.")
    default_profile = default_spec_profile()
    parser.add_argument(
        "--spec-profile",
        default=default_profile,
        help=f"Spec profile name/path. Defaults to {default_profile} from the profile registry.",
    )
    parser.add_argument(
        "--compile-only",
        action="store_true",
        help="Compile and collect evidence, but skip get_result.py.",
    )
    parser.add_argument(
        "--skip-compile",
        action="store_true",
        help="Skip compile_elf.py and only run/postcheck existing artifacts.",
    )
    parser.add_argument(
        "--skip-run",
        action="store_true",
        help="Skip get_result.py even when not compile-only.",
    )
    parser.add_argument(
        "--skip-env-check",
        action="store_true",
        help="Skip check_env.py. Use only when environment has already been checked in the same run context.",
    )
    parser.add_argument(
        "--env",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help=(
            "Environment override for check_env.py, compile_elf.py, and get_result.py, "
            "e.g. --env HYPTEST_SPIKE_BIN=/path/to/spike. Can be repeated."
        ),
    )
    parser.add_argument(
        "--postcheck-md-out",
        help="Optional Markdown output path for the nested case_postcheck_pack.py run.",
    )
    parser.add_argument(
        "--postcheck-json-out",
        help="Optional JSON output path for the nested case_postcheck_pack.py run.",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON report.")
    parser.add_argument("--md-out", help="Write Markdown report to this path.")
    parser.add_argument("--json-out", help="Write JSON report to this path.")
    return parser.parse_args()


def summarize_text(text: str, limit: int = 1600) -> str:
    stripped = text.strip()
    if len(stripped) <= limit:
        return stripped
    return stripped[:limit].rstrip() + "\n..."


def run_command(
    command: list[str],
    *,
    cwd: Path,
    env_overrides: dict[str, str] | None = None,
) -> dict[str, Any]:
    started = time.monotonic()
    env = os.environ.copy()
    env.update(runtime_env_overrides(env_overrides))
    completed = subprocess.run(
        command,
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    result = {
        "ok": completed.returncode == 0,
        "returncode": completed.returncode,
        "duration_seconds": round(time.monotonic() - started, 3),
        "command": " ".join(command),
        "stdout_summary": summarize_text(completed.stdout),
        "stderr_summary": summarize_text(completed.stderr),
    }
    log_file = extract_log_file(completed.stdout)
    if log_file:
        result["log_file"] = log_file
    return result


def extract_log_file(text: str) -> str | None:
    match = re.search(r"(?m)^log_file=(.+?)\s*$", text)
    return match.group(1).strip() if match else None


def run_env_check(args: argparse.Namespace, repo_root: Path, *, run_required: bool) -> dict[str, Any]:
    command = [
        sys.executable,
        str(SCRIPT_DIR / "check_env.py"),
        "--repo-root",
        str(repo_root),
        "--platform",
        args.platform,
        "--task-mode",
        "run-only" if run_required else "writeback-only",
        "--json",
    ]
    if not run_required:
        command.append("--platform-env-optional")
    command.extend(env_override_args(args.env_overrides))
    started = time.monotonic()
    completed = subprocess.run(
        command,
        cwd=str(SKILL_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    result: dict[str, Any] = {
        "ok": completed.returncode == 0,
        "returncode": completed.returncode,
        "duration_seconds": round(time.monotonic() - started, 3),
        "command": " ".join(command),
        "stdout_summary": summarize_text(completed.stdout),
        "stderr_summary": summarize_text(completed.stderr),
    }
    try:
        result["payload"] = json.loads(completed.stdout) if completed.stdout.strip() else {}
    except json.JSONDecodeError:
        result["payload"] = {}
    return result


def collect_log_snapshot(repo_root: Path, platform: str, case_name: str) -> dict[str, float]:
    base = repo_root / ".tmp" / "result_log" / platform
    if not base.is_dir():
        base = repo_root / ".tmp" / "result_log"
    if not base.is_dir():
        return {}
    snapshot: dict[str, float] = {}
    for path in base.rglob("*.log"):
        try:
            snapshot[str(path.resolve())] = path.stat().st_mtime
        except OSError:
            continue
    return snapshot


def discover_run_logs(
    repo_root: Path,
    platform: str,
    case_name: str,
    before_snapshot: dict[str, float],
    *,
    limit: int = 5,
) -> list[dict[str, Any]]:
    base = repo_root / ".tmp" / "result_log" / platform
    if not base.is_dir():
        base = repo_root / ".tmp" / "result_log"
    if not base.is_dir():
        return []
    candidates: list[Path] = []
    seen: set[Path] = set()
    for pattern in (f"{case_name}*.log", f"*{case_name}*.log"):
        for path in base.glob(pattern):
            if path.is_file() and path not in seen:
                candidates.append(path)
                seen.add(path)
    if not candidates:
        candidates = [
            path
            for path in base.rglob("*.log")
            if path.is_file() and (case_name in path.name or case_name in str(path))
        ]
    if not candidates:
        candidates = [path for path in base.rglob("*.log") if path.is_file()]
    found: list[tuple[int, float, Path]] = []
    for path in candidates:
        try:
            resolved = str(path.resolve())
            mtime = path.stat().st_mtime
        except OSError:
            continue
        before = before_snapshot.get(resolved)
        changed = before is None or mtime > before
        if not changed and case_name not in path.name and case_name not in str(path):
            continue
        contains_case = case_name in path.name or case_name in str(path)
        if changed and not contains_case:
            try:
                contains_case = case_name in path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                contains_case = False
        if changed or contains_case:
            found.append((1 if changed else 0, mtime, path))
    found.sort(key=lambda item: (item[0], item[1]), reverse=True)
    logs: list[dict[str, Any]] = []
    for changed, _mtime, path in found[:limit]:
        try:
            rel = str(path.relative_to(repo_root))
        except ValueError:
            rel = str(path)
        logs.append({"path": rel, "new_or_updated": bool(changed)})
    return logs


def add_run_log_from_command(
    repo_root: Path,
    run_log_evidence: list[dict[str, Any]],
    run_result: dict[str, Any],
) -> list[dict[str, Any]]:
    raw = run_result.get("log_file")
    if not raw:
        return run_log_evidence
    path = Path(str(raw))
    try:
        rel = str(path.relative_to(repo_root)) if path.is_absolute() else str(path)
    except ValueError:
        rel = str(path)
    if not any(item.get("path") == rel for item in run_log_evidence):
        run_log_evidence.insert(0, {"path": rel, "new_or_updated": True})
    return run_log_evidence


def run_postcheck(args: argparse.Namespace, repo_root: Path) -> dict[str, Any]:
    command = [
        sys.executable,
        str(SCRIPT_DIR / "case_postcheck_pack.py"),
        "--repo-root",
        str(repo_root),
        "--test-point-file",
        str(resolve_path(args.test_point_file)),
        "--case",
        args.case,
        "--platform",
        args.platform,
        "--spec-profile",
        args.spec_profile,
        "--json",
    ]
    if args.postcheck_md_out:
        command.extend(["--md-out", args.postcheck_md_out])
    if args.postcheck_json_out:
        command.extend(["--json-out", args.postcheck_json_out])
    started = time.monotonic()
    completed = subprocess.run(
        command,
        cwd=str(SKILL_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    result: dict[str, Any] = {
        "ok": completed.returncode == 0,
        "returncode": completed.returncode,
        "duration_seconds": round(time.monotonic() - started, 3),
        "command": " ".join(command),
        "stdout_summary": summarize_text(completed.stdout),
        "stderr_summary": summarize_text(completed.stderr),
    }
    try:
        result["payload"] = json.loads(completed.stdout) if completed.stdout.strip() else {}
    except json.JSONDecodeError:
        result["payload"] = {}
    return result


def first_latest_log(postcheck: dict[str, Any]) -> str | None:
    payload = postcheck.get("payload", {}) if isinstance(postcheck, dict) else {}
    cases = payload.get("cases", []) if isinstance(payload, dict) else []
    if not cases:
        return None
    logs = cases[0].get("latest_logs", []) if isinstance(cases[0], dict) else []
    if not logs:
        return None
    path = logs[0].get("path")
    return str(path) if path else None


def first_run_log(run_log_evidence: list[dict[str, Any]] | None) -> str | None:
    for item in run_log_evidence or []:
        path = item.get("path")
        if path:
            return str(path)
    return None


def classify_failure_log(
    repo_root: Path,
    postcheck: dict[str, Any],
    run_log_evidence: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    rel_log = first_run_log(run_log_evidence) or first_latest_log(postcheck)
    if not rel_log:
        return {
            "attempted": False,
            "reason": "no latest log found in postcheck payload",
        }
    log_path = repo_root / rel_log
    if not log_path.is_file():
        return {
            "attempted": False,
            "reason": f"latest log path not found: {rel_log}",
        }
    command = [
        sys.executable,
        str(SCRIPT_DIR / "classify_failure_log.py"),
        "--log-file",
        str(log_path),
        "--json",
    ]
    started = time.monotonic()
    completed = subprocess.run(
        command,
        cwd=str(SKILL_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    result: dict[str, Any] = {
        "attempted": True,
        "ok": completed.returncode == 0,
        "returncode": completed.returncode,
        "duration_seconds": round(time.monotonic() - started, 3),
        "command": " ".join(command),
        "log_file": str(log_path),
        "stdout_summary": summarize_text(completed.stdout),
        "stderr_summary": summarize_text(completed.stderr),
    }
    try:
        result["payload"] = json.loads(completed.stdout) if completed.stdout.strip() else {}
    except json.JSONDecodeError:
        result["payload"] = {}
    return result


def should_classify_failure(commands: dict[str, Any], evidence_requirements: dict[str, Any]) -> bool:
    run = commands.get("run")
    if run and not run.get("ok"):
        return True
    if not evidence_requirements.get("ok"):
        return True
    postcheck = commands.get("postcheck", {})
    payload = postcheck.get("payload", {}) if isinstance(postcheck, dict) else {}
    cases = payload.get("cases", []) if isinstance(payload, dict) else []
    if not cases:
        return False
    logs = cases[0].get("latest_logs", []) if isinstance(cases[0], dict) else []
    for log in logs:
        summary = log.get("summary", {})
        if summary.get("has_fail") or summary.get("has_timeout"):
            return True
    return False


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    started = time.monotonic()
    repo_root = resolve_path(args.repo_root)
    commands: dict[str, Any] = {}
    skipped: dict[str, str] = {}
    run_log_evidence: list[dict[str, Any]] = []
    run_requested = not args.compile_only and not args.skip_run

    if args.skip_env_check:
        skipped["env"] = "--skip-env-check"
    else:
        commands["env"] = run_env_check(args, repo_root, run_required=run_requested)

    if args.skip_compile:
        skipped["compile"] = "--skip-compile"
    else:
        commands["compile"] = run_command(
            [
                sys.executable,
                "compile_elf.py",
                "--plat",
                args.platform,
                "--name",
                args.case,
            ],
            cwd=repo_root,
            env_overrides=args.env_overrides,
        )

    compile_ok = args.skip_compile or commands.get("compile", {}).get("ok", False)
    env_ok = args.skip_env_check or commands.get("env", {}).get("ok", False)
    should_run = run_requested and compile_ok and env_ok
    if should_run:
        before_logs = collect_log_snapshot(repo_root, args.platform, args.case)
        commands["run"] = run_command(
            [
                sys.executable,
                "get_result.py",
                "--platform",
                args.platform,
                "--case",
                args.case,
            ],
            cwd=repo_root,
            env_overrides=args.env_overrides,
        )
        run_log_evidence = discover_run_logs(repo_root, args.platform, args.case, before_logs)
        run_log_evidence = add_run_log_from_command(
            repo_root,
            run_log_evidence,
            commands["run"],
        )
    else:
        if args.compile_only:
            skipped["run"] = "--compile-only"
        elif args.skip_run:
            skipped["run"] = "--skip-run"
        elif not compile_ok:
            skipped["run"] = "compile failed; run skipped"
        elif not env_ok:
            skipped["run"] = "environment check failed; run skipped"

    commands["postcheck"] = run_postcheck(args, repo_root)
    evidence_requirements = build_evidence_requirements(
        commands["postcheck"],
        args,
        latest_log_required=should_run,
        run_log_evidence=run_log_evidence,
    )
    failure_classification = None
    if should_classify_failure(commands, evidence_requirements):
        failure_classification = classify_failure_log(
            repo_root,
            commands["postcheck"],
            run_log_evidence,
        )

    required_steps = ["postcheck"]
    if not args.skip_env_check:
        required_steps.append("env")
    if not args.skip_compile:
        required_steps.append("compile")
    if should_run:
        required_steps.append("run")
    ok = all(commands.get(step, {}).get("ok") for step in required_steps) and evidence_requirements["ok"]

    report: dict[str, Any] = {
        "repo_root": str(repo_root),
        "test_point_file": str(resolve_path(args.test_point_file)),
        "case": args.case,
        "platform": args.platform,
        "spec_profile": args.spec_profile,
        "compile_only": bool(args.compile_only),
        "env_overrides": dict(args.env_overrides),
        "commands": commands,
        "skipped": skipped,
        "run_log_evidence": run_log_evidence,
        "evidence_requirements": evidence_requirements,
        "failure_classification": failure_classification,
        "ok": bool(ok),
        "timing": build_timing(commands, started, failure_classification),
        "next_steps": build_next_steps(commands, args, evidence_requirements),
    }
    return report


def build_evidence_requirements(
    postcheck: dict[str, Any],
    args: argparse.Namespace,
    *,
    latest_log_required: bool,
    run_log_evidence: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    payload = postcheck.get("payload", {}) if isinstance(postcheck, dict) else {}
    cases = payload.get("cases", []) if isinstance(payload, dict) else []
    case_payload = cases[0] if cases else {}
    artifacts = case_payload.get("artifacts", {}) if isinstance(case_payload, dict) else {}
    latest_logs = case_payload.get("latest_logs", []) if isinstance(case_payload, dict) else []

    requirements = {
        "artifact_elf": bool(artifacts.get("elf")),
        "latest_log": bool(latest_logs) or bool(run_log_evidence),
    }
    if not latest_log_required:
        requirements["latest_log"] = True

    return {
        "ok": all(requirements.values()),
        "requirements": requirements,
        "note": "latest_log is required only when get_result.py was actually run by this gate pack.",
    }


def build_timing(
    commands: dict[str, Any],
    started: float,
    failure_classification: dict[str, Any] | None = None,
) -> dict[str, Any]:
    by_step = {
        name: item.get("duration_seconds")
        for name, item in commands.items()
        if item.get("duration_seconds") is not None
    }
    if failure_classification and failure_classification.get("duration_seconds") is not None:
        by_step["failure_classification"] = failure_classification.get("duration_seconds")
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


def build_next_steps(
    commands: dict[str, Any],
    args: argparse.Namespace,
    evidence_requirements: dict[str, Any],
) -> list[str]:
    steps: list[str] = []
    if commands.get("env") and not commands["env"].get("ok"):
        payload = commands["env"].get("payload", {})
        issues = payload.get("issues", []) if isinstance(payload, dict) else []
        if issues:
            steps.append("Fix platform environment before running get_result.py: " + "; ".join(str(issue) for issue in issues[:3]))
        else:
            steps.append("Fix platform environment before running get_result.py.")
    if commands.get("compile") and not commands["compile"].get("ok"):
        steps.append("Fix compile_elf.py failure before running or tiering the case.")
    if commands.get("run") and not commands["run"].get("ok"):
        steps.append("Inspect get_result.py output/log; classify failure before deciding tier.")
    postcheck = commands.get("postcheck", {})
    if postcheck and not postcheck.get("ok"):
        steps.append("Inspect postcheck payload for missing writeback, register mismatch, artifacts, or logs.")
    requirements = evidence_requirements.get("requirements", {})
    if not requirements.get("artifact_elf", True):
        steps.append("Postcheck did not find the target ELF artifact; rerun compile_elf.py for this case/platform.")
    if not requirements.get("latest_log", True):
        steps.append("Postcheck did not find a target run log; rerun get_result.py for this case/platform.")
    if args.compile_only:
        steps.append("Mark Gate D=N/A(compile-only) in the final summary with the reason.")
    return steps


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# hyptest case gate pack",
        "",
        f"- HYPTEST_HOME: `{report['repo_root']}`",
        f"- test_point_file: `{report['test_point_file']}`",
        f"- case: `{report['case']}`",
        f"- platform: `{report['platform']}`",
        f"- spec_profile: `{report['spec_profile']}`",
        f"- compile_only: `{report['compile_only']}`",
        f"- overall: `{'PASS' if report['ok'] else 'FAIL'}`",
        "",
        "## Checks",
        "",
    ]
    for name, item in report["commands"].items():
        lines.append(
            f"- {'PASS' if item.get('ok') else 'FAIL'} `{name}` "
            f"({item.get('duration_seconds', '-')}s): `{item.get('command', '')}`"
        )
    if report.get("skipped"):
        lines.extend(["", "## Skipped", ""])
        for name, reason in report["skipped"].items():
            lines.append(f"- `{name}`: {reason}")
    run_logs = report.get("run_log_evidence") or []
    if run_logs:
        lines.extend(["", "## Run Log Evidence", ""])
        for log in run_logs:
            lines.append(f"- `{log.get('path')}` new_or_updated=`{log.get('new_or_updated')}`")
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
    lines.extend(["", "## Evidence Requirements", ""])
    evidence = report.get("evidence_requirements", {})
    lines.append(f"- overall: `{'PASS' if evidence.get('ok') else 'FAIL'}`")
    for name, ok in evidence.get("requirements", {}).items():
        lines.append(f"- {name}: `{'PASS' if ok else 'FAIL'}`")

    classification = report.get("failure_classification")
    if classification:
        lines.extend(["", "## Failure Classification", ""])
        lines.append(f"- attempted: `{classification.get('attempted')}`")
        if classification.get("log_file"):
            lines.append(f"- log_file: `{classification.get('log_file')}`")
        payload = classification.get("payload", {})
        if payload:
            lines.append(f"- reason_code_candidates: `{payload.get('reason_code_candidates', [])}`")
            for action in payload.get("next_actions", [])[:5]:
                lines.append(f"- next_action: {action}")
        elif classification.get("reason"):
            lines.append(f"- reason: {classification.get('reason')}")

    post_payload = report.get("commands", {}).get("postcheck", {}).get("payload", {})
    if post_payload:
        lines.extend(["", "## Postcheck Evidence", ""])
        for case in post_payload.get("cases", []):
            lines.append(f"### `{case.get('case')}`")
            lines.append(f"- definition_unique: `{case.get('definition_unique')}`")
            lines.append(f"- register_status: `{case.get('register_status')}`")
            artifacts = case.get("artifacts", {})
            lines.append(f"- artifact ELF: `{artifacts.get('elf') or 'missing'}`")
            lines.append(f"- artifact ASM: `{artifacts.get('asm') or 'missing'}`")
            logs = case.get("latest_logs", [])
            if logs:
                lines.append("- latest logs:")
                for log in logs:
                    summary = log.get("summary", {})
                    lines.append(
                        f"  - `{log.get('path')}` pass={summary.get('has_pass')} "
                        f"fail={summary.get('has_fail')} timeout={summary.get('has_timeout')}"
                    )
            else:
                lines.append("- latest logs: `none`")

    lines.extend(["", "## Next Steps", ""])
    if report.get("next_steps"):
        for step in report["next_steps"]:
            lines.append(f"- {step}")
    else:
        lines.append("- Use this pack as compile/run/postcheck evidence in the final workflow summary.")
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
    try:
        args.env_overrides = apply_env_overrides(args.env)
    except ValueError as exc:
        print(f"invalid --env: {exc}", file=sys.stderr)
        return 2
    report = build_report(args)
    write_outputs(report, args)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(report))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
