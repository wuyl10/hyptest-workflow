#!/usr/bin/env python3
"""Small heuristic classifier for workflow failure-log evals."""

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
    parser = argparse.ArgumentParser(description="Classify a hyptest failure log for workflow triage.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--log", help="Inline log text.")
    source.add_argument("--log-file", help="Path to log file.")
    parser.add_argument("--json", action="store_true", help="Emit JSON report.")
    return parser.parse_args()


def read_log(args: argparse.Namespace) -> str:
    if args.log_file:
        return normalize_log_text(
            Path(args.log_file).expanduser().read_text(encoding="utf-8", errors="ignore")
        )
    return normalize_log_text(args.log or "")


def normalize_log_text(text: str) -> str:
    """Accept both real newlines and JSON-style escaped log snippets."""
    return text.replace("\\r\\n", "\n").replace("\\n", "\n")


def load_reason_catalog() -> dict[str, dict[str, Any]]:
    path = SKILL_ROOT / "assets/reason_codes.json"
    rows = json.loads(path.read_text(encoding="utf-8"))
    return {str(row["code"]): row for row in rows if isinstance(row, dict) and "code" in row}


def first_case_name(text: str) -> str | None:
    match = re.search(r"\b([A-Za-z_][A-Za-z0-9_]*(?:_corner)?)\b", text)
    return match.group(1) if match else None


def find_value(pattern: str, text: str) -> str | None:
    match = re.search(pattern, text)
    return match.group(1).strip() if match else None


def find_key_value(key: str, text: str) -> str | None:
    pattern = rf"(?m)(?:^|\s){re.escape(key)}\s*=\s*([^\r\n]*)"
    match = re.search(pattern, text)
    if not match:
        return None
    value = match.group(1).strip()
    if key != "assert_expr":
        value = re.split(
            r"\s+(?:assert_site|assert_expr|excpt\.|missing_required|found_forbidden|rc=)",
            value,
            maxsplit=1,
        )[0].strip()
    return value


def parse_list_field(name: str, text: str) -> list[str]:
    match = re.search(rf"{re.escape(name)}\s*=\s*\[([^\]]*)\]", text)
    if not match:
        return []
    return [
        item.strip().strip("'\"")
        for item in match.group(1).split(",")
        if item.strip().strip("'\"")
    ]


def marker_present(marker: str, text: str) -> bool:
    if marker in {"PASSED", "FAILED"}:
        return re.search(rf"\b{re.escape(marker)}\b", text) is not None
    return marker in text


def extract_log_markers(text: str) -> dict[str, object]:
    lowered = text.lower()
    missing_required = parse_list_field("missing_required", text)
    found_forbidden = parse_list_field("found_forbidden", text)
    marker_text = re.sub(r"(?:missing_required|found_forbidden)\s*=\s*\[[^\]]*\]", "", text)
    return {
        "has_passed": marker_present("PASSED", marker_text),
        "has_failed": marker_present("FAILED", marker_text),
        "has_error": "ERROR:" in text or " error" in lowered,
        "has_untested_exception": "untested exception" in lowered,
        "has_hit_good_trap": "HIT GOOD TRAP" in text,
        "has_bad_trap": "BAD TRAP" in text,
        "timed_out": "timeout" in lowered or "rc=124" in lowered,
        "rc": find_value(r"\brc\s*=\s*([0-9]+)", text),
        "missing_required": missing_required,
        "found_forbidden": found_forbidden,
    }


def parse_scalar_value(raw: str) -> object:
    value = raw.strip()
    if value.lower() in {"true", "false"}:
        return value.lower() == "true"
    if re.fullmatch(r"0x[0-9a-fA-F]+", value):
        return value.lower()
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    return value


def extract_exception_observed(text: str) -> dict[str, object]:
    observed: dict[str, object] = {}
    for match in re.finditer(r"(?m)^\s*excpt\.([A-Za-z0-9_]+)\s*=\s*([^\r\n]+)", text):
        observed[match.group(1)] = parse_scalar_value(match.group(2))
    return observed


def add_reason(
    reason_codes: list[str],
    reason_details: list[dict[str, object]],
    catalog: dict[str, dict[str, Any]],
    code: str,
    *,
    evidence: str,
) -> None:
    if code in reason_codes:
        return
    reason_codes.append(code)
    row = catalog.get(code, {})
    reason_details.append(
        {
            "code": code,
            "class": row.get("class"),
            "default_decision": row.get("default_decision"),
            "meaning": row.get("meaning"),
            "typical_followup": row.get("typical_followup"),
            "evidence": evidence,
        }
    )


