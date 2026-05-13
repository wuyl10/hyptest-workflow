#!/usr/bin/env python3
"""Case extraction and cache helpers for find_similar_cases.py."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Tuple

from similar_case_cache import load_with_cache
from similar_case_terms import (
    CALL_RE,
    CALL_TARGET_IGNORE,
    FUNC_RE,
    REGISTER_RE,
    read_text,
)
from writeback_register import load_registration_status as _load_registration_status


def load_registration_status(repo_root: Path) -> Dict[str, str]:
    """Delegate to writeback_register.py — single source of truth for register parsing."""
    return _load_registration_status(repo_root)


def find_line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def collect_call_targets(body: str, case_name: str) -> List[str]:
    targets: List[str] = []
    seen = set()
    for target in CALL_RE.findall(body):
        if target == case_name:
            continue
        if target in CALL_TARGET_IGNORE:
            continue
        if target not in seen:
            seen.add(target)
            targets.append(target)
    return targets


def extract_cases(repo_root: Path) -> List[Dict[str, str]]:
    source_roots = [
        repo_root / "ai_test_cases",
        repo_root / "manual_test_cases",
    ]
    existing_roots = [path for path in source_roots if path.is_dir()]
    if not existing_roots:
        raise FileNotFoundError(
            f"Missing ai_test_cases and manual_test_cases directories under {repo_root}"
        )

    register_status = load_registration_status(repo_root)
    cases: List[Dict[str, str]] = []

    source_files: List[Path] = []
    for root in existing_roots:
        source_files.extend(sorted(root.rglob("*.c")))

    for path in sorted(source_files):
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
                    "file": str(path.relative_to(repo_root)),
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


def load_cases_with_cache(
    repo_root: Path,
    *,
    use_cache: bool,
    cache_dir_arg: str | None,
) -> Tuple[List[Dict[str, str]], Dict[str, object]]:
    return load_with_cache(
        repo_root,
        use_cache=use_cache,
        cache_dir_arg=cache_dir_arg,
        builder=extract_cases,
    )


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
