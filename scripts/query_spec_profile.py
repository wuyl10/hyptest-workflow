#!/usr/bin/env python3
"""Query machine-readable rules from a hyptest spec profile."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from profile_utils import load_json_block, read_profile_text, window_contains
from skill_config import default_spec_profile


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Query PMA/PBMT/MMIO rules from a spec profile.")
    parser.add_argument(
        "--spec-profile",
        default=default_spec_profile(),
        help=f"Profile name or markdown path. Defaults to {default_spec_profile()} from the profile registry.",
    )
    parser.add_argument("--pma", help="PMA value to match, e.g. IO or MEM.")
    parser.add_argument("--pbmt", help="PBMT value to match, e.g. None, IO, or NC.")
    parser.add_argument(
        "--window",
        help="Exact PA window string from the profile matrix, e.g. 0x0-0x80000000.",
    )
    parser.add_argument(
        "--address",
        help="Physical address; matches any matrix window containing this address.",
    )
    parser.add_argument(
        "--responder-target",
        help="Substring to match in the MMIO responder matrix target/id.",
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Emit compact human-readable one-line summaries.",
    )
    parser.add_argument(
        "--decision-only",
        action="store_true",
        help="Print only matching default_decision values, one per line.",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON report.")
    parser.add_argument(
        "--nongate-summary",
        action="store_true",
        help=(
            "Emit a machine-readable summary of Spike-nongate scenarios for this profile: "
            "(a) the `hyptest-nongate-keywords` JSON block (if present in the profile), and "
            "(b) the set of PMA/PBMT rows with spike_gate_applicable=false. Intended for bug "
            "hunt tasks so agents can check target_module against the nongate surface without "
            "re-reading the full profile markdown."
        ),
    )
    parser.add_argument(
        "--match-module",
        help=(
            "Together with --nongate-summary: return only nongate categories whose keyword "
            "matches the given target_module name (substring, case-insensitive)."
        ),
    )
    return parser.parse_args()


def norm(raw: str | None) -> str | None:
    return raw.lower() if raw is not None else None


def match_pma_pbmt_row(row: dict[str, Any], args: argparse.Namespace) -> bool:
    if args.pma and norm(str(row.get("pma"))) != norm(args.pma):
        return False
    if args.pbmt and norm(str(row.get("pbmt"))) != norm(args.pbmt):
        return False
    if args.window and str(row.get("window")) != args.window:
        return False
    if args.address and not window_contains(str(row.get("window", "")), args.address):
        return False
    return True


def match_responder_row(row: dict[str, Any], target: str) -> bool:
    haystack = f"{row.get('id', '')} {row.get('target', '')}".lower()
    return target.lower() in haystack


def format_bool(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def pma_summary(row: dict[str, Any]) -> str:
    fields = [
        f"id={row.get('id')}",
        f"window={row.get('window')}",
        f"pma={row.get('pma')}",
        f"pbmt={row.get('pbmt')}",
        f"allowed={format_bool(row.get('allowed'))}",
        f"spike_gate_applicable={format_bool(row.get('spike_gate_applicable'))}",
        f"responder_required={format_bool(row.get('responder_required'))}",
        f"default_decision={row.get('default_decision')}",
    ]
    responder_status = row.get("responder_status")
    if responder_status is not None:
        fields.insert(-1, f"responder_status={responder_status}")
    return " ".join(fields)


def responder_summary(row: dict[str, Any]) -> str:
    fields = [
        f"id={row.get('id')}",
        f"target={row.get('target')}",
        f"type={row.get('responder_type')}",
        f"memory_like_scratch={format_bool(row.get('memory_like_scratch'))}",
        f"default_decision={row.get('default_decision')}",
    ]
    return " ".join(fields)


def nongate_summary(
    text: str,
    pma_rows: list[dict[str, Any]],
    responder_rows: list[dict[str, Any]],
    match_module: str | None = None,
) -> dict[str, Any]:
    """Collect Spike-nongate keywords and PMA/PBMT rows for quick bug-hunt lookup."""
    try:
        keywords = load_json_block(text, "hyptest-nongate-keywords")
        if not isinstance(keywords, list):
            keywords = []
    except (ValueError, json.JSONDecodeError):
        keywords = []

    nongate_pma = [row for row in pma_rows if row.get("spike_gate_applicable") is False]
    nongate_responder = [
        row for row in responder_rows if row.get("spike_gate_applicable") is False
    ]

    def matches_module(keyword_entry: Any) -> bool:
        if not match_module:
            return True
        needle = match_module.lower().replace("_", "").replace("-", "")
        hay_parts: list[str] = []
        if isinstance(keyword_entry, dict):
            for field in ("category", "keywords", "module_hints", "note"):
                value = keyword_entry.get(field)
                if isinstance(value, str):
                    hay_parts.append(value)
                elif isinstance(value, list):
                    hay_parts.extend(str(v) for v in value)
        elif isinstance(keyword_entry, str):
            hay_parts.append(keyword_entry)
        hay = " ".join(hay_parts).lower().replace("_", "").replace("-", "")
        return needle in hay

    filtered = [entry for entry in keywords if matches_module(entry)]

    return {
        "match_module": match_module,
        "keyword_category_count": len(filtered),
        "keyword_categories": filtered,
        "nongate_pma_match_count": len(nongate_pma),
        "nongate_pma_rows": nongate_pma,
        "nongate_responder_match_count": len(nongate_responder),
        "nongate_responder_rows": nongate_responder,
    }


def render_nongate_summary_text(summary: dict[str, Any]) -> str:
    lines: list[str] = []
    if summary.get("match_module"):
        lines.append(f"nongate summary (module filter: {summary['match_module']})")
    else:
        lines.append("nongate summary (no module filter)")
    categories = summary.get("keyword_categories", [])
    if categories:
        lines.append(f"nongate keyword categories: {len(categories)}")
        for entry in categories:
            if isinstance(entry, dict):
                cat = entry.get("category", "<unnamed>")
                kws = entry.get("keywords") or []
                lines.append(f"  - {cat}: {', '.join(str(k) for k in kws[:6])}")
            else:
                lines.append(f"  - {entry}")
    else:
        lines.append("nongate keyword categories: 0 (profile has no hyptest-nongate-keywords block or no match)")
    if summary.get("nongate_pma_match_count"):
        lines.append(f"spike_gate_applicable=false PMA/PBMT rows: {summary['nongate_pma_match_count']}")
    if summary.get("nongate_responder_match_count"):
        lines.append(
            f"spike_gate_applicable=false MMIO responder rows: {summary['nongate_responder_match_count']}"
        )
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    try:
        profile_path, text = read_profile_text(args.spec_profile)
        pma_rows = load_json_block(text, "hyptest-pma-pbmt-matrix")
        responder_rows = load_json_block(text, "hyptest-mmio-responder-matrix")
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        payload = {"ok": False, "error": str(exc)}
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(f"FAIL query spec profile: {exc}", file=sys.stderr)
        return 2

    pma_matches = [row for row in pma_rows if match_pma_pbmt_row(row, args)]
    responder_matches = []
    if args.responder_target:
        responder_matches = [
            row for row in responder_rows if match_responder_row(row, args.responder_target)
        ]

    if args.nongate_summary:
        summary = nongate_summary(text, pma_rows, responder_rows, args.match_module)
        payload = {
            "ok": True,
            "profile": args.spec_profile,
            "profile_path": str(profile_path),
            "nongate": summary,
        }
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(f"profile: {profile_path}")
            print(render_nongate_summary_text(summary))
        return 0

    payload = {
        "ok": True,
        "profile": args.spec_profile,
        "profile_path": str(profile_path),
        "pma_pbmt_match_count": len(pma_matches),
        "pma_pbmt_matches": pma_matches,
        "responder_match_count": len(responder_matches),
        "responder_matches": responder_matches,
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    if args.decision_only:
        decisions: list[str] = []
        seen = set()
        for row in [*pma_matches, *responder_matches]:
            decision = row.get("default_decision")
            if decision is None:
                continue
            decision_text = str(decision)
            if decision_text in seen:
                continue
            seen.add(decision_text)
            decisions.append(decision_text)
        if decisions:
            print("\n".join(decisions))
        else:
            print("no_decision_match")
        return 0

    print(f"profile: {profile_path}")
    if args.summary:
        if pma_matches:
            print(f"pma_pbmt_matches={len(pma_matches)}")
            for row in pma_matches:
                print(f"  {pma_summary(row)}")
        if responder_matches:
            print(f"responder_matches={len(responder_matches)}")
            for row in responder_matches:
                print(f"  {responder_summary(row)}")
        if not pma_matches and not responder_matches:
            print("no matches")
        return 0

    if args.pma or args.pbmt or args.window or args.address:
        print(f"pma_pbmt_matches: {len(pma_matches)}")
        for row in pma_matches:
            print(
                "  - "
                f"id={row.get('id')} window={row.get('window')} "
                f"pma={row.get('pma')} pbmt={row.get('pbmt')} "
                f"allowed={row.get('allowed')} "
                f"spike_gate_applicable={row.get('spike_gate_applicable')} "
                f"responder_required={row.get('responder_required')} "
                f"default_decision={row.get('default_decision')}"
            )
    if args.responder_target:
        print(f"responder_matches: {len(responder_matches)}")
        for row in responder_matches:
            print(
                "  - "
                f"id={row.get('id')} target={row.get('target')} "
                f"type={row.get('responder_type')} "
                f"memory_like_scratch={row.get('memory_like_scratch')} "
                f"default_decision={row.get('default_decision')}"
            )
    if not pma_matches and not responder_matches:
        print("no matches")
    return 0


if __name__ == "__main__":
    sys.exit(main())
