#!/usr/bin/env python3
"""Ranking and retrieval-assessment helpers for find_similar_cases.py."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List

from case_extractor import collect_call_targets
from similar_case_terms import (
    SHORT_ALLOWLIST,
    SIMILARITY_STOPWORDS,
    canonical_term_key,
    count_term_section_matches,
    score_file_term,
    summarize_terms,
)


def build_similarity_tokens(case: Dict[str, str]) -> List[str]:
    tokens: List[str] = []
    seen = set()
    for part in (case["case_name"], Path(case["file_name"]).stem):
        for raw_token in re.split(r"[_-]+", part.lower()):
            token = raw_token.strip().lower().strip("_-+")
            if not token:
                continue
            if token in SIMILARITY_STOPWORDS:
                continue
            if len(token) < 3 and token not in SHORT_ALLOWLIST:
                continue
            key = canonical_term_key(token)
            if key in seen:
                continue
            seen.add(key)
            tokens.append(token)
    return tokens


def build_name_tokens(case: Dict[str, str]) -> List[str]:
    tokens: List[str] = []
    seen = set()
    for raw_token in re.split(r"[_-]+", case["case_name"].lower()):
        token = raw_token.strip().lower().strip("_-+")
        if not token:
            continue
        if token in SIMILARITY_STOPWORDS:
            continue
        if len(token) < 3 and token not in SHORT_ALLOWLIST:
            continue
        key = canonical_term_key(token)
        if key in seen:
            continue
        seen.add(key)
        tokens.append(token)
    return tokens


def similarity_token_weight(token: str) -> int:
    return max(12, score_file_term(token))


def weighted_token_similarity(left: Dict[str, str], right: Dict[str, str]) -> float:
    left_tokens = left.get("similarity_tokens", [])
    right_tokens = right.get("similarity_tokens", [])
    left_map = {canonical_term_key(token): token for token in left_tokens}
    right_map = {canonical_term_key(token): token for token in right_tokens}
    union_keys = set(left_map) | set(right_map)
    if not union_keys:
        return 0.0

    shared_keys = set(left_map) & set(right_map)
    shared_weight = sum(
        similarity_token_weight(left_map.get(key, right_map[key]))
        for key in shared_keys
    )
    union_weight = sum(
        similarity_token_weight(left_map.get(key, right_map.get(key, "")))
        for key in union_keys
    )
    similarity = shared_weight / union_weight if union_weight else 0.0
    if left["file_name"] == right["file_name"]:
        similarity = min(1.0, similarity + 0.08)
    return similarity


def ordered_prefix_similarity(left: Dict[str, str], right: Dict[str, str]) -> float:
    left_tokens = left.get("name_tokens", [])
    right_tokens = right.get("name_tokens", [])
    if not left_tokens or not right_tokens:
        return 0.0

    common = 0
    for left_token, right_token in zip(left_tokens, right_tokens):
        if canonical_term_key(left_token) != canonical_term_key(right_token):
            break
        common += 1

    return common / max(1, min(len(left_tokens), len(right_tokens)))


def build_distinguishing_tokens(
    item: Dict[str, object],
    reference: Dict[str, object],
    limit: int = 6,
) -> List[str]:
    reference_keys = {canonical_term_key(token) for token in reference.get("name_tokens", [])}
    delta: List[str] = []
    for token in item.get("name_tokens", []):
        if canonical_term_key(token) not in reference_keys:
            delta.append(token)
    return delta[:limit]


def score_case(
    case: Dict[str, str],
    term_profiles: Dict[str, Dict[str, object]],
    match_index: Dict[str, Dict[str, int]],
) -> Dict[str, object]:
    body = case["body"].lower()
    query_signal_score = 0.0
    matched_terms: List[str] = []
    significant_matched_terms: List[str] = []

    for term, profile in term_profiles.items():
        counts = count_term_section_matches(match_index, profile)
        term_score = 0.0
        info_weight = float(profile["information_weight"])
        query_weight = float(profile["query_weight"])

        if counts["name"]:
            term_score += 8.0 + info_weight * 2.2
        if counts["file"]:
            term_score += 4.0 + info_weight * 1.2
        if counts["body"]:
            term_score += min(counts["body"], 4) * (1.2 + info_weight * 0.9)

        if term_score <= 0:
            continue

        term_score *= query_weight
        query_signal_score += term_score
        matched_terms.append(term)
        if profile["is_significant"]:
            significant_matched_terms.append(term)

    quality_bonus = 0
    register_status = case["register_status"]
    if register_status == "enabled":
        quality_bonus += 3
    elif register_status == "commented":
        quality_bonus += 1

    assert_count = body.count("TEST_ASSERT(".lower())
    except_count = body.count("TEST_SETUP_EXCEPT(".lower())
    quality_bonus += min(assert_count, 6) * 4
    quality_bonus += min(except_count, 6) * 2

    call_targets = collect_call_targets(case["body"], case["case_name"])
    if assert_count == 0 and len(call_targets) == 1:
        quality_bonus -= 6

    total_score = int(round(query_signal_score + quality_bonus))
    return {
        "score": total_score,
        "query_signal_score": round(query_signal_score, 1),
        "quality_bonus": quality_bonus,
        "matched_terms": matched_terms,
        "significant_matched_terms": significant_matched_terms,
    }


def select_results_with_diversity(
    ranked: List[Dict[str, object]],
    limit: int,
) -> List[Dict[str, object]]:
    if limit <= 0 or not ranked:
        return []

    selected: List[Dict[str, object]] = []
    remaining = ranked[:]

    primary = remaining.pop(0)
    primary["reference_role"] = "primary_reference"
    primary["selection_note"] = (
        "highest raw relevance score and the best starting point for reading the target flow"
    )
    primary["selection_similarity"] = 0.0
    selected.append(primary)

    while remaining and len(selected) < limit:
        best_index = 0
        best_adjusted = None
        best_similarity = 0.0

        for index, item in enumerate(remaining):
            max_similarity = 0.0
            max_prefix_similarity = 0.0
            same_family_count = 0
            for chosen in selected:
                token_similarity = weighted_token_similarity(item, chosen)
                prefix_similarity = ordered_prefix_similarity(item, chosen)
                max_similarity = max(max_similarity, token_similarity)
                max_prefix_similarity = max(max_prefix_similarity, prefix_similarity)
                if prefix_similarity >= 0.72 or token_similarity >= 0.84:
                    same_family_count += 1
            adjusted = (
                float(item["score"])
                + len(item.get("focus_hits", [])) * 6.0
                - max_similarity * 120.0
                - max_prefix_similarity * 90.0
                - same_family_count * 140.0
            )
            if best_adjusted is None or adjusted > best_adjusted:
                best_adjusted = adjusted
                best_index = index
                best_similarity = max(max_similarity, max_prefix_similarity)

        chosen = remaining.pop(best_index)
        chosen["selection_similarity"] = round(best_similarity, 3)
        if best_similarity >= 0.78:
            chosen["reference_role"] = "same_family_variant"
            chosen["selection_note"] = (
                "kept as a very close family variant only after stronger de-dup penalties, because it still adds a meaningful contrast point"
            )
        elif best_similarity >= 0.38:
            chosen["reference_role"] = "complementary_reference"
            chosen["selection_note"] = (
                "selected to stay close to the same scenario while avoiding an over-duplicate sibling result"
            )
        else:
            chosen["reference_role"] = "coverage_expander"
            chosen["selection_note"] = (
                "selected to widen the reference set after the closest siblings became too repetitive"
            )
        selected.append(chosen)

    return selected


def annotate_reference_relationships(results: List[Dict[str, object]]) -> List[Dict[str, object]]:
    if not results:
        return results

    primary = results[0]
    primary["family_relation"] = "primary_anchor"
    primary["reading_hint"] = "read this one first; it is the anchor sample for the current task"

    for item in results[1:]:
        token_similarity = weighted_token_similarity(item, primary)
        prefix_similarity = ordered_prefix_similarity(item, primary)
        delta_tokens = build_distinguishing_tokens(item, primary)
        item["contrast_tokens"] = delta_tokens
        if max(token_similarity, prefix_similarity) >= 0.55:
            item["family_relation"] = "same_family_as_primary"
            if delta_tokens:
                item["reading_hint"] = (
                    f"skim after the primary to compare only the changed detail tokens: {', '.join(delta_tokens)}"
                )
            else:
                item["reading_hint"] = (
                    "skim after the primary only if you need another near-identical sibling variant"
                )
        else:
            item["family_relation"] = "adjacent_flow"
            if delta_tokens:
                item["reading_hint"] = (
                    f"read after the primary to widen coverage toward: {', '.join(delta_tokens)}"
                )
            else:
                item["reading_hint"] = (
                    "read after the primary to widen coverage without changing the core target flow"
                )

    return results


def build_partial_reference_summary(item: Dict[str, object]) -> str:
    focus_hits = item.get("focus_hits", [])
    if focus_hits:
        return summarize_terms(focus_hits, limit=5)
    contrast_tokens = item.get("contrast_tokens", [])
    if contrast_tokens:
        return summarize_terms(contrast_tokens, limit=5)
    return "nearest observable flow"


def build_fallback_plan(
    results: List[Dict[str, object]],
    focus_terms: List[str],
    retrieval_status: str,
) -> List[str]:
    if retrieval_status == "strong_match" or not results:
        return []

    primary = results[0]
    covered_keys = {
        canonical_term_key(term)
        for item in results
        for term in item.get("focus_hits", [])
    }
    remaining_axes = [
        term for term in focus_terms if canonical_term_key(term) not in covered_keys
    ]

    steps: List[str] = []
    if retrieval_status == "weak_match":
        steps.append(
            f"use `{primary['case_name']}` only for the nearest skeleton: {build_partial_reference_summary(primary)}"
        )
        if len(results) > 1:
            support_bits = []
            for item in results[1:]:
                support_bits.append(
                    f"`{item['case_name']}` -> {build_partial_reference_summary(item)}"
                )
            steps.append("borrow supporting fragments selectively: " + "; ".join(support_bits))
        if remaining_axes:
            steps.append(
                "manually fill still-uncovered axes from the test point and `references/writing_cases.md`: "
                + summarize_terms(remaining_axes, limit=8)
            )
        else:
            steps.append(
                "before reusing structure, manually verify the target-only deltas against the test point rather than copying the whole case"
            )
        return steps

    steps.append(
        "treat all current results as partial references only; do not clone any single case structure end-to-end"
    )
    if results:
        primary_summary = build_partial_reference_summary(primary)
        steps.append(f"take only the nearest local idea from `{primary['case_name']}`: {primary_summary}")
    if len(results) > 1:
        support_bits = []
        for item in results[1:]:
            support_bits.append(
                f"`{item['case_name']}` -> {build_partial_reference_summary(item)}"
            )
        steps.append("compose the new case from multiple partial references: " + "; ".join(support_bits))
    if remaining_axes:
        steps.append(
            "the following focus axes still lack a close analog and must be built directly from the test point: "
            + summarize_terms(remaining_axes, limit=8)
        )
    steps.append(
        "if the flow is still unclear, inspect the repo with `rg` around the missing axes instead of forcing a weak analogy"
    )
    return steps


def build_retrieval_assessment(
    results: List[Dict[str, object]],
    focus_terms: List[str],
    query_terms: List[str],
) -> Dict[str, object]:
    if not results:
        return {
            "retrieval_status": "no_close_match",
            "retrieval_reason": "no candidate matched any query axis after exact tokenized matching",
            "fallback_plan": [
                "split the target into flow, assertion, and environment axes before searching again",
                "use `rg` on the repo for the missing axes and fall back to `references/writing_cases.md` rather than forcing an analogy",
            ],
        }

    primary = results[0]
    weighted_ratio = float(primary.get("focus_weighted_ratio", 0.0))
    matched_ratio = len(primary.get("matched_terms", [])) / max(1, len(query_terms))
    significant_focus_hits = primary.get("significant_focus_hits", [])
    significant_focus_total = int(primary.get("significant_focus_total", 0))
    significant_hit_count = len(significant_focus_hits)

    if significant_focus_total > 0:
        strong_shape = significant_hit_count >= max(1, min(2, significant_focus_total))
    else:
        strong_shape = len(primary.get("matched_terms", [])) >= 3

    if weighted_ratio >= 0.76 and matched_ratio >= 0.22 and strong_shape:
        retrieval_status = "strong_match"
        retrieval_reason = (
            "primary reference has high weighted focus coverage "
            f"({weighted_ratio:.2f}) with {significant_hit_count}/{max(1, significant_focus_total)} specific axes aligned"
        )
    elif weighted_ratio >= 0.48 or significant_hit_count >= 1 or matched_ratio >= 0.16:
        retrieval_status = "weak_match"
        retrieval_reason = (
            "nearest result is only a partial analog: weighted focus coverage "
            f"{weighted_ratio:.2f}, specific axes {significant_hit_count}/{significant_focus_total}"
        )
    else:
        retrieval_status = "no_close_match"
        retrieval_reason = (
            "nearest result has weak semantic overlap: weighted focus coverage "
            f"{weighted_ratio:.2f}, specific axes {significant_hit_count}/{significant_focus_total}"
        )

    return {
        "retrieval_status": retrieval_status,
        "retrieval_reason": retrieval_reason,
        "fallback_plan": build_fallback_plan(results, focus_terms, retrieval_status),
    }
