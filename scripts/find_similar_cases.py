#!/usr/bin/env python3
"""
Rank similar existing hyptest cases from ai_test_cases/*.c and manual_test_cases/**/*.c.

The goal is not to auto-generate code, but to help the agent inspect a small
set of good reference cases before writing a new one.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from case_extractor import (
    build_case_index,
    find_related_helper,
    load_cases_with_cache,
)
from similar_case_ranker import (
    annotate_reference_relationships,
    build_name_tokens,
    build_retrieval_assessment,
    build_similarity_tokens,
    score_case,
    select_results_with_diversity,
)
from similar_case_render import (
    build_assert_focused_snippet,
    build_focus_coverage,
    build_learning_focus,
    build_match_notes,
    build_snippet,
    case_allowed,
    render_reading_pack,
)
from similar_case_terms import (
    build_case_match_index,
    build_focus_terms,
    build_term_profile,
    canonical_term_key,
    dedupe_terms_by_canonical_key,
    extract_terms_from_file,
    summarize_terms,
)
from skill_config import resolve_path

QUERY_UNIT_RE = re.compile(r"[a-z0-9][a-z0-9_+-]*")


def expand_query_terms(raw_terms: list[str]) -> list[str]:
    """Keep exact query terms, and make natural phrases searchable."""
    expanded: list[str] = []
    for raw_term in raw_terms:
        term = raw_term.strip().lower()
        if not term:
            continue

        units = [unit.strip("_-+") for unit in QUERY_UNIT_RE.findall(term)]
        units = [unit for unit in units if unit]
        if len(units) > 1:
            expanded.append("_".join(units))
            expanded.extend(units)
        else:
            expanded.append(term)
    return dedupe_terms_by_canonical_key(expanded)


def build_quality_report(results: list[dict[str, object]], focus_terms: list[str]) -> dict[str, object]:
    top_scores = [float(item.get("score", 0.0)) for item in results[:5]]
    top_names = [str(item.get("case_name", "")) for item in results[:5]]
    top_focus_ratios = [
        float(item.get("focus_weighted_ratio", 0.0))
        for item in results[:5]
    ]
    return {
        "top1": top_names[0] if top_names else None,
        "top3": top_names[:3],
        "top5_scores": top_scores,
        "top5_focus_weighted_ratios": top_focus_ratios,
        "focus_term_count": len(focus_terms),
        "result_count": len(results),
        "has_strong_top1_signal": bool(
            results
            and float(results[0].get("score", 0.0)) >= 20.0
            and float(results[0].get("focus_weighted_ratio", 0.0)) >= 0.35
        ),
    }

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Find similar existing hyptest cases before writing a new case."
    )
    parser.add_argument("--repo-root", required=True, help="Path to riscv-hyp-tests repo root")
    parser.add_argument(
        "--query",
        action="append",
        default=[],
        help="Keyword to search for; can be repeated",
    )
    parser.add_argument(
        "--from-file",
        help="Optional text/test-point file to extract English/code identifiers from",
    )
    parser.add_argument(
        "--heading-pattern",
        help="For markdown --from-file, only use sections whose heading matches this case-insensitive regex",
    )
    parser.add_argument(
        "--section-index",
        type=int,
        help="For markdown --from-file, select a specific heading section (1-based; negative values count from the end)",
    )
    parser.add_argument(
        "--enabled-only",
        action="store_true",
        help="Keep only cases enabled in test_register.c",
    )
    parser.add_argument(
        "--file-glob",
        action="append",
        default=[],
        help=(
            "Restrict matches to relative source globs, e.g. "
            "ai_test_cases/*.c or manual_test_cases/memory/*.c; can be repeated"
        ),
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Do not use the repo-local case extraction cache.",
    )
    parser.add_argument(
        "--cache-dir",
        help="Override the case extraction cache directory. Default: <repo-root>/.hyptest_workflow_skill/cache",
    )
    parser.add_argument(
        "--show-snippet",
        action="store_true",
        help="Show a useful snippet from each matched function body",
    )
    parser.add_argument(
        "--assert-only",
        action="store_true",
        help="Prefer TEST_ASSERT-centered snippets; useful when reading results with an LLM",
    )
    parser.add_argument(
        "--emit-reading-pack",
        action="store_true",
        help="Emit an LLM-friendly reading pack instead of the default compact list",
    )
    parser.add_argument(
        "--explain-score",
        action="store_true",
        help="Include score explanation fields for each result.",
    )
    parser.add_argument(
        "--snippet-lines",
        type=int,
        default=10,
        help="Maximum number of lines to show for each snippet",
    )
    parser.add_argument(
        "--max-file-terms",
        type=int,
        default=0,
        help="Maximum number of auto-extracted terms to keep from --from-file; 0 means auto",
    )
    parser.add_argument("--limit", type=int, default=5, help="Maximum number of results")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of text")
    return parser.parse_args()

def main() -> int:
    args = parse_args()
    repo_root = resolve_path(args.repo_root)

    explicit_terms = expand_query_terms(args.query)
    terms = list(explicit_terms)
    if args.from_file:
        from_file = resolve_path(args.from_file)
        if not from_file.is_file():
            print(f"from-file not found: {from_file}", file=sys.stderr)
            return 2
        try:
            terms.extend(
                extract_terms_from_file(
                    from_file,
                    args.max_file_terms,
                    heading_pattern=args.heading_pattern,
                    section_index=args.section_index,
                )
            )
        except re.error as exc:
            print(f"invalid --heading-pattern: {exc}", file=sys.stderr)
            return 2
        except (IndexError, ValueError) as exc:
            print(str(exc), file=sys.stderr)
            return 2

    terms = dedupe_terms_by_canonical_key(terms)

    if not terms:
        print("No query terms provided. Use --query and/or --from-file.", file=sys.stderr)
        return 2

    focus_terms = build_focus_terms(terms)
    focus_term_keys = {canonical_term_key(term) for term in focus_terms}
    explicit_term_keys = {canonical_term_key(term) for term in explicit_terms}
    term_profiles = {
        term: build_term_profile(
            term,
            is_focus_term=canonical_term_key(term) in focus_term_keys,
            is_explicit_term=canonical_term_key(term) in explicit_term_keys,
        )
        for term in terms
    }

    cases, cache_info = load_cases_with_cache(
        repo_root,
        use_cache=not args.no_cache,
        cache_dir_arg=args.cache_dir,
    )
    case_index = build_case_index(cases)
    ranked = []
    need_snippet = args.show_snippet or args.assert_only or args.emit_reading_pack
    for case in cases:
        if not case_allowed(case, args):
            continue
        match_index = build_case_match_index(case)
        score_card = score_case(case, term_profiles, match_index)
        if score_card["query_signal_score"] <= 0 or score_card["score"] <= 0:
            continue
        item = {
            "case_name": case["case_name"],
            "file": case["file"],
            "file_name": case["file_name"],
            "line": case["line"],
            "register_status": case["register_status"],
            "symbol_kind": case["symbol_kind"],
            "score": score_card["score"],
            "query_signal_score": score_card["query_signal_score"],
            "quality_bonus": score_card["quality_bonus"],
            "matched_terms": score_card["matched_terms"],
            "significant_matched_terms": score_card["significant_matched_terms"],
            "match_notes": build_match_notes(case, score_card),
            "learning_focus": build_learning_focus(case),
            "similarity_tokens": build_similarity_tokens(case),
            "name_tokens": build_name_tokens(case),
        }
        if args.explain_score:
            item["score_explain"] = {
                "score": score_card["score"],
                "query_signal_score": score_card["query_signal_score"],
                "quality_bonus": score_card["quality_bonus"],
                "matched_terms": score_card["matched_terms"],
                "significant_matched_terms": score_card["significant_matched_terms"],
                "focus_hits": item.get("focus_hits", []),
                "focus_misses": item.get("focus_misses", []),
            }
        item.update(build_focus_coverage(match_index, focus_terms, term_profiles))
        if args.explain_score:
            item["score_explain"].update(
                {
                    "focus_hits": item.get("focus_hits", []),
                    "focus_misses": item.get("focus_misses", []),
                    "focus_weighted_ratio": item.get("focus_weighted_ratio", 0.0),
                    "significant_focus_hits": item.get("significant_focus_hits", []),
                    "significant_focus_total": item.get("significant_focus_total", 0),
                }
            )
        if need_snippet:
            snippet_builder = build_assert_focused_snippet if args.assert_only else build_snippet
            item["snippet"] = snippet_builder(case["body"], args.snippet_lines)
            related_helper = find_related_helper(case, case_index)
            if related_helper:
                helper_match_index = build_case_match_index(related_helper)
                helper_score_card = score_case(related_helper, term_profiles, helper_match_index)
                item["related_helper"] = {
                    "case_name": related_helper["case_name"],
                    "file": related_helper["file"],
                    "line": related_helper["line"],
                    "symbol_kind": related_helper["symbol_kind"],
                    "match_notes": build_match_notes(related_helper, helper_score_card),
                    "snippet": snippet_builder(
                        related_helper["body"],
                        args.snippet_lines,
                    ),
                }
        ranked.append(item)

    ranked.sort(key=lambda item: (-item["score"], item["case_name"]))
    results = annotate_reference_relationships(
        select_results_with_diversity(ranked, max(args.limit, 1))
    )

    payload = {
        "repo_root": str(repo_root),
        "query_terms": terms,
        "focus_terms": focus_terms,
        "searched_case_count": len(cases),
        "result_count": len(results),
        "cache": cache_info,
        "results": results,
    }
    payload.update(build_retrieval_assessment(results, focus_terms, terms))
    payload["retrieval_quality"] = build_quality_report(results, focus_terms)
    if args.emit_reading_pack:
        payload["reading_pack"] = render_reading_pack(payload)

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    if args.emit_reading_pack:
        print(payload["reading_pack"])
        return 0

    print(f"HYPTEST_HOME: {payload['repo_root']}")
    print(f"query_terms: {summarize_terms(payload['query_terms'])}")
    print(f"focus_terms: {summarize_terms(payload['focus_terms'])}")
    print(f"retrieval_status: {payload['retrieval_status']}")
    print(f"retrieval_reason: {payload['retrieval_reason']}")
    print(f"searched_cases: {payload['searched_case_count']}")
    cache = payload.get("cache", {})
    if cache.get("enabled"):
        state = "hit" if cache.get("hit") else "miss"
        print(f"cache: {state} {cache.get('path')}")
    print(f"top_results: {payload['result_count']}")
    if payload.get("fallback_plan"):
        for step in payload["fallback_plan"]:
            print(f"fallback: {step}")

    for index, item in enumerate(results, start=1):
        matched = summarize_terms(item["matched_terms"], limit=12)
        print(
            f"{index}. {item['case_name']} [{item['register_status']}, {item['symbol_kind']}, {item.get('reference_role', 'reference')}] "
            f"score={item['score']} matched={matched}"
        )
        print(f"   file: {item['file']}:{item['line']}")
        if item.get("selection_note"):
            print(f"   select: {item['selection_note']}")
        if item.get("reading_hint"):
            print(f"   read: {item['reading_hint']}")
        if item.get("focus_hits") is not None:
            focus_hits = item.get("focus_hits", [])
            focus_misses = item.get("focus_misses", [])
            total_focus = len(focus_hits) + len(focus_misses)
            print(f"   focus: {len(focus_hits)}/{total_focus} hit")
            print(f"   focus_weighted: {item.get('focus_weighted_ratio', 0.0):.2f}")
            print(
                "   focus_specific: "
                f"{len(item.get('significant_focus_hits', []))}/{item.get('significant_focus_total', 0)}"
            )
        print(
            "   signal: "
            f"query={item.get('query_signal_score', 0.0)} "
            f"quality={item.get('quality_bonus', 0)}"
        )
        if args.explain_score and item.get("score_explain"):
            explain = item["score_explain"]
            print(
                "   score_explain: "
                f"score={explain['score']} "
                f"query_signal={explain['query_signal_score']} "
                f"quality_bonus={explain['quality_bonus']} "
                f"focus_weighted={explain.get('focus_weighted_ratio', 0.0)}"
            )
            if explain.get("significant_matched_terms"):
                print(
                    "   score_terms: "
                    + summarize_terms(explain["significant_matched_terms"], limit=10)
                )
        if need_snippet and "snippet" in item:
            for snippet_line in item["snippet"].splitlines():
                print(f"   | {snippet_line}")
        if item.get("match_notes"):
            for note in item["match_notes"]:
                print(f"   note: {note}")
        if need_snippet and "related_helper" in item:
            helper = item["related_helper"]
            print(
                f"   helper: {helper['case_name']} "
                f"[{helper['symbol_kind']}] {helper['file']}:{helper['line']}"
            )
            for snippet_line in helper["snippet"].splitlines():
                print(f"   > {snippet_line}")

    if not results:
        print("No matching cases found. Broaden the query terms or inspect manually with rg.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
