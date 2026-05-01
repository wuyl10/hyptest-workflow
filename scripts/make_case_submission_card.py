#!/usr/bin/env python3
"""Create a submission evidence card from hyptest workflow pack JSON files."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Summarize preflight/gate/postcheck JSON evidence into a final delivery card."
    )
    parser.add_argument("--preflight-json", help="case_preflight_pack.py JSON report.")
    parser.add_argument("--gate-json", help="case_gate_pack.py JSON report.")
    parser.add_argument("--postcheck-json", help="case_postcheck_pack.py JSON report.")
    parser.add_argument("--case", help="Optional case name override/filter.")
    parser.add_argument(
        "--emit-final-draft",
        action="store_true",
        help="Add a final-summary draft section. It still does not decide the tier.",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON card.")
    parser.add_argument("--md-out", help="Write Markdown card to this path.")
    parser.add_argument("--json-out", help="Write JSON card to this path.")
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


def first_case_payload(postcheck: dict[str, Any], case_name: str | None) -> dict[str, Any]:
    for item in postcheck.get("cases", []):
        if case_name is None or item.get("case") == case_name:
            return item
    return {}


def postcheck_from_gate(gate: dict[str, Any]) -> dict[str, Any]:
    return gate.get("commands", {}).get("postcheck", {}).get("payload", {})


def command_summary(payload: dict[str, Any], name: str) -> dict[str, Any]:
    item = payload.get("commands", {}).get(name, {})
    return {
        "ok": item.get("ok"),
        "returncode": item.get("returncode"),
        "duration_seconds": item.get("duration_seconds"),
        "command": item.get("command"),
    }


def collect_similar_cases(preflight: dict[str, Any]) -> list[dict[str, Any]]:
    similar = preflight.get("commands", {}).get("similar_cases", {}).get("payload", {})
    results = similar.get("top_results") or similar.get("results") or []
    collected = []
    for item in results[:5]:
        collected.append(
            {
                "case_name": item.get("case_name"),
                "file": item.get("file"),
                "line": item.get("line"),
                "score": item.get("score"),
                "register_status": item.get("register_status"),
                "reference_role": item.get("reference_role"),
                "matched_terms": item.get("matched_terms", [])[:12],
            }
        )
    return collected


def build_card(args: argparse.Namespace) -> dict[str, Any]:
    preflight = load_json(args.preflight_json)
    gate = load_json(args.gate_json)
    postcheck = load_json(args.postcheck_json)
    if not postcheck and gate:
        postcheck = postcheck_from_gate(gate)

    case_name = args.case or gate.get("case")
    case_payload = first_case_payload(postcheck, case_name)
    if not case_name:
        case_name = case_payload.get("case")

    card = {
        "case": case_name,
        "repo_root": gate.get("repo_root") or postcheck.get("repo_root") or preflight.get("repo_root"),
        "test_point_file": gate.get("test_point_file")
        or postcheck.get("test_point_file")
        or preflight.get("test_point_file"),
        "platform": gate.get("platform") or postcheck.get("platform") or preflight.get("platform"),
        "spec_profile": gate.get("spec_profile")
        or postcheck.get("spec_profile")
        or preflight.get("spec_profile"),
        "sources": {
            "preflight_json": preflight.get("_source_path"),
            "gate_json": gate.get("_source_path"),
            "postcheck_json": postcheck.get("_source_path"),
        },
        "preflight": {
            "ok": preflight.get("ok"),
            "cache": preflight.get("cache"),
            "similar_cases": collect_similar_cases(preflight),
            "retrieval_status": preflight.get("commands", {})
            .get("similar_cases", {})
            .get("payload", {})
            .get("retrieval_status"),
        },
        "gate": {
            "ok": gate.get("ok"),
            "compile": command_summary(gate, "compile"),
            "run": command_summary(gate, "run"),
            "postcheck": command_summary(gate, "postcheck"),
            "skipped": gate.get("skipped", {}),
            "evidence_requirements": gate.get("evidence_requirements"),
            "timing": gate.get("timing"),
        },
        "postcheck": {
            "ok": postcheck.get("ok"),
            "timing": postcheck.get("timing"),
            "case": {
                "definition_unique": case_payload.get("definition_unique"),
                "definitions": case_payload.get("definitions", []),
                "register_status": case_payload.get("register_status"),
                "artifacts": case_payload.get("artifacts", {}),
                "latest_logs": case_payload.get("latest_logs", []),
                "test_point_mentions": case_payload.get("test_point_mentions", []),
            },
        },
        "decision_note": (
            "This card summarizes evidence only. Final default/manual/compile-only/blocked "
            "tiering still requires profile, Spike gate, logs, and tiering rules."
        ),
    }
    card["ready_for_human_tiering"] = bool(
        case_name
        and card["postcheck"]["case"]["definition_unique"]
        and card["postcheck"]["case"]["register_status"] in {"enabled", "commented"}
        and card["postcheck"]["case"]["test_point_mentions"]
        and card["postcheck"]["case"]["artifacts"].get("elf")
    )
    if args.emit_final_draft:
        card["final_summary_draft"] = build_final_summary_draft(card)
    return card


def format_bool(value: Any) -> str:
    if value is True:
        return "PASS"
    if value is False:
        return "FAIL"
    return "N/A"


def build_final_summary_draft(card: dict[str, Any]) -> dict[str, Any]:
    case_info = card.get("postcheck", {}).get("case", {})
    artifacts = case_info.get("artifacts") or {}
    logs = case_info.get("latest_logs") or []
    similar = card.get("preflight", {}).get("similar_cases") or []
    gate = card.get("gate", {})
    compile_step = gate.get("compile") or {}
    run_step = gate.get("run") or {}
    skipped = gate.get("skipped") or {}
    return {
        "changed_case": card.get("case"),
        "spec_profile": card.get("spec_profile"),
        "unique_evidence": {
            "definition_unique": case_info.get("definition_unique"),
            "register_status": case_info.get("register_status"),
            "similar_case_count": len(similar),
            "top_similar_cases": [
                {
                    "case_name": item.get("case_name"),
                    "file": item.get("file"),
                    "line": item.get("line"),
                    "score": item.get("score"),
                }
                for item in similar[:3]
            ],
        },
        "compile_result": {
            "status": format_bool(compile_step.get("ok")),
            "command": compile_step.get("command"),
            "artifact_elf": artifacts.get("elf"),
            "artifact_asm": artifacts.get("asm"),
        },
        "run_result": {
            "status": format_bool(run_step.get("ok")),
            "command": run_step.get("command"),
            "skipped": skipped.get("run"),
            "latest_logs": [item.get("path") for item in logs[:5]],
        },
        "writeback_result": {
            "test_point_mentions": case_info.get("test_point_mentions", []),
            "register_status": case_info.get("register_status"),
        },
        "decision_placeholder": (
            "decision_final must be filled by the workflow after checking profile, "
            "Spike gate applicability, logs, and tiering rules."
        ),
    }


def render_markdown(card: dict[str, Any]) -> str:
    case = card.get("case") or "<unknown>"
    lines = [
        "# hyptest case submission evidence card",
        "",
        f"- case: `{case}`",
        f"- HYPTEST_HOME: `{card.get('repo_root') or ''}`",
        f"- test_point_file: `{card.get('test_point_file') or ''}`",
        f"- platform: `{card.get('platform') or ''}`",
        f"- spec_profile: `{card.get('spec_profile') or ''}`",
        f"- ready_for_human_tiering: `{card.get('ready_for_human_tiering')}`",
        "",
        "## Source Reports",
        "",
    ]
    for name, path in card.get("sources", {}).items():
        if path:
            lines.append(f"- {name}: `{path}`")

    lines.extend(["", "## Preflight", ""])
    preflight = card.get("preflight", {})
    lines.append(f"- ok: `{preflight.get('ok')}`")
    cache = preflight.get("cache") or {}
    if cache:
        lines.append(f"- cache_hit: `{cache.get('hit')}`")
    lines.append(f"- retrieval_status: `{preflight.get('retrieval_status')}`")
    similar = preflight.get("similar_cases") or []
    if similar:
        lines.append("- similar cases:")
        for item in similar[:5]:
            lines.append(
                f"  - `{item.get('case_name')}` {item.get('file')}:{item.get('line')} "
                f"score={item.get('score')} status={item.get('register_status')}"
            )
    else:
        lines.append("- similar cases: `none`")

    lines.extend(["", "## Gate", ""])
    gate = card.get("gate", {})
    lines.append(f"- ok: `{gate.get('ok')}`")
    for step in ("compile", "run", "postcheck"):
        item = gate.get(step) or {}
        if item.get("command"):
            lines.append(
                f"- {step}: ok=`{item.get('ok')}` rc=`{item.get('returncode')}` "
                f"time=`{item.get('duration_seconds')}`"
            )
    evidence = gate.get("evidence_requirements") or {}
    if evidence:
        lines.append(f"- evidence_requirements: `{evidence.get('ok')}`")
        for name, ok in (evidence.get("requirements") or {}).items():
            lines.append(f"  - {name}: `{ok}`")
    timing = gate.get("timing") or {}
    if timing:
        lines.append(f"- timing.total_seconds: `{timing.get('total_seconds')}`")

    lines.extend(["", "## Postcheck", ""])
    postcheck = card.get("postcheck", {})
    lines.append(f"- ok: `{postcheck.get('ok')}`")
    case_info = postcheck.get("case") or {}
    lines.append(f"- definition_unique: `{case_info.get('definition_unique')}`")
    for definition in case_info.get("definitions", []):
        lines.append(f"  - definition: `{definition.get('path')}:{definition.get('line')}`")
    lines.append(f"- register_status: `{case_info.get('register_status')}`")
    artifacts = case_info.get("artifacts") or {}
    lines.append(f"- artifact ELF: `{artifacts.get('elf') or 'missing'}`")
    lines.append(f"- artifact ASM: `{artifacts.get('asm') or 'missing'}`")
    logs = case_info.get("latest_logs") or []
    if logs:
        lines.append("- latest logs:")
        for log in logs[:5]:
            summary = log.get("summary", {})
            lines.append(
                f"  - `{log.get('path')}` pass={summary.get('has_pass')} "
                f"fail={summary.get('has_fail')} timeout={summary.get('has_timeout')}"
            )
    else:
        lines.append("- latest logs: `none`")
    mentions = case_info.get("test_point_mentions") or []
    if mentions:
        lines.append("- test_point mentions:")
        for mention in mentions:
            lines.append(f"  - line {mention.get('line')}: `{mention.get('text')}`")
    else:
        lines.append("- test_point mentions: `none`")

    lines.extend(["", "## Decision Boundary", "", card.get("decision_note", ""), ""])
    draft = card.get("final_summary_draft")
    if draft:
        lines.extend(["## Final Summary Draft", ""])
        lines.append(f"- case: `{draft.get('changed_case')}`")
        lines.append(f"- spec_profile: `{draft.get('spec_profile')}`")
        unique = draft.get("unique_evidence") or {}
        lines.append(f"- definition_unique: `{unique.get('definition_unique')}`")
        lines.append(f"- register_status: `{unique.get('register_status')}`")
        compile_result = draft.get("compile_result") or {}
        lines.append(
            f"- compile: `{compile_result.get('status')}` artifact=`{compile_result.get('artifact_elf') or 'missing'}`"
        )
        run_result = draft.get("run_result") or {}
        lines.append(
            f"- run: `{run_result.get('status')}` skipped=`{run_result.get('skipped')}`"
        )
        if run_result.get("latest_logs"):
            for log in run_result["latest_logs"]:
                lines.append(f"  - log: `{log}`")
        writeback = draft.get("writeback_result") or {}
        mentions = writeback.get("test_point_mentions") or []
        lines.append(f"- test_point_mentions: `{len(mentions)}`")
        lines.append(f"- decision_final: `<manual fill>`")
        lines.append(f"- note: {draft.get('decision_placeholder')}")
        lines.append("")
    return "\n".join(lines)


def write_outputs(card: dict[str, Any], args: argparse.Namespace) -> None:
    if args.json_out:
        path = Path(args.json_out).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(card, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.md_out:
        path = Path(args.md_out).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render_markdown(card), encoding="utf-8")


def main() -> int:
    args = parse_args()
    try:
        card = build_card(args)
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    write_outputs(card, args)
    if args.json:
        print(json.dumps(card, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(card))
    return 0 if card.get("ready_for_human_tiering") else 1


if __name__ == "__main__":
    raise SystemExit(main())
