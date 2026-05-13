#!/usr/bin/env python3
"""Snippet, note, and reading-pack rendering helpers for find_similar_cases.py."""

from __future__ import annotations

import argparse
import fnmatch
import re
from pathlib import Path
from typing import Dict, List, Set, Tuple

from case_extractor import collect_call_targets
from similar_case_terms import (
    INTERESTING_MARKERS,
    LINE_RE,
    summarize_terms,
    term_matches_case,
)


MANUAL_REFERENCE_CASE_RE = re.compile(r"`(ai_[A-Za-z_][A-Za-z0-9_]*)`")


def load_manual_reference_case_names(repo_root: Path) -> Set[str]:
    """Scan test_point/Manual_Reference.md and return the set of case names
    mentioned inside backticks. Used by build_match_notes to distinguish
    formally-reviewed Spike boundary entries from ad-hoc comment-outs.

    Returns an empty set if the file is missing or empty — callers should
    treat this as "no Manual_Reference judgement available" and fall back
    to the weak-signal note.
    """
    path = repo_root / "test_point" / "Manual_Reference.md"
    if not path.is_file():
        return set()
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return set()
    return {m.group(1) for m in MANUAL_REFERENCE_CASE_RE.finditer(text)}


def build_snippet(body: str, max_lines: int) -> str:
    lines = LINE_RE.split(body.strip())
    if not lines:
        return ""

    max_lines = max(max_lines, 1)
    anchor_index = 0
    for marker in INTERESTING_MARKERS:
        for idx, line in enumerate(lines):
            if marker in line:
                anchor_index = idx
                break
        if anchor_index:
            break

    if anchor_index <= max_lines:
        return "\n".join(lines[:max_lines])

    signature = lines[:2]
    body_start = max(2, anchor_index - 2)
    remaining = max(1, max_lines - len(signature) - 1)
    body_lines = lines[body_start : body_start + remaining]
    return "\n".join(signature + ["..."] + body_lines)


def build_assert_focused_snippet(body: str, max_lines: int) -> str:
    lines = LINE_RE.split(body.strip())
    if not lines:
        return ""

    max_lines = max(max_lines, 1)
    assert_indexes = [idx for idx, line in enumerate(lines) if "TEST_ASSERT(" in line]
    if not assert_indexes:
        return build_snippet(body, max_lines)

    signature = lines[:2]
    remaining = max_lines - len(signature)
    if remaining <= 0:
        return "\n".join(signature[:max_lines])

    ranges: List[Tuple[int, int]] = []
    for anchor_index in assert_indexes:
        start = max(2, anchor_index - 1)
        end = min(len(lines), anchor_index + 3)
        if ranges and start <= ranges[-1][1]:
            ranges[-1] = (ranges[-1][0], max(ranges[-1][1], end))
        else:
            ranges.append((start, end))

    selected: List[str] = signature[:]
    previous_end = 2
    for range_index, (start, end) in enumerate(ranges):
        if remaining <= 0:
            break
        if start > previous_end and selected:
            selected.append("...")
            remaining -= 1
            if remaining <= 0:
                break

        for line in lines[start:end]:
            if remaining <= 0:
                break
            selected.append(line)
            remaining -= 1
        previous_end = end

        if range_index >= 1:
            break

    if len(selected) < max_lines and previous_end < len(lines):
        selected.append("...")

    return "\n".join(selected[:max_lines])


def build_learning_focus(case: Dict[str, str]) -> List[str]:
    body = case["body"]
    body_lower = body.lower()
    focus: List[str] = []

    if "goto_priv(" in body:
        focus.append("pay attention to privilege-stage setup before the target access path")
    if "TEST_SETUP_EXCEPT(" in body:
        focus.append("preserve the exception-state reset only for segments that read excpt.*")
    if "excpt.cause" in body or "excpt.tval" in body:
        focus.append("keep observable exception assertions explicit instead of checking only triggered")
    if "guard" in body_lower or "adjacent" in body_lower or "boundary" in body_lower:
        focus.append("retain side-effect boundary checks, not just the target word/value")
    if "sfence_vma(" in body:
        focus.append("keep translation updates paired with sfence_vma when the mapping changes")
    if "repair" in body_lower or "retry" in body_lower or "refault" in body_lower:
        focus.append("preserve the fault -> repair -> retry ordering; do not collapse stages")

    if not focus:
        focus.append("reuse structure and assertions selectively; confirm semantics against project rules")

    return focus[:3]


