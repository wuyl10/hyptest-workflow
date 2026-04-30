#!/usr/bin/env python3
"""Static eval for case-generation workflow rules in SKILL.md and references."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from skill_config import current_profile_anchor


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parent
FIXTURE = SKILL_ROOT / "assets/evals/case_generation_contract_eval.json"
DOCS = [
    "SKILL.md",
    "references/spec_and_model_limits.md",
    "references/repo_layout.md",
    "references/coverage_and_dedupe.md",
    "references/task_input_schema.md",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate case generation contract docs.")
    parser.add_argument("--fixture", default=str(FIXTURE), help="Fixture JSON path.")
    parser.add_argument("--json", action="store_true", help="Emit JSON report.")
    return parser.parse_args()


def load_doc_text() -> str:
    chunks: list[str] = []
    for rel in DOCS + [current_profile_anchor()]:
        path = SKILL_ROOT / rel
        if path.is_file():
            chunks.append(path.read_text(encoding="utf-8", errors="ignore"))
    return "\n".join(chunks)


def main() -> int:
    args = parse_args()
    cases = json.loads(Path(args.fixture).expanduser().read_text(encoding="utf-8"))
    text = load_doc_text()
    failures: list[str] = []
    results: list[dict[str, object]] = []

    for item in cases:
        case_failures: list[str] = []
        for term in item.get("expected_terms", []):
            if term not in text:
                case_failures.append(f"missing expected term {term}")
        for term in item.get("forbidden_terms", []):
            if term in text:
                case_failures.append(f"forbidden term present {term}")
        if case_failures:
            failures.append(f"{item['id']}: {', '.join(case_failures)}")
        results.append({"id": item["id"], "ok": not case_failures})

    payload = {
        "ok": not failures,
        "fixture": str(Path(args.fixture).expanduser()),
        "case_count": len(cases),
        "failures": failures,
        "results": results,
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(("PASS" if payload["ok"] else "FAIL") + " case generation contract eval")
        for failure in failures:
            print(f"  - {failure}")
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
