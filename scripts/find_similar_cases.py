#!/usr/bin/env python3
"""
Rank similar existing hyptest cases from ai_test_cases/*.c.

The goal is not to auto-generate code, but to help the agent inspect a small
set of good reference cases before writing a new one.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple


FUNC_RE = re.compile(r"^\s*(?:static\s+)?bool\s+(ai_[A-Za-z0-9_]+)\s*\(", re.MULTILINE)
REGISTER_RE = re.compile(r"TEST_REGISTER\s*\(\s*(ai_[A-Za-z0-9_]+)\s*\)")
TOKEN_RE = re.compile(r"`([^`]+)`|([A-Za-z_][A-Za-z0-9_./+-]*)")
INNER_TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_+-]*|\d+[Bb]\+\d+[Bb]")
LINE_RE = re.compile(r"\r?\n")
CALL_RE = re.compile(r"\b(ai_[A-Za-z0-9_]+)\s*\(")
POINT_ID_RE = re.compile(r"^p\d+[a-z]?$")
MARKDOWN_HEADING_RE = re.compile(r"^#{1,6}\s+")
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Find similar ai_test_cases before writing a new hyptest case."
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
        help="Restrict matches to ai_test_cases file globs; can be repeated",
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


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


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


def split_markdown_sections(text: str) -> List[Dict[str, str]]:
    sections: List[Dict[str, str]] = []
    current_lines: List[str] = []
    current_heading = ""

    def flush_current() -> None:
        if not current_lines:
            return
        sections.append(
            {
                "heading": current_heading,
                "text": "\n".join(current_lines),
            }
        )

    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if MARKDOWN_HEADING_RE.match(stripped):
            flush_current()
            current_heading = MARKDOWN_HEADING_RE.sub("", stripped).strip()
            current_lines = [raw_line]
            continue
        current_lines.append(raw_line)

    flush_current()
    return sections


def extract_latest_markdown_term_records(text: str) -> List[Dict[str, object]]:
    for section in reversed(split_markdown_sections(text)):
        section_text = section["text"]
        if not any(label in section_text for label in MARKDOWN_INCLUDE_LABELS):
            continue
        records = extract_markdown_term_records(section_text)
        if records:
            return records

    return []


def filter_markdown_sections_by_heading(
    sections: List[Dict[str, str]],
    heading_pattern: str,
) -> List[Dict[str, str]]:
    matcher = re.compile(heading_pattern, re.IGNORECASE)
    return [section for section in sections if matcher.search(section["heading"])]


def pick_markdown_section_by_index(
    sections: List[Dict[str, str]],
    section_index: int,
) -> Dict[str, str]:
    if section_index == 0:
        raise ValueError("--section-index must not be 0")

    index = section_index - 1 if section_index > 0 else len(sections) + section_index
    if index < 0 or index >= len(sections):
        raise IndexError(
            f"--section-index {section_index} is out of range for {len(sections)} matching sections"
        )
    return sections[index]


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


def load_registration_status(repo_root: Path) -> Dict[str, str]:
    status: Dict[str, str] = {}
    register_path = repo_root / "test_register.c"
    if not register_path.exists():
        return status

    for line in read_text(register_path).splitlines():
        match = REGISTER_RE.search(line)
        if not match:
            continue
        case_name = match.group(1)
        stripped = line.strip()
        if stripped.startswith("//") or stripped.startswith("/*") or stripped.startswith("*"):
            status[case_name] = "commented"
        else:
            status[case_name] = "enabled"
    return status


def find_line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


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
            if remaining <= 0:
                break
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


def collect_call_targets(body: str, case_name: str) -> List[str]:
    targets: List[str] = []
    seen = set()
    for target in CALL_RE.findall(body):
        if target == case_name:
            continue
        if target not in seen:
            seen.add(target)
            targets.append(target)
    return targets


def extract_cases(repo_root: Path) -> List[Dict[str, str]]:
    ai_dir = repo_root / "ai_test_cases"
    if not ai_dir.is_dir():
        raise FileNotFoundError(f"Missing ai_test_cases directory under {repo_root}")

    register_status = load_registration_status(repo_root)
    cases: List[Dict[str, str]] = []

    for path in sorted(ai_dir.glob("*.c")):
        text = read_text(path)
        matches = list(FUNC_RE.finditer(text))
        for idx, match in enumerate(matches):
            case_name = match.group(1)
            start = match.start()
            end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
            body = text[start:end]
            line_number = find_line_number(text, start)
            signature_text = text[start : match.end()]
            cases.append(
                {
                    "case_name": case_name,
                    "file": str(path),
                    "file_name": path.name,
                    "body": body,
                    "line": line_number,
                    "symbol_kind": "static_helper"
                    if "static" in signature_text
                    else "case",
                    "register_status": register_status.get(case_name, "unregistered"),
                }
            )
    return cases


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
    focus_total = max(1, len(focus_terms))
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


def build_match_notes(case: Dict[str, str], score_card: Dict[str, object]) -> List[str]:
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


def summarize_terms(terms: List[str], limit: int = 16) -> str:
    if len(terms) <= limit:
        return ", ".join(terms)
    preview = ", ".join(terms[:limit])
    return f"{preview} ... (+{len(terms) - limit} more)"


def render_reading_pack(payload: Dict[str, object]) -> str:
    lines: List[str] = []
    lines.append("# Similar Case Reading Pack")
    lines.append("")
    lines.append(f"repo_root: {payload['repo_root']}")
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


def build_case_index(cases: List[Dict[str, str]]) -> Dict[str, Dict[str, str]]:
    return {case["case_name"]: case for case in cases}


def find_related_helper(
    case: Dict[str, str],
    case_index: Dict[str, Dict[str, str]],
) -> Dict[str, str] | None:
    candidates: List[Tuple[int, Dict[str, str]]] = []
    for target in collect_call_targets(case["body"], case["case_name"]):
        helper = case_index.get(target)
        if not helper:
            continue
        richness = 0
        helper_body = helper["body"]
        richness += helper_body.count("TEST_ASSERT(") * 5
        richness += helper_body.count("TEST_SETUP_EXCEPT(") * 3
        richness += helper_body.count("goto_priv(")
        if helper["file"] == case["file"]:
            richness += 4
        if helper["symbol_kind"] == "static_helper":
            richness += 2
        if richness > 0:
            candidates.append((richness, helper))

    if not candidates:
        return None

    candidates.sort(key=lambda item: (-item[0], item[1]["case_name"]))
    return candidates[0][1]


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).expanduser().resolve()

    explicit_terms = [term.strip().lower() for term in args.query if term.strip()]
    terms = list(explicit_terms)
    if args.from_file:
        from_file = Path(args.from_file).expanduser().resolve()
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

    cases = extract_cases(repo_root)
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
        item.update(build_focus_coverage(match_index, focus_terms, term_profiles))
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
        "results": results,
    }
    payload.update(build_retrieval_assessment(results, focus_terms, terms))
    if args.emit_reading_pack:
        payload["reading_pack"] = render_reading_pack(payload)

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    if args.emit_reading_pack:
        print(payload["reading_pack"])
        return 0

    print(f"repo_root: {payload['repo_root']}")
    print(f"query_terms: {summarize_terms(payload['query_terms'])}")
    print(f"focus_terms: {summarize_terms(payload['focus_terms'])}")
    print(f"retrieval_status: {payload['retrieval_status']}")
    print(f"retrieval_reason: {payload['retrieval_reason']}")
    print(f"searched_cases: {payload['searched_case_count']}")
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
