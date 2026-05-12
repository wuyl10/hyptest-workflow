#!/usr/bin/env python3
"""Build an end-to-end timing and rework ledger for one hyptest case workflow."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Summarize preflight/gate/submission timing and rework signals for one case."
    )
    parser.add_argument("--case", help="Case name override/filter.")
    parser.add_argument("--preflight-json", help="case_preflight_pack.py JSON report.")
    parser.add_argument("--gate-json", help="case_gate_pack.py JSON report.")
    parser.add_argument("--postcheck-json", help="case_postcheck_pack.py JSON report.")
    parser.add_argument("--submission-json", help="make_case_submission_card.py JSON report.")
    parser.add_argument(
        "--manual-edit-seconds",
        type=float,
        help="Optional manually measured edit/design time to include in the ledger.",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON report.")
    parser.add_argument("--md-out", help="Write Markdown report to this path.")
    parser.add_argument("--json-out", help="Write JSON report to this path.")
    return parser.parse_args()


def load_json(path_arg: str | None) -> dict[str, Any]:
    if not path_arg:
        return {}
    path = Path(path_arg).expanduser()
    if not path.is_file():
        raise FileNotFoundError(str(path))
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root is not an object: {path}")
    payload["_source_path"] = str(path)
    return payload


def first_case(postcheck: dict[str, Any], case_name: str | None) -> dict[str, Any]:
    for item in postcheck.get("cases", []):
        if case_name is None or item.get("case") == case_name:
            return item
    return {}


def postcheck_from_gate(gate: dict[str, Any]) -> dict[str, Any]:
    return gate.get("commands", {}).get("postcheck", {}).get("payload", {})


def add_step(steps: list[dict[str, Any]], name: str, seconds: Any, ok: Any = None, source: str | None = None) -> None:
    if seconds is None:
        return
    try:
        value = round(float(seconds), 3)
    except (TypeError, ValueError):
        return
    steps.append({"name": name, "seconds": value, "ok": ok, "source": source})


def cache_signal(preflight: dict[str, Any]) -> dict[str, Any]:
    cache = preflight.get("cache") or {}
    similar_cache = (
        preflight.get("commands", {})
        .get("similar_cases", {})
        .get("payload", {})
        .get("cache", {})
    )
    repo_cache = (
        preflight.get("commands", {})
        .get("repo_evidence_index", {})
        .get("payload", {})
        .get("cache", {})
    )
    return {
        "preflight_pack": {"seen": bool(cache), "hit": cache.get("hit")},
        "similar_cases": {"seen": bool(similar_cache), "hit": similar_cache.get("hit")},
        "repo_evidence_index": {"seen": bool(repo_cache), "hit": repo_cache.get("hit")},
    }


def collect_rework_signals(
    gate: dict[str, Any],
    postcheck: dict[str, Any],
    case_payload: dict[str, Any],
) -> list[dict[str, str]]:
    signals: list[dict[str, str]] = []
    compile_step = gate.get("commands", {}).get("compile", {})
    run_step = gate.get("commands", {}).get("run", {})
    postcheck_step = gate.get("commands", {}).get("postcheck", {})
    if compile_step and not compile_step.get("ok"):
        signals.append({"kind": "compile_failed", "detail": "compile_elf.py failed"})
    if run_step and not run_step.get("ok"):
        signals.append({"kind": "run_failed", "detail": "get_result.py failed"})
    if postcheck_step and not postcheck_step.get("ok"):
        signals.append({"kind": "postcheck_failed", "detail": "case_postcheck_pack.py failed"})
    evidence = gate.get("evidence_requirements") or {}
    if evidence and not evidence.get("ok"):
        missing = [
            name
            for name, ok in (evidence.get("requirements") or {}).items()
            if not ok
        ]
        signals.append({"kind": "missing_evidence", "detail": ", ".join(missing)})
    if case_payload:
        if not case_payload.get("definition_unique"):
            signals.append({"kind": "definition_not_unique", "detail": "case function definition is not unique"})
        if case_payload.get("register_status") not in {"enabled", "commented"}:
            signals.append({"kind": "register_missing", "detail": str(case_payload.get("register_status"))})
        if not case_payload.get("test_point_mentions"):
            signals.append({"kind": "writeback_missing", "detail": "case is not mentioned in test_point"})
        artifacts = case_payload.get("artifacts") or {}
        if not artifacts.get("elf"):
            signals.append({"kind": "artifact_missing", "detail": "ELF artifact missing"})
    if postcheck and not postcheck.get("ok"):
        for command_name, item in (postcheck.get("commands") or {}).items():
            if not item.get("ok"):
                signals.append({"kind": f"{command_name}_failed", "detail": item.get("stderr_summary") or item.get("stdout_summary", "")[:200]})
    return signals


def build_ledger(args: argparse.Namespace) -> dict[str, Any]:
    preflight = load_json(args.preflight_json)
    gate = load_json(args.gate_json)
    postcheck = load_json(args.postcheck_json)
    submission = load_json(args.submission_json)
    if not postcheck and gate:
        postcheck = postcheck_from_gate(gate)

    case_name = args.case or gate.get("case") or submission.get("case")
    case_payload = first_case(postcheck, case_name)
    if not case_name:
        case_name = case_payload.get("case")

    steps: list[dict[str, Any]] = []
    add_step(steps, "preflight.total", preflight.get("timing", {}).get("total_seconds"), preflight.get("ok"), preflight.get("_source_path"))
    for name, seconds in (preflight.get("timing", {}).get("by_step") or {}).items():
        add_step(steps, f"preflight.{name}", seconds, None, preflight.get("_source_path"))
    if args.manual_edit_seconds is not None:
        add_step(steps, "manual_edit", args.manual_edit_seconds, None, "manual")
    add_step(steps, "gate.total", gate.get("timing", {}).get("total_seconds"), gate.get("ok"), gate.get("_source_path"))
    for name, seconds in (gate.get("timing", {}).get("by_step") or {}).items():
        ok = gate.get("commands", {}).get(name, {}).get("ok")
        add_step(steps, f"gate.{name}", seconds, ok, gate.get("_source_path"))
    add_step(steps, "postcheck.total", postcheck.get("timing", {}).get("total_seconds"), postcheck.get("ok"), postcheck.get("_source_path"))
    for name, seconds in (postcheck.get("timing", {}).get("by_step") or {}).items():
        ok = postcheck.get("commands", {}).get(name, {}).get("ok")
        add_step(steps, f"postcheck.{name}", seconds, ok, postcheck.get("_source_path"))

    total_seconds = round(sum(float(step["seconds"]) for step in steps if "." not in step["name"] or step["name"].endswith(".total") or step["name"] == "manual_edit"), 3)
    slowest = sorted(steps, key=lambda item: float(item.get("seconds") or 0), reverse=True)[:8]
    rework = collect_rework_signals(gate, postcheck, case_payload)
    return {
        "case": case_name,
        "repo_root": gate.get("repo_root") or postcheck.get("repo_root") or preflight.get("repo_root") or submission.get("repo_root"),
        "test_point_file": gate.get("test_point_file") or postcheck.get("test_point_file") or preflight.get("test_point_file") or submission.get("test_point_file"),
        "platform": gate.get("platform") or postcheck.get("platform") or preflight.get("platform") or submission.get("platform"),
        "spec_profile": gate.get("spec_profile") or postcheck.get("spec_profile") or preflight.get("spec_profile") or submission.get("spec_profile"),
        "sources": {
            "preflight_json": preflight.get("_source_path"),
            "gate_json": gate.get("_source_path"),
            "postcheck_json": postcheck.get("_source_path"),
            "submission_json": submission.get("_source_path"),
        },
        "cache": cache_signal(preflight),
        "timing": {
            "total_observed_seconds": total_seconds,
            "steps": steps,
            "slowest_steps": slowest,
        },
        "rework_signals": rework,
        "quality_boundary": (
            "This ledger records timing and rework signals only. It does not decide "
            "default/manual/compile-only/blocked."
        ),
        "ok": not rework,
    }


def render_markdown(ledger: dict[str, Any]) -> str:
    lines = [
        "# hyptest case workflow ledger",
        "",
        f"- case: `{ledger.get('case')}`",
        f"- HYPTEST_HOME: `{ledger.get('repo_root') or ''}`",
        f"- test_point_file: `{ledger.get('test_point_file') or ''}`",
        f"- platform: `{ledger.get('platform') or ''}`",
        f"- spec_profile: `{ledger.get('spec_profile') or ''}`",
        f"- observed_total_seconds: `{ledger.get('timing', {}).get('total_observed_seconds')}`",
        f"- rework_signal_count: `{len(ledger.get('rework_signals') or [])}`",
        "",
        "## Cache",
        "",
    ]
    for name, item in (ledger.get("cache") or {}).items():
        lines.append(f"- {name}: seen=`{item.get('seen')}` hit=`{item.get('hit')}`")
    lines.extend(["", "## Slowest Steps", ""])
    steps = ledger.get("timing", {}).get("steps", [])
    if steps:
        lines.append("### All Steps")
        for step in steps:
            lines.append(
                f"- `{step.get('name')}` {step.get('seconds')}s ok=`{step.get('ok')}` source=`{step.get('source')}`"
            )
        lines.append("")
    for step in ledger.get("timing", {}).get("slowest_steps", []):
        lines.append(f"- `{step.get('name')}` {step.get('seconds')}s ok=`{step.get('ok')}`")
    lines.extend(["", "## Rework Signals", ""])
    if ledger.get("rework_signals"):
        for signal in ledger["rework_signals"]:
            lines.append(f"- {signal.get('kind')}: {signal.get('detail')}")
    else:
        lines.append("- none")
    lines.extend(["", "## Quality Boundary", "", ledger.get("quality_boundary", ""), ""])
    return "\n".join(lines)


def write_outputs(ledger: dict[str, Any], args: argparse.Namespace) -> None:
    if args.json_out:
        path = Path(args.json_out).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.md_out:
        path = Path(args.md_out).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render_markdown(ledger), encoding="utf-8")


def main() -> int:
    args = parse_args()
    try:
        ledger = build_ledger(args)
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    write_outputs(ledger, args)
    if args.json:
        print(json.dumps(ledger, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(ledger))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
