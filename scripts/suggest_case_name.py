#!/usr/bin/env python3
"""Suggest hyptest case names and check repo-wide naming conflicts."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from repo_evidence_index import load_or_build
from skill_config import expand_path, resolve_path


IDENT_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]*")
CASE_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
STOP_WORDS = {
    "case",
    "test",
    "tests",
    "point",
    "points",
    "scenario",
    "scenarios",
    "default",
    "manual",
    "compile",
    "only",
    "with",
    "then",
    "when",
    "that",
    "this",
    "from",
    "into",
    "after",
    "before",
    "where",
    "should",
    "must",
    "the",
    "and",
    "for",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Suggest ai_arch/ai_micro case names from preflight/test-point evidence."
    )
    parser.add_argument("--repo-root", required=True, help="Path to hyptest repo root.")
    parser.add_argument("--preflight-json", help="Optional case_preflight_pack.py JSON report.")
    parser.add_argument("--from-file", help="Optional test_point markdown file to mine terms from.")
    parser.add_argument("--query", action="append", default=[], help="Extra naming term; can be repeated.")
    parser.add_argument(
        "--prefix",
        default="ai_micro",
        choices=["ai_micro", "ai_arch", "ai"],
        help="Preferred case name prefix.",
    )
    parser.add_argument("--limit", type=int, default=5, help="Number of suggestions.")
    parser.add_argument("--no-cache", action="store_true", help="Do not use repo evidence index cache.")
    parser.add_argument("--json", action="store_true", help="Emit JSON report.")
    return parser.parse_args()


def load_json(path_arg: str | None) -> dict[str, Any]:
    if not path_arg:
        return {}
    path = Path(path_arg).expanduser()
    if not path.is_file():
        raise FileNotFoundError(str(path))
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root is not an object: {path}")
    return payload


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore") if path.is_file() else ""


def normalize_token(raw: str) -> str:
    token = raw.strip("_").lower()
    token = re.sub(r"[^a-z0-9_]+", "_", token)
    token = re.sub(r"_+", "_", token).strip("_")
    return token


def collect_terms(args: argparse.Namespace, preflight: dict[str, Any]) -> list[str]:
    raw_terms: list[str] = []
    raw_terms.extend(args.query)
    raw_terms.extend(preflight.get("commands", {}).get("similar_cases", {}).get("payload", {}).get("focus_terms", []))
    raw_terms.extend(preflight.get("commands", {}).get("similar_cases", {}).get("payload", {}).get("query_terms", []))
    raw_terms.append(preflight.get("target_test_point_excerpt", ""))
    if args.from_file:
        raw_terms.append(read_text(expand_path(args.from_file)))
    terms: list[str] = []
    seen: set[str] = set()
    for raw in raw_terms:
        for match in IDENT_RE.findall(str(raw)):
            token = normalize_token(match)
            if not token or token in STOP_WORDS or len(token) < 2:
                continue
            if token not in seen:
                seen.add(token)
                terms.append(token)
    return terms


def token_score(token: str) -> int:
    score = 1
    strong = [
        "memblock",
        "mprv",
        "mpp",
        "pmp",
        "pte",
        "pbmt",
        "cbo",
        "sfence",
        "amo",
        "fault",
        "misalign",
        "store",
        "load",
        "fetch",
        "page",
        "access",
        "tlb",
        "retry",
        "boundary",
    ]
    if token in strong:
        score += 4
    if "_" in token:
        score += 1
    if len(token) <= 14:
        score += 1
    return score


def select_base_terms(terms: list[str], limit: int = 7) -> list[str]:
    ordered = sorted(terms, key=lambda term: (-token_score(term), terms.index(term), term))
    selected: list[str] = []
    for term in ordered:
        if any(term == old or term in old or old in term for old in selected):
            continue
        selected.append(term)
        if len(selected) >= limit:
            break
    return selected


def existing_case_names(index: dict[str, Any]) -> set[str]:
    return {str(item.get("case_name")) for item in index.get("cases", []) if item.get("case_name")}


def find_similar_names(candidate: str, names: set[str]) -> list[str]:
    candidate_terms = set(candidate.split("_"))
    hits: list[tuple[int, str]] = []
    for name in names:
        name_terms = set(name.split("_"))
        overlap = len(candidate_terms & name_terms)
        if overlap >= max(3, min(len(candidate_terms), 5)):
            hits.append((overlap, name))
    hits.sort(key=lambda item: (-item[0], item[1]))
    return [name for _score, name in hits[:5]]


def build_candidates(prefix: str, terms: list[str], existing: set[str], limit: int) -> list[dict[str, Any]]:
    base_terms = select_base_terms(terms)
    variants: list[list[str]] = []
    if base_terms:
        variants.append(base_terms[:6])
    if len(base_terms) >= 4:
        variants.append(base_terms[:3] + base_terms[-2:])
    if len(base_terms) >= 3:
        variants.append(base_terms[:3])
    if len(base_terms) >= 5:
        variants.append([base_terms[0], base_terms[2], base_terms[3], base_terms[4]])
    if not variants:
        variants.append(["new", "case"])

    suggestions: list[dict[str, Any]] = []
    seen: set[str] = set()
    for parts in variants:
        candidate = normalize_token("_".join([prefix, *parts]))
        if not CASE_NAME_RE.match(candidate) or candidate in seen:
            continue
        seen.add(candidate)
        exact = candidate in existing
        similar = find_similar_names(candidate, existing)
        suggestions.append(
            {
                "name": candidate,
                "exact_conflict": exact,
                "similar_existing": similar,
                "usable": not exact,
                "rationale": "prefix plus strongest scenario terms from preflight/test_point evidence",
            }
        )
        if len(suggestions) >= limit:
            break
    suffix = 2
    while len(suggestions) < limit and base_terms:
        candidate = normalize_token("_".join([prefix, *base_terms[:5], str(suffix)]))
        suffix += 1
        if candidate in seen:
            continue
        seen.add(candidate)
        suggestions.append(
            {
                "name": candidate,
                "exact_conflict": candidate in existing,
                "similar_existing": find_similar_names(candidate, existing),
                "usable": candidate not in existing,
                "rationale": "numeric suffix fallback to avoid exact conflicts",
            }
        )
    return suggestions


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    preflight = load_json(args.preflight_json)
    repo_root = resolve_path(args.repo_root)
    # Reuse repo_evidence_index cache behavior without exposing an extra CLI cache-dir surface here.
    index_args = argparse.Namespace(no_cache=args.no_cache, cache_dir=None)
    index, cache = load_or_build(repo_root, index_args)
    terms = collect_terms(args, preflight)
    existing = existing_case_names(index)
    suggestions = build_candidates(args.prefix, terms, existing, max(args.limit, 1))
    return {
        "repo_root": str(repo_root),
        "prefix": args.prefix,
        "terms": terms[:40],
        "cache": cache,
        "existing_case_count": len(existing),
        "suggestions": suggestions,
        "decision_note": (
            "These are naming suggestions only. Final case names still require repo-level "
            "similar-case review and exact uniqueness checks before editing."
        ),
        "ok": any(item.get("usable") for item in suggestions),
    }


def render_text(report: dict[str, Any]) -> str:
    lines = ["# hyptest case name suggestions", ""]
    lines.append(f"- repo_root: `{report.get('repo_root')}`")
    lines.append(f"- prefix: `{report.get('prefix')}`")
    lines.append(f"- existing_case_count: `{report.get('existing_case_count')}`")
    cache = report.get("cache") or {}
    lines.append(f"- repo_index_cache_hit: `{cache.get('hit')}`")
    lines.extend(["", "## Suggestions", ""])
    for item in report.get("suggestions", []):
        lines.append(
            f"- `{item.get('name')}` usable=`{item.get('usable')}` exact_conflict=`{item.get('exact_conflict')}`"
        )
        if item.get("similar_existing"):
            lines.append(f"  - similar_existing: `{', '.join(item.get('similar_existing', [])[:5])}`")
    lines.extend(["", "## Decision Boundary", "", report.get("decision_note", ""), ""])
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    try:
        report = build_report(args)
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_text(report))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