def build_match_notes(
    case: Dict[str, str],
    score_card: Dict[str, object],
    manual_reference_case_names: set | None = None,
) -> List[str]:
    body = case["body"]
    notes: List[str] = []
    matched_terms = score_card.get("matched_terms", [])

    if matched_terms:
        notes.append(f"matched terms: {summarize_terms(matched_terms, limit=12)}")
    notes.append(
        "signal split: "
        f"query={score_card.get('query_signal_score', 0):.1f}, "
        f"quality={score_card.get('quality_bonus', 0)}"
    )
    if score_card.get("significant_matched_terms"):
        notes.append(
            "specific axes hit: "
            + summarize_terms(score_card["significant_matched_terms"], limit=8)
        )

    assert_count = body.count("TEST_ASSERT(")
    except_count = body.count("TEST_SETUP_EXCEPT(")
    if assert_count or except_count:
        notes.append(
            f"observability density: TEST_ASSERT x{assert_count}, TEST_SETUP_EXCEPT x{except_count}"
        )

    call_targets = collect_call_targets(body, case["case_name"])
    if assert_count == 0 and len(call_targets) == 1:
        notes.append(f"thin wrapper: inspect called helper {call_targets[0]}")
    elif call_targets:
        notes.append(f"calls related helpers: {', '.join(call_targets[:3])}")

    if "excpt.tval" in body or "excpt.cause" in body:
        notes.append("contains explicit cause/tval checking")

    if "guard" in body.lower() or "adjacent" in body.lower() or "boundary" in body.lower():
        notes.append("contains boundary or adjacent-side-effect validation")

    register_status = case.get("register_status")
    case_name = case.get("case_name") or ""
    if register_status == "commented":
        # Two-tier judgment: Manual_Reference.md presence decides signal strength.
        # - Has Manual_Reference entry → formally-reviewed Spike boundary (strong signal)
        # - No Manual_Reference entry → likely WIP/manual debug (weak signal, do not gate)
        has_manual_ref = False
        if manual_reference_case_names is not None and case_name:
            has_manual_ref = case_name in manual_reference_case_names
        if has_manual_ref:
            notes.append(
                "register_status=commented + Manual_Reference entry EXISTS — this is a "
                "formally-reviewed Spike model boundary; MUST read the case source + the "
                "corresponding Manual_Reference.md entry before choosing a similar angle"
            )
        elif manual_reference_case_names is not None:
            # Explicit Manual_Reference lookup was performed but found no entry.
            notes.append(
                "register_status=commented but no Manual_Reference.md entry — likely a "
                "manual/WIP comment-out (not a Spike boundary signal); still a useful "
                "reference for similar case structure, but not a hard gate"
            )
        else:
            # No lookup performed (older call path); emit generic signal.
            notes.append(
                "register_status=commented — the case was intentionally disabled; check "
                "Manual_Reference.md to see if it is a formal Spike boundary entry "
                "(strong signal) or a manual/WIP comment (weak signal)"
            )
    elif register_status == "unregistered":
        notes.append(
            "register_status=unregistered — source exists but no TEST_REGISTER line; "
            "check if the case is a helper or was omitted intentionally"
        )

    return notes


def build_focus_coverage(
    match_index: Dict[str, Dict[str, int]],
    focus_terms: List[str],
    term_profiles: Dict[str, Dict[str, object]],
) -> Dict[str, object]:
    hits: List[str] = []
    misses: List[str] = []
    significant_hits: List[str] = []
    total_weight = 0.0
    hit_weight = 0.0
    significant_total = 0

    for term in focus_terms:
        profile = term_profiles[term]
        weight = float(profile["information_weight"])
        total_weight += weight
        if profile["is_significant"]:
            significant_total += 1

        if term_matches_case(match_index, profile):
            hits.append(term)
            hit_weight += weight
            if profile["is_significant"]:
                significant_hits.append(term)
        else:
            misses.append(term)

    weighted_ratio = hit_weight / total_weight if total_weight else 0.0
    return {
        "focus_hits": hits,
        "focus_misses": misses,
        "focus_hit_weight": round(hit_weight, 2),
        "focus_total_weight": round(total_weight, 2),
        "focus_weighted_ratio": round(weighted_ratio, 3),
        "significant_focus_hits": significant_hits,
        "significant_focus_total": significant_total,
    }


def case_allowed(case: Dict[str, str], args: argparse.Namespace) -> bool:
    if args.enabled_only and case["register_status"] != "enabled":
        return False

    if args.file_glob:
        file_name = case["file_name"]
        full_path = case["file"]
        if not any(
            fnmatch.fnmatch(file_name, pattern) or fnmatch.fnmatch(full_path, pattern)
            for pattern in args.file_glob
        ):
            return False

    return True


