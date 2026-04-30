#!/usr/bin/env python3
"""Static quality checks for workflow task prompt eval fixtures."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REQUIRED_IDS = {
    "new_case_only_file_scope",
    "supplement_existing_point",
    "spike_fail_gate_decision",
    "pma_pbmt_mmio_nongate",
    "similar_case_coverage",
    "no_duplicate_case",
    "rtl_only_cache_tlb",
    "negative_rerun_only_no_new_case",
    "negative_analysis_only_no_edits",
    "negative_xiangshan_platform_alias",
}

REQUIRED_COVERAGE_TERMS = {
    "spec_profile": "spec_profile",
    "new-case-only": "new-case-only",
    "PMA": "PMA",
    "PBMT": "PBMT",
    "MMIO": "MMIO",
    "Spike": "Spike",
    "LinkNan": "LinkNan",
    "相似": "相似",
    "重复": "重复",
    "TLB": "TLB",
    "cache": "cache",
    "不新增": "不新增",
    "不要改代码": "不要改代码",
    "xiangshan": "xiangshan",
    "linknan": "linknan",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate workflow task prompt fixtures.")
    parser.add_argument(
        "--fixture",
        default=str(
            Path(__file__).resolve().parent.parent
            / "assets/evals/workflow_task_prompts.json"
        ),
        help="Path to workflow task prompt fixture JSON.",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON report.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    fixture = Path(args.fixture).expanduser().resolve()
    issues: list[str] = []
    try:
        payload = json.loads(fixture.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"FAIL workflow task prompts: {exc}", file=sys.stderr)
        return 2

    positive_evals = payload.get("positive_evals")
    negative_evals = payload.get("negative_evals")
    if isinstance(positive_evals, list) or isinstance(negative_evals, list):
        if not isinstance(positive_evals, list) or not positive_evals:
            issues.append("fixture must contain non-empty `positive_evals` list")
            positive_evals = []
        if not isinstance(negative_evals, list) or not negative_evals:
            issues.append("fixture must contain non-empty `negative_evals` list")
            negative_evals = []
        evals = [
            {**item, "kind": "positive"} for item in positive_evals if isinstance(item, dict)
        ] + [
            {**item, "kind": "negative"} for item in negative_evals if isinstance(item, dict)
        ]
    else:
        evals = payload.get("evals")
        if not isinstance(evals, list) or not evals:
            issues.append("fixture must contain non-empty `evals` list")
            evals = []

    ids = set()
    corpus = ""
    for index, item in enumerate(evals, start=1):
        if not isinstance(item, dict):
            issues.append(f"eval {index}: must be an object")
            continue
        eval_id = item.get("id")
        prompt = item.get("prompt")
        expected = item.get("expected_output")
        kind = item.get("kind", "unspecified")
        if not isinstance(eval_id, str) or not eval_id:
            issues.append(f"eval {index}: missing string id")
        else:
            if eval_id in ids:
                issues.append(f"duplicate eval id `{eval_id}`")
            ids.add(eval_id)
        if not isinstance(prompt, str) or len(prompt.strip()) < 20:
            issues.append(f"{eval_id or index}: prompt is too short or missing")
        if not isinstance(expected, str) or len(expected.strip()) < 20:
            issues.append(f"{eval_id or index}: expected_output is too short or missing")
        if kind not in {"positive", "negative", "unspecified"}:
            issues.append(f"{eval_id or index}: invalid kind `{kind}`")
        corpus += f"\n{prompt or ''}\n{expected or ''}\n"

    missing_ids = sorted(REQUIRED_IDS - ids)
    for eval_id in missing_ids:
        issues.append(f"missing required eval id `{eval_id}`")

    for label, needle in REQUIRED_COVERAGE_TERMS.items():
        if needle not in corpus:
            issues.append(f"fixture does not cover required term `{label}`")

    report = {
        "ok": not issues,
        "fixture": str(fixture),
        "eval_count": len(evals),
        "positive_count": sum(1 for item in evals if item.get("kind") == "positive"),
        "negative_count": sum(1 for item in evals if item.get("kind") == "negative"),
        "issues": issues,
    }
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(("PASS" if report["ok"] else "FAIL") + " workflow task prompts")
        for issue in issues:
            print(f"  - {issue}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
