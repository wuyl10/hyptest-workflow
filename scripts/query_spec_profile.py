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
