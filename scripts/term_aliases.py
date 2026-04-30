#!/usr/bin/env python3
"""Shared term canonicalization and alias expansion helpers."""

from __future__ import annotations

import re
from typing import List


TERM_ALIAS_GROUPS = (
    ("cross16b", "cross_16b", "cross-16b"),
    ("crosspage", "cross_page", "cross-page"),
    ("samepage", "same_page", "same-page"),
    ("sameaddress", "same_address", "same-address"),
    ("widthswitch", "width_switch", "width-switch"),
    ("pagefault", "page_fault", "page-fault"),
    ("accessfault", "access_fault", "access-fault"),
)
TERM_ALIAS_BY_KEY = {
    re.sub(r"[-_]", "", alias.lower()): tuple(group)
    for group in TERM_ALIAS_GROUPS
    for alias in group
}


def canonical_term_key(term: str) -> str:
    return re.sub(r"[-_]", "", term.lower())


def expand_search_aliases(term: str) -> List[str]:
    raw = term.lower()
    candidates = {raw}

    if "-" in raw or "_" in raw:
        candidates.add(raw.replace("-", "_"))
        candidates.add(raw.replace("_", "-"))
        candidates.add(raw.replace("-", "").replace("_", ""))

    alias_group = TERM_ALIAS_BY_KEY.get(canonical_term_key(raw))
    if alias_group:
        candidates.update(alias_group)

    ordered = [raw]
    for candidate in sorted(candidates):
        if candidate != raw:
            ordered.append(candidate)
    return ordered


def dedupe_terms_by_canonical_key(terms: List[str]) -> List[str]:
    deduped: List[str] = []
    seen = set()
    for term in terms:
        key = canonical_term_key(term)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(term)
    return deduped