def render_reading_pack(payload: Dict[str, object]) -> str:
    lines: List[str] = []
    lines.append("# Similar Case Reading Pack")
    lines.append("")
    lines.append(f"HYPTEST_HOME: {payload['repo_root']}")
    lines.append(f"query_terms: {summarize_terms(payload['query_terms'])}")
    if payload.get("focus_terms"):
        lines.append(f"focus_terms: {summarize_terms(payload['focus_terms'])}")
    if payload.get("retrieval_status"):
        lines.append(f"retrieval_status: {payload['retrieval_status']}")
    if payload.get("retrieval_reason"):
        lines.append(f"retrieval_reason: {payload['retrieval_reason']}")
    lines.append(f"searched_cases: {payload['searched_case_count']}")
    lines.append(f"selected_cases: {payload['result_count']}")
    lines.append("")
    lines.append("## How to use this pack")
    if payload.get("retrieval_status") == "strong_match":
        lines.append("- Read the primary reference first, then use the additional entries as contrastive support.")
    elif payload.get("retrieval_status") == "weak_match":
        lines.append("- Treat the primary reference as a partial skeleton only; verify every missing axis before reuse.")
    else:
        lines.append("- No close analog was found; treat all listed results as partial hints rather than a reusable template.")
    lines.append("- Read these cases before writing the new case; do not copy blindly.")
    lines.append("- Prefer reusing structure, assertion shape, and environment setup order.")
    lines.append("- Reconcile any borrowed pattern with Manual_Reference and writing_cases.md.")
    lines.append("- If a result is a thin wrapper, inspect the related helper first.")
    fallback_plan = payload.get("fallback_plan", [])
    if fallback_plan:
        lines.append("")
        lines.append("## Fallback Plan")
        for step in fallback_plan:
            lines.append(f"- {step}")

    results = payload["results"]
    for index, item in enumerate(results, start=1):
        lines.append("")
        lines.append(f"## {index}. {item['case_name']}")
        lines.append(f"- register_status: {item['register_status']}")
        lines.append(f"- symbol_kind: {item['symbol_kind']}")
        lines.append(f"- location: {item['file']}:{item['line']}")
        lines.append(f"- score: {item['score']}")
        if item.get("reference_role"):
            lines.append(f"- reference_role: {item['reference_role']}")
        if item.get("selection_note"):
            lines.append(f"- selection_note: {item['selection_note']}")
        if item.get("family_relation"):
            lines.append(f"- family_relation: {item['family_relation']}")
        if item.get("reading_hint"):
            lines.append(f"- reading_hint: {item['reading_hint']}")
        if item.get("contrast_tokens"):
            lines.append(f"- contrast_tokens: {summarize_terms(item['contrast_tokens'], limit=6)}")
        if item.get("focus_hits") is not None:
            focus_hits = item.get("focus_hits", [])
            focus_misses = item.get("focus_misses", [])
            total_focus = len(focus_hits) + len(focus_misses)
            lines.append(f"- focus_coverage: {len(focus_hits)}/{total_focus}")
            lines.append(
                f"- weighted_focus_coverage: {item.get('focus_weighted_ratio', 0.0):.2f}"
            )
            if focus_hits:
                lines.append(f"- focus_hits: {summarize_terms(focus_hits, limit=8)}")
            if focus_misses:
                lines.append(f"- focus_misses: {summarize_terms(focus_misses, limit=6)}")
            if item.get("significant_focus_hits") is not None:
                lines.append(
                    "- specific_focus_axes: "
                    f"{len(item.get('significant_focus_hits', []))}/{item.get('significant_focus_total', 0)}"
                )
        if item.get("matched_terms"):
            lines.append(f"- matched_terms: {summarize_terms(item['matched_terms'], limit=12)}")
        if item.get("query_signal_score") is not None:
            lines.append(f"- query_signal_score: {item['query_signal_score']}")
        if item.get("quality_bonus") is not None:
            lines.append(f"- quality_bonus: {item['quality_bonus']}")

        match_notes = item.get("match_notes", [])
        if match_notes:
            lines.append("- why_selected:")
            for note in match_notes:
                lines.append(f"  - {note}")

        learning_focus = item.get("learning_focus", [])
        if learning_focus:
            lines.append("- adaptation_focus:")
            for note in learning_focus:
                lines.append(f"  - {note}")

        if item.get("snippet"):
            lines.append("- key_snippet:")
            lines.append("```c")
            lines.extend(item["snippet"].splitlines())
            lines.append("```")

        helper = item.get("related_helper")
        if helper:
            lines.append("- related_helper:")
            lines.append(
                f"  - {helper['case_name']} [{helper['symbol_kind']}] {helper['file']}:{helper['line']}"
            )
            if helper.get("match_notes"):
                lines.append("  - why_helper:")
                for note in helper["match_notes"]:
                    lines.append(f"    - {note}")
            if helper.get("snippet"):
                lines.append("```c")
                lines.extend(helper["snippet"].splitlines())
                lines.append("```")

    if not results:
        lines.append("")
        lines.append("No matching cases found. Broaden the query terms or inspect manually with rg.")

    return "\n".join(lines)