def classify(text: str) -> dict[str, object]:
    lowered = text.lower()
    scenario: list[str] = []
    error_points: list[str] = []
    reason_codes: list[str] = []
    reason_details: list[dict[str, object]] = []
    next_actions: list[str] = []
    catalog = load_reason_catalog()

    normalized = lowered.replace("_", " ").replace("-", " ")
    log_markers = extract_log_markers(text)
    exception_observed = extract_exception_observed(text)

    for term in [
        "pma",
        "pbmt",
        "mmio",
        "io",
        "trigger",
        "page fault",
        "access fault",
        "vector",
        "store",
        "load",
        "amo",
        "cache",
        "tlb",
    ]:
        if term in lowered or term in normalized:
            scenario.append(term)

    if "official spike" in lowered and ("pma" in lowered or "pbmt" in lowered):
        add_reason(
            reason_codes,
            reason_details,
            catalog,
            "D-MANUAL-NONGATE",
            evidence="official Spike PMA/PBMT model boundary",
        )
        error_points.append("official Spike model gap around PMA/PBMT/cacheability")
        next_actions.extend(["check spec profile Spike gate", "run LinkNan/RTL path"])
    if "mmio" in lowered or ("io" in lowered and "responder" in lowered):
        add_reason(
            reason_codes,
            reason_details,
            catalog,
            "D-COMPILE-ONLY-ENV",
            evidence="MMIO/IO responder or platform environment dependency",
        )
        next_actions.append("confirm MMIO responder before running")
    if "assert_site" in lowered or "assert_expr" in lowered or log_markers.get("has_failed"):
        add_reason(
            reason_codes,
            reason_details,
            catalog,
            "D-BLOCK-RUN-UNEXPLAINED",
            evidence="failed/assert_site/assert_expr in log",
        )
        error_points.append(
            "case assertion failed; inspect assert_site/assert_expr/excpt.triggered/cause dump"
        )
        next_actions.append("verify TEST_SETUP_EXCEPT before excpt.* assertions")
    if "missing_required" in lowered and "passed" in lowered:
        add_reason(
            reason_codes,
            reason_details,
            catalog,
            "D-BLOCK-EVIDENCE",
            evidence="missing PASSED marker in batch result",
        )
        error_points.append("PASS marker missing in batch result")
    if "timeout" in lowered or "rc=124" in lowered or "no commit" in lowered:
        add_reason(
            reason_codes,
            reason_details,
            catalog,
            "D-BLOCK-RUN-UNEXPLAINED",
            evidence="timeout/rc=124/no-commit symptom requires triage",
        )
        if "50000" in lowered and "no commit" in lowered:
            error_points.append("timeout/stuck symptom: 50000 cycles no commit")
        else:
            error_points.append("timeout/stuck symptom")
        next_actions.extend(["inspect run.log", "open FSDB if available"])
    if "cache" in lowered or "tlb" in lowered:
        add_reason(
            reason_codes,
            reason_details,
            catalog,
            "D-MANUAL-NONGATE",
            evidence="cache/TLB microarchitectural model boundary",
        )
        next_actions.append("treat cache/TLB flows as RTL-only unless profile says otherwise")

    dedup_reason = list(dict.fromkeys(reason_codes))
    return {
        "case_name": first_case_name(text),
        "scenario": scenario,
        "assert_site": find_key_value("assert_site", text),
        "assert_expr": find_key_value("assert_expr", text),
        "exception_observed": exception_observed,
        "log_markers": log_markers,
        "error_points": error_points,
        "reason_code_candidates": dedup_reason,
        "reason_code_details": reason_details,
        "next_actions": list(dict.fromkeys(next_actions)),
    }


def main() -> int:
    args = parse_args()
    try:
        text = read_log(args)
    except OSError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    payload = classify(text)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"case_name: {payload['case_name'] or '-'}")
        print("scenario: " + ", ".join(payload["scenario"]))
        print("reason_code_candidates: " + ", ".join(payload["reason_code_candidates"]))
        for detail in payload["reason_code_details"]:
            print(
                f"reason_detail: {detail['code']} decision={detail.get('default_decision')} "
                f"evidence={detail.get('evidence')}"
            )
        for point in payload["error_points"]:
            print(f"error: {point}")
        for action in payload["next_actions"]:
            print(f"next: {action}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
