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
ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Classify a hyptest failure log for workflow triage.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--log", help="Inline log text.")
    source.add_argument("--log-file", help="Path to log file.")
    parser.add_argument("--spec-profile", help="Accepted for workflow command compatibility; recorded by handoff tools.")
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
    normalized = text.replace("\\r\\n", "\n").replace("\\n", "\n")
    normalized = (
        normalized.replace("\\u001b", "\x1b")
        .replace("\\x1b", "\x1b")
        .replace("\\033", "\x1b")
    )
    return ANSI_RE.sub("", normalized)


def load_reason_catalog() -> dict[str, dict[str, Any]]:
    path = SKILL_ROOT / "assets/reason_codes.json"
    rows = json.loads(path.read_text(encoding="utf-8"))
    return {str(row["code"]): row for row in rows if isinstance(row, dict) and "code" in row}


def first_case_name(text: str) -> str | None:
    names = collect_case_names(text)
    if names:
        return names[0]
    skip = {
        "the",
        "first",
        "instruction",
        "instr",
        "core",
        "dut",
        "ref",
        "commit",
        "commited",
        "committed",
        "difftest",
        "enabled",
        "failed",
        "passed",
        "risc",
        "riscv",
        "riscv64",
        "python",
        "python3",
        "get_result",
        "compile_elf",
        "classify_failure_log",
        "make_triage_handoff",
        "linknan",
        "spike",
        "platform",
        "pma",
        "pbmt",
        "mmio",
        "io",
        "of",
        "in",
        "last",
        "group",
        "trace",
        "mode",
        "cycle",
        "cycles",
        "pc",
        "right",
        "wrong",
        "data",
        "idx",
        "regs",
        "privilege",
        "mismatch",
        "delta",
        "different",
        "trapped",
        "continued",
    }
    option_patterns = [
        r"(?:--case|--name)\s+([A-Za-z_][A-Za-z0-9_]*)",
        r"TEST_REGISTER\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*\)",
    ]
    for pattern in option_patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1)
    preferred_patterns = [
        r"(?m)^\s*((?:ai|manual)_[A-Za-z0-9_]*(?:_corner)?)\s*$",
        r"(?m)^\s*([A-Za-z_][A-Za-z0-9_]*(?:_tests?|_test)_\d+)\s*$",
        r"\b(ai_[A-Za-z0-9_]*(?:_corner)?)\b",
        r"\b(manual_[A-Za-z0-9_]*(?:_corner)?)\b",
        r"\b([A-Za-z_][A-Za-z0-9_]*_corner)\b",
        r"\b([A-Za-z_][A-Za-z0-9_]*(?:_tests?|_test)_\d+)\b",
        r"\b([A-Za-z_][A-Za-z0-9_]*_tests?)\b",
    ]
    for pattern in preferred_patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1)
    for match in re.finditer(r"\b([A-Za-z_][A-Za-z0-9_]*(?:_corner)?)\b", text):
        candidate = match.group(1)
        lowered = candidate.lower()
        if lowered in skip:
            continue
        if lowered.endswith(".py"):
            continue
        return candidate
    return None


def collect_case_names(text: str) -> list[str]:
    names: list[str] = []

    def add(value: str, end: int | None = None) -> None:
        if end is not None and re.match(r"\.(?:c|h|cc|cpp|S|s)\b", text[end:]):
            return
        if value not in names:
            names.append(value)

    option_patterns = [
        r"(?:--case|--name)\s+([A-Za-z_][A-Za-z0-9_]*)",
        r"TEST_REGISTER\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*\)",
    ]
    preferred_patterns = [
        r"(?m)^\s*((?:ai|manual)_[A-Za-z0-9_]*(?:_corner)?)\s*$",
        r"(?m)^\s*([A-Za-z_][A-Za-z0-9_]*(?:_tests?|_test)_\d+)\s*$",
        r"\b(ai_[A-Za-z0-9_]*(?:_corner)?)\b",
        r"\b(manual_[A-Za-z0-9_]*(?:_corner)?)\b",
        r"\b([A-Za-z_][A-Za-z0-9_]*_corner)\b",
        r"\b([A-Za-z_][A-Za-z0-9_]*(?:_tests?|_test)_\d+)\b",
    ]
    for pattern in [*option_patterns, *preferred_patterns]:
        for match in re.finditer(pattern, text):
            add(match.group(1), match.end(1))
    return names


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


