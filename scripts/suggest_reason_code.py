#!/usr/bin/env python3
"""Suggest hyptest reason codes from a short symptom string."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parent

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Suggest reason_code candidates.")
    parser.add_argument(
        "--symptom",
        action="append",
        default=[],
        help="Symptom text. Can be repeated.",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON report.")
    return parser.parse_args()


def load_reason_codes() -> dict[str, dict[str, Any]]:
    path = SKILL_ROOT / "assets/reason_codes.json"
    rows = json.loads(path.read_text(encoding="utf-8"))
    return {str(row["code"]): row for row in rows}


def tokenize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower())


def keyword_rules(catalog: dict[str, dict[str, Any]]) -> list[tuple[str, list[str]]]:
    rules: list[tuple[str, list[str]]] = []
    for code, row in catalog.items():
        keywords = row.get("keywords", [])
        if not isinstance(keywords, list):
            keywords = []
        normalized = [str(keyword) for keyword in keywords if str(keyword).strip()]
        if normalized:
            rules.append((code, normalized))
    return rules


def needs_linknan_first_divergence(symptom: str) -> bool:
    lowered = tokenize(symptom)
    has_linknan = any(
        token in lowered
        for token in [
            "linknan difftest",
            "hyptest_difftest_ref_so",
            "hyptest-difftest-ref-so",
            "ref-dut",
            "ref dut",
            "difftest ref",
        ]
    )
    has_sensitive = any(
        token in lowered
        for token in ["pma", "pbmt", "mmio", "csr", "illegal instruction", "unknown csr"]
    )
    return has_linknan and has_sensitive


def prioritize_for_linknan_first_divergence(scored: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for item in scored:
        if item.get("code") == "D-BLOCK-RUN-UNEXPLAINED":
            item["score"] = int(item.get("score", 0)) + 100
            matched = item.setdefault("matched_keywords", [])
            if isinstance(matched, list) and "linknan first-divergence required" not in matched:
                matched.append("linknan first-divergence required")
            return scored
    scored.append(
        {
            "code": "D-BLOCK-RUN-UNEXPLAINED",
            "score": 100,
            "matched_keywords": ["linknan first-divergence required"],
            "class": "BLOCK",
            "default_decision": "blocked",
            "meaning": "已运行，但失败结果不可归因。",
            "typical_followup": "先完成归因，不用关键词直接落 manual/nongate。",
        }
    )
    return scored


def main() -> int:
    args = parse_args()
    symptom = " ".join(args.symptom).strip()
    if not symptom:
        print("missing --symptom", file=sys.stderr)
        return 2

    catalog = load_reason_codes()
    lowered = tokenize(symptom)
    scored: list[dict[str, Any]] = []
    for code, keywords in keyword_rules(catalog):
        hits = [keyword for keyword in keywords if keyword.lower() in lowered]
        if not hits:
            continue
        row = catalog.get(code, {"code": code})
        scored.append(
            {
                "code": code,
                "score": len(hits),
                "matched_keywords": hits,
                "class": row.get("class"),
                "default_decision": row.get("default_decision"),
                "meaning": row.get("meaning"),
                "typical_followup": row.get("typical_followup"),
            }
        )

    needs_first_divergence = needs_linknan_first_divergence(symptom)
    if needs_first_divergence:
        scored = prioritize_for_linknan_first_divergence(scored)
    scored.sort(key=lambda item: (-int(item["score"]), str(item["code"])))
    if not scored:
        scored.append(
            {
                "code": "D-BLOCK-EVIDENCE",
                "score": 0,
                "matched_keywords": [],
                "class": catalog["D-BLOCK-EVIDENCE"]["class"],
                "default_decision": catalog["D-BLOCK-EVIDENCE"]["default_decision"],
                "meaning": catalog["D-BLOCK-EVIDENCE"]["meaning"],
                "typical_followup": "No specific keyword matched; collect logs/rules before final tiering.",
            }
        )
    warnings: list[dict[str, Any]] = []
    if needs_first_divergence:
        warnings.append(
            {
                "code": "do_not_close_without_first_divergence",
                "requires_triage": True,
                "message": (
                    "LinkNan difftest/REF-DUT symptoms are not closed by reason_code "
                    "keywords alone; hand off to hyptest-failure-triage for first-divergence. "
                    "If this becomes a model limitation for HYPTEST_DIFFTEST_REF_SO, "
                    "report it as a LinkNan difftest REF/model alignment gap, not an official Spike gap."
                ),
            }
        )

    payload = {
        "ok": True,
        "symptom": symptom,
        "suggestions": scored[:5],
        "warnings": warnings,
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    print(f"symptom: {symptom}")
    for item in scored[:5]:
        print(
            f"- {item['code']} score={item['score']} decision={item.get('default_decision')} "
            f"hits={', '.join(item['matched_keywords']) or '-'}"
        )
        if item.get("meaning"):
            print(f"  meaning: {item['meaning']}")
        if item.get("typical_followup"):
            print(f"  followup: {item['typical_followup']}")
    for warning in warnings:
        print(f"warning: {warning['code']} requires_triage={warning['requires_triage']}")
        print(f"  message: {warning['message']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
