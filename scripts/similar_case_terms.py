#!/usr/bin/env python3
"""Term extraction and scoring helpers for find_similar_cases.py."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List

from markdown_sections import (
    MARKDOWN_HEADING_RE,
    filter_markdown_sections_by_heading,
    pick_markdown_section_by_index,
    split_markdown_sections,
)
from term_aliases import (
    TERM_ALIAS_BY_KEY,
    canonical_term_key,
    dedupe_terms_by_canonical_key,
    expand_search_aliases,
)

CASE_NAME_RE = r"[A-Za-z_][A-Za-z0-9_]*"
FUNC_RE = re.compile(
    rf"^\s*(?:static\s+)?bool\s+({CASE_NAME_RE})\s*\(",
    re.MULTILINE,
)
REGISTER_RE = re.compile(rf"TEST_REGISTER\s*\(\s*({CASE_NAME_RE})\s*\)")
TOKEN_RE = re.compile(r"`([^`]+)`|([A-Za-z_][A-Za-z0-9_./+-]*)")
INNER_TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_+-]*|\d+[Bb]\+\d+[Bb]")
LINE_RE = re.compile(r"\r?\n")
CALL_RE = re.compile(rf"\b({CASE_NAME_RE})\s*\(")
POINT_ID_RE = re.compile(r"^p\d+[a-z]?$")
BYTE_TOKEN_RE = re.compile(r"^byte\d+$|^bytes\d+\-\d+$")
BOUNDARY_OFFSET_RE = re.compile(r"^boundary\+\d+$")
SEARCH_UNIT_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_+-]*")

STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "that",
    "this",
    "from",
    "into",
    "then",
    "when",
    "need",
    "case",
    "cases",
    "test",
    "point",
    "file",
    "path",
    "mode",
    "only",
    "default",
    "manual",
    "compile",
    "enabled",
    "commented",
    "implemented",
    "should",
    "would",
    "there",
    "where",
    "which",
    "after",
    "before",
    "using",
    "used",
    "same",
    "still",
    "keep",
    "into",
    "true",
    "false",
}

SHORT_ALLOWLIST = {
    "hs",
    "hu",
    "af",
    "pf",
    "tlb",
    "pma",
    "pbmt",
    "amo",
    "csr",
}

DOMAIN_TERMS = {
    "load",
    "store",
    "amo",
    "prefetch",
    "sfence",
    "fault",
    "refault",
    "repair",
    "retry",
    "replay",
    "translated",
    "translation",
    "misalign",
    "misaligned",
    "cross_page",
    "cross-page",
    "cross_16b",
    "cross-16b",
    "same-page",
    "same_address",
    "same-address",
    "width_switch",
    "width-switch",
    "boundary",
    "guard",
    "overlay",
    "pmp",
    "pma",
    "pbmt",
    "tlb",
    "cache",
    "uncache",
    "mprv",
    "mpp",
    "csr",
    "trigger",
    "page_fault",
    "access_fault",
    "page",
    "access",
    "hs",
    "hu",
    "mab",
    "memblock",
}

INTERESTING_MARKERS = (
    "TEST_ASSERT(",
    "TEST_SETUP_EXCEPT(",
    "goto_priv(",
    "sfence_vma(",
    "TEST_END(",
)
CALL_TARGET_IGNORE = {
    "TEST_START",
    "TEST_END",
    "TEST_ASSERT",
    "TEST_SETUP_EXCEPT",
    "sizeof",
    "for",
    "if",
    "while",
    "switch",
    "return",
}

LOCATION_FILE_HINTS = (".scala", ".c", ".cc", ".cpp", ".h", ".hpp", ".s", ".py", ".md")
MARKDOWN_INCLUDE_LABELS = {"测试点", "构建场景", "对应场景"}
MARKDOWN_EXCLUDE_LABELS = {"怀疑点", "已实现 case", "复用依据"}
FILE_SOURCE_BONUS = {
    "heading": 28,
    "测试点": 24,
    "对应场景": 14,
    "构建场景": 10,
    "plain": 0,
}
FILE_LOW_SIGNAL_TERMS = {
    "no-h",
    "m-mode",
    "s-mode",
    "u-mode",
    "mprv",
    "mpp",
    "trap-free",
    "excpt",
    "triggered",
    "fault_vaddr",
}
FILE_PRIORITY_KEYWORDS = (
    "memblock",
    "mab",
    "retry",
    "repair",
    "refault",
    "fault",
    "cross",
    "same",
    "width",
    "template",
    "owner",
    "producer",
    "consumer",
    "store",
    "load",
    "amo",
    "misalign",
    "translated",
    "boundary",
    "guard",
    "overlay",
    "bridge",
    "head",
    "tail",
    "upper",
    "lower",
    "word",
    "halfword",
    "byte",
    "lane",
    "pmp",
    "pma",
    "pbmt",
    "cache",
    "uncache",
)
SIMILARITY_STOPWORDS = STOPWORDS | {
    "ai",
    "micro",
    "arch",
    "mmode",
    "smode",
    "umode",
    "hmode",
    "corner",
    "followup",
    "cases",
}
GENERIC_SIGNAL_TERMS = {
    "fault",
    "store",
    "load",
    "retry",
    "repair",
    "page",
    "access",
    "translated",
    "translation",
    "boundary",
    "guard",
    "memblock",
    "mab",
}
SPECIFIC_SIGNAL_KEYWORDS = (
    "cross",
    "same",
    "width",
    "template",
    "overlay",
    "bridge",
    "head",
    "tail",
    "upper",
    "lower",
    "halfword",
    "byte",
    "word",
    "producer",
    "consumer",
    "adjacent",
    "refault",
    "page_fault",
    "access_fault",
    "uncache",
    "cacheable",
)
SIGNIFICANT_TERM_WEIGHT = 4.0

def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def summarize_terms(terms: List[str], limit: int = 16) -> str:
    if len(terms) <= limit:
        return ", ".join(terms)
    preview = ", ".join(terms[:limit])
    return f"{preview} ... (+{len(terms) - limit} more)"


def is_location_reference(source: str) -> bool:
    lowered = source.lower()
    return "/" in source and any(hint in lowered for hint in LOCATION_FILE_HINTS)


def iter_candidate_terms(text: str) -> List[str]:
    terms: List[str] = []
    for backtick_token, plain_token in TOKEN_RE.findall(text):
        source = backtick_token or plain_token
        if not source:
            continue
        location_source = is_location_reference(source)
        for raw_token in INNER_TOKEN_RE.findall(source):
            token = raw_token.strip().lower()
            if not token:
                continue
            token = token.split("/")[-1]
            token = token.split(".")[0]
            token = token.strip("_-+")
            if not token:
                continue
            if token.startswith("0x"):
                continue
            if POINT_ID_RE.fullmatch(token):
                continue
            if token in STOPWORDS:
                continue
            if len(token) < 3 and token not in SHORT_ALLOWLIST:
                continue
            if location_source and token not in DOMAIN_TERMS and not token.startswith("ai_"):
                continue
            if not backtick_token:
                looks_code_like = (
                    "_" in raw_token
                    or "-" in raw_token
                    or any(ch.isdigit() for ch in raw_token)
                    or token.startswith("ai_")
                    or token in DOMAIN_TERMS
                )
                if not looks_code_like:
                    continue
            terms.append(token)
    return terms


def extract_terms(text: str) -> List[str]:
    seen = set()
    terms: List[str] = []
    for token in iter_candidate_terms(text):
        if token not in seen:
            seen.add(token)
            terms.append(token)
    return terms


def is_valid_search_fragment(fragment: str) -> bool:
    if not fragment:
        return False
    if fragment in STOPWORDS:
        return False
    if len(fragment) < 3 and fragment not in SHORT_ALLOWLIST:
        has_digit = any(ch.isdigit() for ch in fragment)
        has_alpha = any(ch.isalpha() for ch in fragment)
        if not (has_digit and has_alpha):
            return False
    return True


def build_search_key_stats(text: str, max_ngram: int = 3) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    tokens: List[str] = []

    for raw_unit in SEARCH_UNIT_RE.findall(text.lower()):
        unit = raw_unit.strip("_-")
        if not unit:
            continue

        raw_parts = [part.strip("_-") for part in re.split(r"[_-]+", unit) if part.strip("_-")]
        if not raw_parts:
            continue

        compound_parts = [part for part in raw_parts if any(ch.isalnum() for ch in part)]
        if len(compound_parts) > 1:
            compound_limit = min(len(compound_parts), max_ngram)
            for size in range(2, compound_limit + 1):
                for index in range(len(compound_parts) - size + 1):
                    key = canonical_term_key("".join(compound_parts[index : index + size]))
                    counts[key] = counts.get(key, 0) + 1

        for part in raw_parts:
            if not is_valid_search_fragment(part):
                continue
            tokens.append(part)

    for token in tokens:
        key = canonical_term_key(token)
        counts[key] = counts.get(key, 0) + 1

    max_ngram = max(2, max_ngram)
    for size in range(2, max_ngram + 1):
        if len(tokens) < size:
            break
        for index in range(len(tokens) - size + 1):
            key = canonical_term_key("".join(tokens[index : index + size]))
            counts[key] = counts.get(key, 0) + 1

    return counts


def build_case_match_index(case: Dict[str, str]) -> Dict[str, Dict[str, int]]:
    return {
        "name": build_search_key_stats(case["case_name"]),
        "file": build_search_key_stats(Path(case["file_name"]).stem),
        "body": build_search_key_stats(case["body"]),
    }


def term_information_weight(term: str) -> float:
    lowered = term.lower()
    key = canonical_term_key(lowered)
    weight = 1.0

    if any(ch.isdigit() for ch in lowered):
        weight += 1.8
    if "+" in lowered:
        weight += 1.6
    if "_" in lowered or "-" in lowered:
        weight += 1.2
    if key in TERM_ALIAS_BY_KEY:
        weight += 0.8
    if len(lowered) >= 12:
        weight += 0.6
    if any(keyword in lowered for keyword in SPECIFIC_SIGNAL_KEYWORDS):
        weight += 1.4
    if key in GENERIC_SIGNAL_TERMS:
        weight -= 0.8

    return round(max(1.0, weight), 2)


def build_term_profile(
    term: str,
    is_focus_term: bool = False,
    is_explicit_term: bool = False,
) -> Dict[str, object]:
    alias_keys: List[str] = []
    seen = set()
    for alias in expand_search_aliases(term):
        key = canonical_term_key(alias)
        if key in seen:
            continue
        seen.add(key)
        alias_keys.append(key)

    info_weight = term_information_weight(term)
    return {
        "term": term,
        "alias_keys": alias_keys,
        "information_weight": info_weight,
        "is_significant": info_weight >= SIGNIFICANT_TERM_WEIGHT,
        "query_weight": 1.0 if (is_focus_term or is_explicit_term) else 0.45,
    }


def count_term_section_matches(
    match_index: Dict[str, Dict[str, int]],
    term_profile: Dict[str, object],
) -> Dict[str, int]:
    alias_keys = term_profile["alias_keys"]
    return {
        "name": max(match_index["name"].get(key, 0) for key in alias_keys),
        "file": max(match_index["file"].get(key, 0) for key in alias_keys),
        "body": max(match_index["body"].get(key, 0) for key in alias_keys),
    }


def build_focus_terms(terms: List[str], limit: int = 12) -> List[str]:
    ranked = sorted(
        enumerate(terms),
        key=lambda item: (-score_file_term(item[1]), item[0]),
    )
    selected = [term for _index, term in ranked[:limit]]
    return dedupe_terms_by_canonical_key(selected)


def score_file_term(term: str, source: str = "plain") -> int:
    if term in FILE_LOW_SIGNAL_TERMS:
        return -100
    if term.startswith("ai_"):
        return -80

    score = FILE_SOURCE_BONUS.get(source, 0)
    if term in DOMAIN_TERMS:
        score += 80
    if re.fullmatch(r"\d+[bB]\+\d+[bB]", term):
        score += 70
    if BYTE_TOKEN_RE.fullmatch(term):
        score += 28
    if BOUNDARY_OFFSET_RE.fullmatch(term):
        score += 24
    if any(keyword in term for keyword in FILE_PRIORITY_KEYWORDS):
        score += 32
    if any(ch.isdigit() for ch in term):
        score += 8
    if "-" in term or "_" in term:
        score += 6
    if len(term) >= 12:
        score += 4
    return score


def extract_markdown_term_records(text: str) -> List[Dict[str, object]]:
    records: Dict[str, Dict[str, object]] = {}
    include_current = False
    current_section = "plain"
    saw_include_section = False
    order = 0

    def add_terms(source: str, raw_text: str) -> None:
        nonlocal order
        for term in iter_candidate_terms(raw_text):
            key = canonical_term_key(term)
            existing = records.get(key)
            if existing is None:
                records[key] = {
                    "term": term,
                    "source": source,
                    "index": order,
                }
            else:
                old_source = str(existing["source"])
                if FILE_SOURCE_BONUS.get(source, 0) > FILE_SOURCE_BONUS.get(old_source, 0):
                    existing["term"] = term
                    existing["source"] = source
            order += 1

    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        normalized = stripped.rstrip(":：")

        if MARKDOWN_HEADING_RE.match(stripped):
            add_terms("heading", stripped)
            include_current = False
            current_section = "plain"
            continue

        if normalized in MARKDOWN_INCLUDE_LABELS:
            include_current = True
            current_section = normalized
            saw_include_section = True
            continue

        if normalized in MARKDOWN_EXCLUDE_LABELS:
            include_current = False
            current_section = "plain"
            continue

        if include_current and stripped:
            add_terms(current_section, raw_line)

    if not saw_include_section:
        return [
            {"term": term, "source": "plain", "index": index}
            for index, term in enumerate(extract_terms(text))
        ]

    return sorted(records.values(), key=lambda item: int(item["index"]))


def extract_latest_markdown_term_records(text: str) -> List[Dict[str, object]]:
    for section in reversed(split_markdown_sections(text)):
        section_text = section["text"]
        if not any(label in section_text for label in MARKDOWN_INCLUDE_LABELS):
            continue
        records = extract_markdown_term_records(section_text)
        if records:
            return records

    return []


def extract_selected_markdown_term_records(
    text: str,
    heading_pattern: str | None,
    section_index: int | None,
) -> List[Dict[str, object]]:
    sections = split_markdown_sections(text)
    if heading_pattern:
        sections = filter_markdown_sections_by_heading(sections, heading_pattern)
    if not sections:
        return []

    if section_index is not None:
        return extract_markdown_term_records(
            pick_markdown_section_by_index(sections, section_index)["text"]
        )

    return extract_markdown_term_records(sections[0]["text"])


def choose_auto_max_file_terms(records: List[Dict[str, object]]) -> int:
    filtered_scores = [
        score_file_term(str(record["term"]), str(record["source"]))
        for record in records
        if score_file_term(str(record["term"]), str(record["source"])) >= 0
    ]
    total = len(filtered_scores)
    if total <= 36:
        return total

    limit = 40
    if total > 64:
        limit = 48
    if total > 96:
        limit = 56
    if total > 144:
        limit = 64
    if total > 200:
        limit = 72

    strong = sum(score >= 100 for score in filtered_scores)
    if strong > limit * 0.75:
        limit += 8

    return min(limit, total)


def compress_file_term_records(
    records: List[Dict[str, object]],
    max_terms: int = 0,
) -> List[str]:
    filtered = [
        record
        for record in records
        if score_file_term(str(record["term"]), str(record["source"])) >= 0
    ]
    if not filtered:
        return []

    limit = max_terms if max_terms > 0 else choose_auto_max_file_terms(filtered)
    if len(filtered) <= limit:
        return [str(record["term"]) for record in filtered]

    ranked = sorted(
        enumerate(filtered),
        key=lambda item: (
            -score_file_term(str(item[1]["term"]), str(item[1]["source"])),
            int(item[1]["index"]),
        ),
    )
    keep_indexes = {index for index, _record in ranked[:limit]}
    return [str(record["term"]) for index, record in enumerate(filtered) if index in keep_indexes]


def extract_terms_from_file(
    path: Path,
    max_terms: int,
    heading_pattern: str | None = None,
    section_index: int | None = None,
) -> List[str]:
    text = read_text(path)
    if path.suffix.lower() == ".md":
        if heading_pattern or section_index is not None:
            selected_records = extract_selected_markdown_term_records(
                text,
                heading_pattern=heading_pattern,
                section_index=section_index,
            )
            return compress_file_term_records(selected_records, max_terms=max_terms)
        latest_records = extract_latest_markdown_term_records(text)
        global_records = extract_markdown_term_records(text)
        latest_terms = compress_file_term_records(
            latest_records,
            max_terms=min(max_terms, 24) if max_terms > 0 else 24,
        )
        if len(latest_terms) >= 6:
            return latest_terms
        global_terms = compress_file_term_records(global_records, max_terms=max_terms)
        latest_keys = {canonical_term_key(item) for item in latest_terms}
        return latest_terms + [
            term
            for term in global_terms
            if canonical_term_key(term) not in latest_keys
        ]
    return extract_terms(text)


def term_matches_case(
    match_index: Dict[str, Dict[str, int]],
    term_profile: Dict[str, object],
) -> bool:
    counts = count_term_section_matches(match_index, term_profile)
    return any(counts.values())