def marker_text_without_result_lists(text: str) -> str:
    return re.sub(r"(?:missing_required|found_forbidden)\s*=\s*\[[^\]]*\]", "", text)


def has_difftest_failed(text: str) -> bool:
    return re.search(r"\bdifftest\s+failed\b", text, re.I) is not None


def has_mismatch(text: str) -> bool:
    return (
        re.search(r"\bmismatch(?:es)?\b", text, re.I) is not None
        or has_difftest_failed(text)
        or has_ref_dut_delta(text)
    )


def has_ref_dut_delta(text: str) -> bool:
    lowered = text.lower()
    paired_markers = [
        ("the first commit instr pc of dut", "the first commit instr pc of ref"),
        ("ref mcause", "dut mcause"),
        ("ref regs", "dut"),
        ("ref trapped", "dut continued"),
    ]
    if any(left in lowered and right in lowered for left, right in paired_markers):
        return True
    line_patterns = [
        r"\bref[-_\s]?dut\b",
        r"\bright\s*=\s*0x[0-9a-f]+\s*,?\s*wrong\s*=\s*0x[0-9a-f]+",
        r"\bdifferent\s+at\s+pc\b",
        r"\bthe\s+first\s+commit\s+instr\s+pc\s+of\s+dut\b",
        r"\bthe\s+first\s+commit\s+instr\s+pc\s+of\s+ref\b",
        r"\bref\s+regs\b",
        r"\bdut\s+continued\b",
        r"\bref\s+trapped\b",
    ]
    for line in text.splitlines():
        if any(re.search(pattern, line, re.I) for pattern in line_patterns):
            return True
        lowered_line = line.lower()
        if "ref" in lowered_line and "dut" in lowered_line:
            if any(token in lowered_line for token in ["mismatch", "delta", "different", "trapped", "continued"]):
                return True
    return False


def has_assertion_context(text: str) -> bool:
    return re.search(
        r"\b(?:assert_site|assert_expr|TEST_ASSERT|AI_ASSERT|selfcheck|excpt\.)\b",
        text,
        re.I,
    ) is not None


def has_selfcheck_failed(text: str) -> bool:
    marker_text = marker_text_without_result_lists(text)
    has_difftest_or_delta = has_difftest_failed(marker_text) or has_mismatch(marker_text)
    if has_difftest_or_delta and not has_assertion_context(marker_text):
        return False
    marker_text = re.sub(r"\bdifftest\s+failed\b", "", marker_text, flags=re.I)
    marker_text = re.sub(r"\bREF[-_\s]?DUT\s+mismatch(?:es)?\b", "", marker_text, flags=re.I)
    return marker_present("FAILED", marker_text)


