#!/usr/bin/env python3
"""Static eval for realistic workflow prompt transcripts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


FIXTURE = Path(__file__).resolve().parent.parent / "assets/evals/workflow_transcript_eval.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check workflow transcript eval coverage.")
    parser.add_argument("--fixture", default=str(FIXTURE), help="Fixture JSON path.")
    parser.add_argument("--json", action="store_true", help="Emit JSON report.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    fixture = Path(args.fixture).expanduser().resolve()
    items = json.loads(fixture.read_text(encoding="utf-8"))
    issues: list[str] = []
    for item in items:
        text = json.dumps(item, ensure_ascii=False)
        if len(item.get("prompt", "")) < 20:
            issues.append(f"{item.get('id')}: prompt too short")
        for term in item.get("expected_terms", []):
            if term not in text:
                issues.append(f"{item.get('id')}: missing expected term `{term}`")
        if not item.get("forbidden_terms"):
            issues.append(f"{item.get('id')}: missing forbidden_terms")
    report = {
        "ok": not issues,
        "fixture": str(fixture),
        "case_count": len(items),
        "issues": issues,
    }
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(("PASS" if report["ok"] else "FAIL") + " workflow transcript eval")
        for issue in issues:
            print(f"  - {issue}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
