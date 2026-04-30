#!/usr/bin/env python3
"""
Compatibility re-export for the split find_similar_cases.py helper modules.

New code should import from case_extractor.py, similar_case_ranker.py,
similar_case_render.py, and similar_case_terms.py directly.
"""

from case_extractor import (  # noqa: F401
    build_case_index,
    collect_call_targets,
    extract_cases,
    find_line_number,
    find_related_helper,
    load_cases_with_cache,
    load_registration_status,
)
from similar_case_ranker import (  # noqa: F401
    annotate_reference_relationships,
    build_distinguishing_tokens,
    build_fallback_plan,
    build_name_tokens,
    build_partial_reference_summary,
    build_retrieval_assessment,
    build_similarity_tokens,
    ordered_prefix_similarity,
    score_case,
    select_results_with_diversity,
    similarity_token_weight,
    weighted_token_similarity,
)
from similar_case_render import (  # noqa: F401
    build_assert_focused_snippet,
    build_focus_coverage,
    build_learning_focus,
    build_match_notes,
    build_snippet,
    case_allowed,
    render_reading_pack,
)
from similar_case_terms import summarize_terms  # noqa: F401
