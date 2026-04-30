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

    payload = {
        "ok": True,
        "symptom": symptom,
        "suggestions": scored[:5],
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
    return 0


if __name__ == "__main__":
    sys.exit(main())
