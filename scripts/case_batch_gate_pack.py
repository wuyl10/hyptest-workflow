#!/usr/bin/env python3
"""Run case_gate_pack.py for multiple cases while preserving per-case evidence."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from skill_config import default_spec_profile, resolve_path
from workflow_paths import workflow_report_dir


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compile/run multiple hyptest cases and collect independent gate evidence."
    )
    parser.add_argument("--repo-root", required=True, help="Path to hyptest repo root.")
    parser.add_argument("--test-point-file", required=True, help="Path to test_point markdown file.")
    parser.add_argument("--case", action="append", required=True, help="Case name; repeat for 1-3 cases.")
    parser.add_argument("--platform", default="spike", choices=["spike", "linknan"], help="Target platform.")
    default_profile = default_spec_profile()
    parser.add_argument(
        "--spec-profile",
        default=default_profile,
        help=f"Spec profile name/path. Defaults to {default_profile} from the profile registry.",
    )
    parser.add_argument("--compile-only", action="store_true", help="Pass --compile-only to each gate.")
    parser.add_argument("--skip-compile", action="store_true", help="Pass --skip-compile to each gate.")
    parser.add_argument("--skip-run", action="store_true", help="Pass --skip-run to each gate.")
    parser.add_argument(
        "--env",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="Pass environment override to each case gate, e.g. --env HYPTEST_SPIKE_BIN=/path/to/spike.",
    )
    parser.add_argument(
        "--parallel",
        action="store_true",
        help=(
            "Run per-case gates in parallel. Use only when the target repo's compile/run outputs "
            "are known to be isolated for these cases."
        ),
    )
    parser.add_argument(
        "--report-dir",
        help="Directory for per-case gate/postcheck reports. Default: <repo-root>/.hyptest_workflow_skill/reports",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON report.")
    parser.add_argument("--md-out", help="Write Markdown report to this path.")
    parser.add_argument("--json-out", help="Write JSON report to this path.")
    return parser.parse_args()


def safe_name(case_name: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in case_name)


def summarize_text(text: str, limit: int = 1600) -> str:
    stripped = text.strip()
    if len(stripped) <= limit:
        return stripped
    return stripped[:limit].rstrip() + "\n..."


def run_case(args: argparse.Namespace, case_name: str) -> dict[str, Any]:
    repo_root = resolve_path(args.repo_root)
    report_dir = workflow_report_dir(repo_root, args.report_dir)
    stem = safe_name(case_name)
    command = [
        sys.executable,
        str(SCRIPT_DIR / "case_gate_pack.py"),
        "--repo-root",
        args.repo_root,
        "--test-point-file",
        args.test_point_file,
        "--case",
        case_name,
        "--platform",
        args.platform,
        "--spec-profile",
        args.spec_profile,
        "--json",
        "--json-out",
        str(report_dir / f"case_gate_{stem}_{args.platform}.json"),
        "--md-out",
        str(report_dir / f"case_gate_{stem}_{args.platform}.md"),
        "--postcheck-json-out",
        str(report_dir / f"case_postcheck_{stem}_{args.platform}.json"),
        "--postcheck-md-out",
        str(report_dir / f"case_postcheck_{stem}_{args.platform}.md"),
    ]
    if args.compile_only:
        command.append("--compile-only")
    if args.skip_compile:
        command.append("--skip-compile")
    if args.skip_run:
        command.append("--skip-run")
    for item in args.env:
        command.extend(["--env", item])

    started = time.monotonic()
    completed = subprocess.run(command, cwd=str(SKILL_ROOT), capture_output=True, text=True, check=False)
    result: dict[str, Any] = {
        "case": case_name,
        "ok": completed.returncode == 0,
        "returncode": completed.returncode,
        "duration_seconds": round(time.monotonic() - started, 3),
        "command": " ".join(command),
        "stdout_summary": summarize_text(completed.stdout),
        "stderr_summary": summarize_text(completed.stderr),
        "report_json": str(report_dir / f"case_gate_{stem}_{args.platform}.json"),
        "report_md": str(report_dir / f"case_gate_{stem}_{args.platform}.md"),
        "postcheck_json": str(report_dir / f"case_postcheck_{stem}_{args.platform}.json"),
        "postcheck_md": str(report_dir / f"case_postcheck_{stem}_{args.platform}.md"),
    }
    try:
        result["payload"] = json.loads(completed.stdout) if completed.stdout.strip() else {}
    except json.JSONDecodeError:
        result["payload"] = {}
    return result


def run_cases(args: argparse.Namespace, cases: list[str]) -> dict[str, Any]:
    results: dict[str, Any] = {}
    if args.parallel and len(cases) > 1:
        with ThreadPoolExecutor(max_workers=min(len(cases), 3)) as executor:
            future_to_case = {executor.submit(run_case, args, case): case for case in cases}
            for future in as_completed(future_to_case):
                case = future_to_case[future]
                results[case] = future.result()
    else:
        for case in cases:
            results[case] = run_case(args, case)
    return {case: results[case] for case in cases}


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    started = time.monotonic()
    cases = list(dict.fromkeys(args.case))
    case_results = run_cases(args, cases)
    by_step = {case: item.get("duration_seconds") for case, item in case_results.items()}
    return {
        "repo_root": str(resolve_path(args.repo_root)),
        "test_point_file": str(resolve_path(args.test_point_file)),
        "platform": args.platform,
        "spec_profile": args.spec_profile,
        "cases": cases,
        "parallel": bool(args.parallel),
        "ok": all(item.get("ok") for item in case_results.values()),
        "case_results": case_results,
        "timing": {
            "total_seconds": round(time.monotonic() - started, 3),
            "by_step": by_step,
            "slowest_steps": [
                {"name": case, "seconds": seconds}
                for case, seconds in sorted(
                    by_step.items(),
                    key=lambda item: float(item[1] or 0),
                    reverse=True,
                )
            ],
        },
        "decision_note": (
            "This pack preserves per-case gate evidence. It does not merge cases into a "
            "single default/manual/compile-only decision."
        ),
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# hyptest batch case gate pack",
        "",
        f"- HYPTEST_HOME: `{report['repo_root']}`",
        f"- test_point_file: `{report['test_point_file']}`",
        f"- platform: `{report['platform']}`",
        f"- spec_profile: `{report['spec_profile']}`",
        f"- cases: `{', '.join(report['cases'])}`",
        f"- parallel: `{report['parallel']}`",
        f"- overall: `{'PASS' if report['ok'] else 'FAIL'}`",
        "",
        "## Case Results",
        "",
    ]
    for case, item in report.get("case_results", {}).items():
        lines.append(
            f"- `{case}`: ok=`{item.get('ok')}` rc=`{item.get('returncode')}` "
            f"time=`{item.get('duration_seconds')}` report=`{item.get('report_json')}`"
        )
        payload = item.get("payload", {})
        logs = payload.get("run_log_evidence") or []
        for log in logs[:3]:
            lines.append(f"  - run_log: `{log.get('path')}` new_or_updated=`{log.get('new_or_updated')}`")
    lines.extend(["", "## Timing", ""])
    timing = report.get("timing", {})
    lines.append(f"- total_seconds: `{timing.get('total_seconds')}`")
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
    lines.extend(["", "## Decision Boundary", "", report.get("decision_note", ""), ""])
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
