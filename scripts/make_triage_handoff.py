#!/usr/bin/env python3
"""Build a workflow-to-triage handoff JSON from a failure log."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from classify_failure_log import classify
from skill_config import default_spec_profile
from validate_triage_handoff import validate as validate_handoff


EXCPT_RE = re.compile(r"excpt\.(triggered|cause|tval2?|tinst|priv)\s*=\s*([^\s]+)")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a hyptest triage handoff card.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--log", help="Inline log text.")
    source.add_argument("--log-file", help="Path to log file.")
    parser.add_argument("--platform", default="unknown", help="spike/linknan/unknown.")
    parser.add_argument(
        "--spec-profile",
        default=default_spec_profile(),
        help=f"Spec profile name. Defaults to {default_spec_profile()} from the profile registry.",
    )
    parser.add_argument("--next-single-run", help="Suggested single-run command.")
    parser.add_argument(
        "--runner-mode",
        choices=["spike-gate", "linknan-difftest", "linknan-no-diff"],
        help="Optional triage-to-workflow runner request mode.",
    )
    parser.add_argument("--compile-plat", choices=["spike", "linknan"], help="Runner request compile platform.")
    parser.add_argument("--run-platform", choices=["spike", "linknan"], help="Runner request run platform.")
    parser.add_argument(
        "--difftest-mode",
        choices=["not-applicable", "enabled", "disabled"],
        help="Runner request difftest mode.",
    )
    parser.add_argument(
        "--include-commented",
        action="store_true",
        help="Runner request should include commented registrations.",
    )
    parser.add_argument(
        "--cleanup-allowed",
        action="store_true",
        help="Runner request evidence may be used for cleanup/removal decisions.",
    )
    parser.add_argument("--runner-purpose", help="Short purpose for the runner request.")
    parser.add_argument("--log-path", action="append", default=[], help="Related log path.")
    parser.add_argument("--waveform-path", help="Related FSDB/VCD/FST path for downstream triage.")
    parser.add_argument("--rtl-root", help="RTL/source root to pass to waveform triage.")
    parser.add_argument("--top-module", help="Top module name for waveform triage.")
    parser.add_argument("--debug-target", help="Concrete waveform debug target or signal question.")
    parser.add_argument("--time-window", help="Known failing time window or cycle range.")
    parser.add_argument("--expected-behavior", help="Expected behavior to check in waveform triage.")
    parser.add_argument("--observed-behavior", help="Observed behavior to contrast with expected behavior.")
    parser.add_argument("--waveform-report", help="Suggested or existing waveform-debug report.md path.")
    parser.add_argument(
        "--no-validate",
        action="store_true",
        help="Emit the generated handoff without validating it against the bundled schema.",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON only.")
    return parser.parse_args()


def read_log(args: argparse.Namespace) -> tuple[str, list[str]]:
    if args.log_file:
        path = Path(args.log_file).expanduser()
        return path.read_text(encoding="utf-8", errors="ignore"), [str(path)]
    return args.log or "", []


def find_value(pattern: str, text: str) -> str | None:
    match = re.search(pattern, text)
    return match.group(1).strip() if match else None


def waveform_context(args: argparse.Namespace) -> dict[str, str | None]:
    return {
        "waveform_path": args.waveform_path,
        "rtl_root": args.rtl_root,
        "top_module": args.top_module,
        "debug_target": args.debug_target,
        "time_window": args.time_window,
        "expected_behavior": args.expected_behavior,
        "observed_behavior": args.observed_behavior,
        "suggested_waveform_report": args.waveform_report,
    }


def has_waveform_context(context: dict[str, str | None]) -> bool:
    return any(value for value in context.values())


def runner_request(args: argparse.Namespace) -> dict[str, object] | None:
    if not args.runner_mode:
        return None
    mode = args.runner_mode
    if mode == "spike-gate":
        compile_plat = args.compile_plat or "spike"
        run_platform = args.run_platform or "spike"
        difftest_mode = args.difftest_mode or "not-applicable"
    elif mode == "linknan-no-diff":
        compile_plat = args.compile_plat or "linknan"
        run_platform = args.run_platform or "linknan"
        difftest_mode = args.difftest_mode or "disabled"
    else:
        compile_plat = args.compile_plat or "linknan"
        run_platform = args.run_platform or "linknan"
        difftest_mode = args.difftest_mode or "enabled"
    return {
        "runner_mode": mode,
        "compile_plat": compile_plat,
        "run_platform": run_platform,
        "difftest_mode": difftest_mode,
        "include_commented": bool(args.include_commented),
        "cleanup_allowed": bool(args.cleanup_allowed),
        "purpose": args.runner_purpose,
    }


def runner_arg_combo_errors(
    mode: str | None,
    compile_plat: str | None,
    run_platform: str | None,
    difftest_mode: str | None,
) -> list[str]:
    if mode is None:
        return []
    expected = {
        "spike-gate": ("spike", "spike", "not-applicable"),
        "linknan-difftest": ("linknan", "linknan", "enabled"),
        "linknan-no-diff": ("linknan", "linknan", "disabled"),
    }[mode]
    actual = (
        compile_plat or expected[0],
        run_platform or expected[1],
        difftest_mode or expected[2],
    )
    if actual == expected:
        return []
    return [
        f"{mode} runner_request must use {expected[0]}/{expected[1]}/{expected[2]}; "
        f"got {actual[0]}/{actual[1]}/{actual[2]}"
    ]


def validate_runner_args(args: argparse.Namespace) -> list[str]:
    if args.runner_mode:
        return runner_arg_combo_errors(
            args.runner_mode,
            args.compile_plat,
            args.run_platform,
            args.difftest_mode,
        )
    partial_args = []
    for attr, flag in [
        ("compile_plat", "--compile-plat"),
        ("run_platform", "--run-platform"),
        ("difftest_mode", "--difftest-mode"),
        ("include_commented", "--include-commented"),
        ("cleanup_allowed", "--cleanup-allowed"),
        ("runner_purpose", "--runner-purpose"),
    ]:
        if getattr(args, attr):
            partial_args.append(flag)
    if not partial_args:
        return []
    return [
        "runner request arguments require explicit --runner-mode; got "
        + ", ".join(partial_args)
    ]


def main() -> int:
    args = parse_args()
    runner_arg_errors = validate_runner_args(args)
    if runner_arg_errors:
        for error in runner_arg_errors:
            print(error, file=sys.stderr)
        return 2
    try:
        text, implicit_paths = read_log(args)
    except OSError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    classified = classify(text, spec_profile=args.spec_profile)
    excpt_dump = {match.group(1): match.group(2) for match in EXCPT_RE.finditer(text)}
    wave_ctx = waveform_context(args)
    classifier_wants_waveform = any(
        token in " ".join(classified.get("next_actions", [])).lower()
        for token in ["fsdb", "wave"]
    )
    handoff = {
        "case_name": classified.get("case_name"),
        "case_names": classified.get("case_names", []),
        "platform": args.platform,
        "spec_profile": args.spec_profile,
        "scenario": classified.get("scenario", []),
        "assert_site": classified.get("assert_site"),
        "assert_expr": classified.get("assert_expr"),
        "exception_observed": classified.get("exception_observed", {}),
        "excpt_dump": excpt_dump,
        "log_markers": classified.get("log_markers", {}),
        "runner_context": classified.get("runner_context", {}),
        "error_points": classified.get("error_points", []),
        "reason_code_candidates": classified.get("reason_code_candidates", []),
        "reason_code_details": classified.get("reason_code_details", []),
        "next_single_run": args.next_single_run,
        "runner_request": runner_request(args),
        "waveform_needed": classifier_wants_waveform or has_waveform_context(wave_ctx),
        "waveform_context": wave_ctx,
        "log_paths": [*implicit_paths, *args.log_path],
    }
    if not args.no_validate:
        validation = validate_handoff(handoff)
        if not validation["ok"]:
            print("generated handoff does not satisfy triage schema:", file=sys.stderr)
            for issue in validation["issues"]:
                print(f"  - {issue}", file=sys.stderr)
            return 1
    if args.json:
        print(json.dumps(handoff, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(handoff, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
