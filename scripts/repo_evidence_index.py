#!/usr/bin/env python3
"""Build a cached repo-wide evidence index for hyptest workflow preflight."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any

from case_extractor import extract_cases
from skill_config import resolve_path
from workflow_paths import cache_file


CACHE_VERSION = 1
HEADING_RE = re.compile(r"^(###\s+P[0-9A-Za-z][^\n]*)", re.MULTILINE)
IMPLEMENTED_CASE_RE = re.compile(r"^\s*-\s*`([A-Za-z_][A-Za-z0-9_]*)`", re.MULTILINE)
# Reference files and subdirs under test_point/ that do not carry PnX entries.
NON_ENTRY_REFERENCE_STEMS = frozenset({"manual_reference", "critical_issues_log"})
NON_ENTRY_REFERENCE_DIRS = frozenset({"reference_tables"})


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build/cache a repo-wide case, test_point, and register evidence index."
    )
    parser.add_argument("--repo-root", required=True, help="Path to hyptest repo root.")
    parser.add_argument("--query", action="append", default=[], help="Optional term to match in test_point entries.")
    parser.add_argument("--limit", type=int, default=20, help="Maximum query hits to report.")
    parser.add_argument("--no-cache", action="store_true", help="Rebuild without reading/writing the cache.")
    parser.add_argument(
        "--cache-dir",
        help="Override cache directory. Default: <repo-root>/.hyptest_workflow_skill/cache",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON report.")
    return parser.parse_args()


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore") if path.is_file() else ""


def source_paths(repo_root: Path) -> list[Path]:
    paths: list[Path] = []
    for rel, suffix in (
        ("ai_test_cases", "*.c"),
        ("manual_test_cases", "*.c"),
        ("test_point", "*.md"),
    ):
        root = repo_root / rel
        if root.is_dir():
            paths.extend(sorted(root.rglob(suffix)))
    register = repo_root / "test_register.c"
    if register.is_file():
        paths.append(register)
    return sorted(paths)


def source_fingerprint(repo_root: Path) -> dict[str, Any]:
    digest = hashlib.sha256()
    entries: list[dict[str, Any]] = []
    for path in source_paths(repo_root):
        rel = str(path.relative_to(repo_root))
        stat = path.stat()
        entry = {"path": rel, "mtime_ns": stat.st_mtime_ns, "size": stat.st_size}
        entries.append(entry)
        digest.update(rel.encode("utf-8"))
        digest.update(str(stat.st_mtime_ns).encode("ascii"))
        digest.update(str(stat.st_size).encode("ascii"))
    return {"version": CACHE_VERSION, "digest": digest.hexdigest(), "entries": entries}


def cache_path(repo_root: Path, cache_dir_arg: str | None) -> Path:
    if cache_dir_arg:
        return resolve_path(cache_dir_arg) / "repo_evidence_index.json"
    return cache_file(repo_root, "repo_evidence_index.json")


def split_heading_sections(text: str) -> list[tuple[str, int, str]]:
    matches = list(HEADING_RE.finditer(text))
    sections: list[tuple[str, int, str]] = []
    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        line = text.count("\n", 0, start) + 1
        sections.append((match.group(1).strip(), line, text[start:end]))
    return sections


def build_test_point_entries(repo_root: Path) -> list[dict[str, Any]]:
    base = repo_root / "test_point"
    if not base.is_dir():
        return []
    entries: list[dict[str, Any]] = []
    for path in sorted(base.rglob("*.md")):
        if path.stem.lower() in NON_ENTRY_REFERENCE_STEMS:
            continue
        try:
            top = path.relative_to(base).parts[0] if path.relative_to(base).parts else ""
        except ValueError:
            top = ""
        if top in NON_ENTRY_REFERENCE_DIRS:
            continue
        text = read_text(path)
        for heading, line, section in split_heading_sections(text):
            implemented = IMPLEMENTED_CASE_RE.findall(section)
            excerpt = "\n".join(section.splitlines()[:24])
            entries.append(
                {
                    "file": str(path.relative_to(repo_root)),
                    "line": line,
                    "heading": heading,
                    "implemented_cases": implemented,
                    "excerpt": excerpt,
                }
            )
    return entries


def register_summary(cases: list[dict[str, Any]]) -> dict[str, int]:
    summary = {"enabled": 0, "commented": 0, "unregistered": 0}
    for case in cases:
        status = str(case.get("register_status", "unregistered"))
        summary[status] = summary.get(status, 0) + 1
    return summary


def build_index(repo_root: Path) -> dict[str, Any]:
    cases = extract_cases(repo_root)
    test_points = build_test_point_entries(repo_root)
    case_refs: dict[str, list[dict[str, Any]]] = {}
    for entry in test_points:
        for case_name in entry.get("implemented_cases", []):
            case_refs.setdefault(case_name, []).append(
                {"file": entry["file"], "line": entry["line"], "heading": entry["heading"]}
            )
    compact_cases = [
        {
            "case_name": item.get("case_name"),
            "file": item.get("file"),
            "line": item.get("line"),
            "symbol_kind": item.get("symbol_kind"),
            "register_status": item.get("register_status"),
            "test_point_refs": case_refs.get(str(item.get("case_name")), []),
        }
        for item in cases
    ]
    return {
        "cases": compact_cases,
        "test_points": test_points,
        "summary": {
            "case_count": len(compact_cases),
            "test_point_entry_count": len(test_points),
            "implemented_case_ref_count": sum(len(item.get("implemented_cases", [])) for item in test_points),
            "register_status": register_summary(compact_cases),
        },
    }


def load_or_build(repo_root: Path, args: argparse.Namespace) -> tuple[dict[str, Any], dict[str, Any]]:
    fingerprint = source_fingerprint(repo_root)
    path = cache_path(repo_root, args.cache_dir)
    if not args.no_cache and path.is_file():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if payload.get("fingerprint") == fingerprint and isinstance(payload.get("index"), dict):
                return payload["index"], {
                    "enabled": True,
                    "hit": True,
                    "path": str(path),
                    "fingerprint_digest": fingerprint["digest"],
                    "build_seconds": 0.0,
                }
        except (json.JSONDecodeError, OSError, TypeError):
            pass

    started = time.monotonic()
    index = build_index(repo_root)
    cache = {
        "enabled": not args.no_cache,
        "hit": False,
        "path": str(path) if not args.no_cache else None,
        "fingerprint_digest": fingerprint["digest"],
        "build_seconds": round(time.monotonic() - started, 3),
    }
    if not args.no_cache:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps({"fingerprint": fingerprint, "index": index}, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        except OSError as exc:
            cache["write_error"] = str(exc)
    return index, cache


def query_hits(index: dict[str, Any], terms: list[str], limit: int) -> list[dict[str, Any]]:
    needles = [term.strip().lower() for term in terms if term.strip()]
    if not needles:
        return []
    hits: list[dict[str, Any]] = []
    for entry in index.get("test_points", []):
        haystack = f"{entry.get('heading', '')}\n{entry.get('excerpt', '')}".lower()
        matched = [term for term in needles if term in haystack]
        if matched:
            hits.append(
                {
                    "file": entry.get("file"),
                    "line": entry.get("line"),
                    "heading": entry.get("heading"),
                    "matched_terms": matched,
                    "implemented_cases": entry.get("implemented_cases", []),
                }
            )
        if len(hits) >= limit:
            break
    return hits


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    repo_root = resolve_path(args.repo_root)
    started = time.monotonic()
    index, cache = load_or_build(repo_root, args)
    report = {
        "repo_root": str(repo_root),
        "ok": repo_root.is_dir(),
        "cache": cache,
        "summary": index.get("summary", {}),
        "query_terms": list(args.query),
        "test_point_hits": query_hits(index, args.query, args.limit),
        "timing": {
            "total_seconds": round(time.monotonic() - started, 3),
            "by_step": {"build_or_load": round(time.monotonic() - started, 3)},
        },
    }
    return report


def render_text(report: dict[str, Any]) -> str:
    lines = ["PASS repo evidence index" if report.get("ok") else "FAIL repo evidence index"]
    lines.append(f"HYPTEST_HOME: {report.get('repo_root')}")
    cache = report.get("cache", {})
    lines.append(f"cache: {'hit' if cache.get('hit') else 'miss'} {cache.get('path') or ''}".rstrip())
    summary = report.get("summary", {})
    lines.append(f"cases: {summary.get('case_count', 0)}")
    lines.append(f"test_point_entries: {summary.get('test_point_entry_count', 0)}")
    lines.append(f"implemented_case_refs: {summary.get('implemented_case_ref_count', 0)}")
    if report.get("test_point_hits"):
        lines.append("test_point_hits:")
        for hit in report["test_point_hits"]:
            lines.append(f"  {hit['file']}:{hit['line']} {hit['heading']}")
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    report = build_report(args)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_text(report))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