def extract_log_markers(text: str) -> dict[str, object]:
    missing_required = parse_list_field("missing_required", text)
    found_forbidden = parse_list_field("found_forbidden", text)
    marker_text = marker_text_without_result_lists(text)
    lowered = marker_text.lower()
    return {
        "has_passed": marker_present("PASSED", marker_text),
        "has_failed": marker_present("FAILED", marker_text),
        "has_difftest_failed": has_difftest_failed(marker_text),
        "has_mismatch": has_mismatch(marker_text),
        "has_ref_dut_delta": has_ref_dut_delta(marker_text),
        "has_selfcheck_failed": has_selfcheck_failed(marker_text),
        "has_error": "ERROR:" in marker_text or " error" in lowered,
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


def detect_runner_context(text: str, case_names: list[str] | None = None) -> dict[str, bool]:
    raw_lowered = text.lower()
    normalized = raw_lowered.replace("-", "_")
    case_names = case_names or collect_case_names(text)
    official_patterns = [
        r"official\s+spike",
        r"community\s+spike",
        r"upstream\s+spike",
        r"\bhyptest_spike_bin\b",
        r"\bspike[_\s-]?gate\b",
        r"\bplatform\s*[=:]\s*spike\b",
        r"--platform\s+spike\b",
        r"--plat\s+spike\b",
        r"\bget_result\.py\b.*--platform\s+spike\b",
        r"\bcompile_elf\.py\b.*--plat\s+spike\b",
    ]
    linknan_platform_patterns = [
        r"\blinknan\b",
        r"\bplatform\s*[=:]\s*linknan\b",
        r"--platform\s+linknan\b",
        r"--plat\s+linknan\b",
        r"\bsim/simv\b",
        r"\bhyptest_linknan_home\b",
    ]
    linknan_patterns = [
        r"\bhyptest_difftest_ref_so\b",
        r"\blinknan[_\s-]?difftest\b",
        r"\bdiff[-_\s]?test\s+ref\s+so\b",
        r"\bdifftest\s+enabled\b",
        r"\bdifftest\s+failed\b",
        r"\bthe\s+reference\s+model\s+is\b",
        r"\briscv64[-_\s]?spike[-_\s]?so\b",
        r"\bref[-_\s]?dut\b",
        r"\bref\s+.*dut\b",
        r"\bdut\s+.*ref\b",
        r"\bref\s+trapped\b",
        r"\bdut\s+continued\b",
    ]
    difftest_disabled_patterns = [
        r"\bdiff[-_\s]?test\s+disabled\b",
        r"\bdifftest\s+disabled\b",
        r"\bdisabled\s+diff[-_\s]?test\b",
        r"\bdisable[sd]?\s+diff[-_\s]?test\b",
        r"\bno[-_\s]?diff\b",
    ]
    strong_difftest_patterns = [
        r"\bhyptest_difftest_ref_so\b",
        r"\bdifftest\s+enabled\b",
        r"\bdifftest\s+failed\b",
        r"\bref[-_\s]?dut\b",
    ]
    official_spike = any(
        re.search(pattern, raw_lowered, re.S) or re.search(pattern, normalized, re.S)
        for pattern in official_patterns
    )
    linknan_platform = any(
        re.search(pattern, raw_lowered, re.S) or re.search(pattern, normalized, re.S)
        for pattern in linknan_platform_patterns
    )
    linknan_difftest = any(
        re.search(pattern, raw_lowered, re.S) or re.search(pattern, normalized, re.S)
        for pattern in linknan_patterns
    )
    difftest_disabled = any(
        re.search(pattern, raw_lowered, re.S) or re.search(pattern, normalized, re.S)
        for pattern in difftest_disabled_patterns
    )
    strong_difftest_enabled = any(
        re.search(pattern, raw_lowered, re.S) or re.search(pattern, normalized, re.S)
        for pattern in strong_difftest_patterns
    )
    difftest_mode_conflict = bool(difftest_disabled and strong_difftest_enabled)
    if difftest_disabled and not strong_difftest_enabled:
        linknan_difftest = False
    runner_conflict = official_spike and linknan_platform
    command_count = len(re.findall(r"\b(?:get_result\.py|compile_elf\.py)\b", raw_lowered))
    test_header_count = len(re.findall(r"(?im)^\s*risc[-\s]?v\s+nh[-\s]?v5\s+tests\s*$", text))
    difftest_failed_count = len(re.findall(r"\bdifftest\s+failed\b", raw_lowered))
    multi_run = (
        command_count > 1
        or len(case_names) > 1
        or test_header_count > 1
        or difftest_failed_count > 1
    )
    return {
        "official_spike": official_spike,
        "linknan_platform": linknan_platform,
        "linknan_difftest": linknan_difftest,
        "difftest_disabled": difftest_disabled,
        "linknan_no_diff": linknan_platform and difftest_disabled and not linknan_difftest,
        "difftest_mode_conflict": difftest_mode_conflict,
        "multi_run": multi_run,
        "runner_conflict": runner_conflict,
        "runner_ambiguous": not official_spike and not linknan_platform and not linknan_difftest,
    }


def scenario_has_term(term: str, lowered: str, normalized: str) -> bool:
    if term == "io":
        return bool(
            re.search(r"\bio\b", normalized)
            or re.search(r"\bio\s+(?:region|range|memory|responder|device)\b", lowered)
            or re.search(r"\b(?:pma|pbmt)\s+io\b", lowered)
            or re.search(r"\bmmio\b", lowered)
        )
    if term == "cache":
        return bool(re.search(r"\b(?:cache|cacheable|cacheability|uncache(?:able)?)\b", normalized))
    if " " in term:
        return term in lowered or term in normalized
    return bool(re.search(rf"\b{re.escape(term)}\b", normalized))


def classify(text: str, spec_profile: str | None = None) -> dict[str, object]:
    lowered = text.lower()
    scenario: list[str] = []
    error_points: list[str] = []
    reason_codes: list[str] = []
    reason_details: list[dict[str, object]] = []
    next_actions: list[str] = []
    catalog = load_reason_catalog()

    normalized = lowered.replace("_", " ").replace("-", " ")
    case_names = collect_case_names(text)
    log_markers = extract_log_markers(text)
    exception_observed = extract_exception_observed(text)
    runner_context = detect_runner_context(text, case_names=case_names)

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
        if scenario_has_term(term, lowered, normalized):
            scenario.append(term)

    pma_pbmt_mmio = any(term in scenario for term in ["pma", "pbmt", "mmio"])
    if runner_context["multi_run"]:
        error_points.append(
            "multiple runner commands appear in one log; split batch evidence before assigning a single-case cause"
        )
        next_actions.append("split batch log by case/runner before first-divergence or cleanup decisions")
    if runner_context["difftest_mode_conflict"]:
        error_points.append(
            "difftest enabled and disabled/no-diff markers both appear; split log by run before cleanup or runner classification"
        )
        next_actions.append("separate difftest-enabled evidence from no-diff/disabled observation runs")
    if runner_context["runner_conflict"]:
        error_points.append(
            "runner context is conflicting: official Spike and LinkNan evidence both appear; disambiguate before model-gap classification"
        )
        next_actions.append(
            "separate HYPTEST_SPIKE_BIN official gate evidence from LinkNan difftest/no-diff/RTL evidence"
        )
    if (
        runner_context["official_spike"]
        and not runner_context["linknan_difftest"]
        and ("pma" in scenario or "pbmt" in scenario)
    ):
        add_reason(
            reason_codes,
            reason_details,
            catalog,
            "D-MANUAL-NONGATE",
            evidence="official Spike PMA/PBMT model boundary",
        )
        error_points.append("official Spike model gap around PMA/PBMT/cacheability")
        next_actions.extend(["check spec profile Spike gate", "run LinkNan/RTL path"])
    if runner_context["linknan_difftest"] and pma_pbmt_mmio:
        error_points.append(
            "LinkNan difftest PMA/PBMT/MMIO mismatch requires REF-DUT first-divergence; do not close as official Spike gap"
        )
        next_actions.extend([
            "handoff to hyptest-failure-triage with linknan-difftest evidence",
            "record REF-DUT first divergence, PMA CSR/profile, PA window, and responder evidence",
        ])
    elif runner_context["runner_ambiguous"] and pma_pbmt_mmio:
        next_actions.append(
            "identify runner first: HYPTEST_SPIKE_BIN official gate versus HYPTEST_DIFFTEST_REF_SO LinkNan difftest"
        )
    if "mmio" in scenario or ("io" in scenario and "responder" in lowered):
        add_reason(
            reason_codes,
            reason_details,
            catalog,
            "D-COMPILE-ONLY-ENV",
            evidence="MMIO/IO responder or platform environment dependency",
        )
        next_actions.append("confirm MMIO responder before running")
    if (
        log_markers.get("has_difftest_failed")
        or log_markers.get("has_mismatch")
        or log_markers.get("has_ref_dut_delta")
    ):
        add_reason(
            reason_codes,
            reason_details,
            catalog,
            "D-BLOCK-RUN-UNEXPLAINED",
            evidence="difftest mismatch/REF-DUT delta requires triage",
        )
        error_points.append("difftest mismatch; inspect first divergent commit or trap-state delta")
        next_actions.append(
            "collect REF-DUT first-divergence PC, instruction, cause, tval, and privilege state"
        )
    if "assert_site" in lowered or "assert_expr" in lowered or log_markers.get("has_selfcheck_failed"):
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
    if "cache" in scenario or "tlb" in scenario:
        add_reason(
            reason_codes,
            reason_details,
            catalog,
            "D-MANUAL-NONGATE",
            evidence="cache/TLB microarchitectural model boundary",
        )
        next_actions.append("treat cache/TLB flows as RTL-only unless profile says otherwise")
    # Official/community Spike implementation gap (Nanhu implements the spec,
    # HYPTEST_SPIKE_BIN does not). LinkNan difftest REF-DUT mismatches need
    # first-divergence triage before using this reason.
    # Keywords are chosen to match wording a user is likely to put in a log
    # or narrative summary when they spot an unmodeled behavior in Spike.
    if (
        "spike gap" in lowered
        or "spike not modeled" in lowered
        or "not modeled in spike" in lowered
        or "chain closed bp" in lowered
        or ("mcontrol6" in lowered and "chain" in lowered)
    ):
        add_reason(
            reason_codes,
            reason_details,
            catalog,
            "D-MANUAL-SPIKE-GAP",
            evidence=(
                "official/community Spike implementation gap "
                "(Nanhu follows spec, HYPTEST_SPIKE_BIN lacks model)"
            ),
        )
        error_points.append(
            "official/community Spike implementation gap detected; Nanhu may behave correctly but HYPTEST_SPIKE_BIN cannot gate"
        )
        next_actions.extend([
            "confirm Nanhu behavior matches spec (profile §5)",
            "route LinkNan difftest REF-DUT mismatches back to failure-triage for first-divergence before using this reason",
        ])
    # Nanhu implementation out-of-scope (spec exists but Nanhu did not implement).
    # These corners must not be written per Non-Negotiable §3 rule 4; the
    # classifier surfaces the match so the agent/reviewer can roll back.
    if (
        "data trigger" in lowered
        or "nanhu not impl" in lowered
        or "not implemented in nanhu" in lowered
        or ("chain" in lowered and ("3 layer" in lowered or "three layer" in lowered or "3-layer" in lowered))
    ):
        add_reason(
            reason_codes,
            reason_details,
            catalog,
            "D-MANUAL-NANHU-NOT-IMPL",
            evidence="corner appears to exceed current Nanhu implementation scope",
        )
        error_points.append(
            "Nanhu implementation out-of-scope; Non-Negotiable §3 says do not write these cases"
        )
        next_actions.extend([
            "fall back to a Nanhu-implemented equivalent angle",
            "confirm with user before keeping the case as a placeholder",
        ])

    dedup_reason = list(dict.fromkeys(reason_codes))
    return {
        "case_name": first_case_name(text),
        "case_names": case_names,
        "spec_profile": spec_profile,
        "scenario": scenario,
        "assert_site": find_key_value("assert_site", text),
        "assert_expr": find_key_value("assert_expr", text),
        "exception_observed": exception_observed,
        "log_markers": log_markers,
        "runner_context": runner_context,
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
    payload = classify(text, spec_profile=args.spec_profile)
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
