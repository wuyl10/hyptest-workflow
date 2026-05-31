#!/usr/bin/env python3
"""Check hyptest case-name uniqueness using the cached repo evidence index."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

from repo_evidence_index import load_or_build
from skill_config import resolve_path
from writeback_register import load_registration_status


CASE_SOURCE_SCOPE = "ai_test_cases/*.c, manual_test_cases/**/*.c"
REGISTER_SCOPE = "test_register.c TEST_REGISTER(...)"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Check exact hyptest case-name uniqueness before editing. The default "
            "path reuses repo_evidence_index.py cache instead of cold-scanning "
            "the repo with rg for each candidate name."
        )
    )
    parser.add_argument("--repo-root", required=True, help="Path to hyptest repo root.")
    parser.add_argument(
        "--case",
        action="append",
        required=True,
        help="Candidate case name; can be repeated.",
    )
    parser.add_argument(
        "--expect",
        choices=["absent", "unique", "at-most-one"],
        default="absent",
        help=(
            "Expected definition state. Use absent before writing a new case, "
            "unique after writing, and at-most-one for a neutral duplicate check."
        ),
    )
    parser.add_argument(
        "--cache-dir",
        help="Override repo_evidence_index.py cache directory.",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Do not read/write the repo evidence cache.",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON report.")
    return parser.parse_args()


def definitions_for(index: dict[str, Any], case_name: str) -> list[dict[str, Any]]:
    definitions: list[dict[str, Any]] = []
    for item in index.get("cases", []):
        if item.get("case_name") != case_name:
            continue
        definitions.append(
            {
                "file": item.get("file"),
                "line": item.get("line"),
                "symbol_kind": item.get("symbol_kind"),
                "register_status_from_case_index": item.get("register_status"),
            }
        )
    return definitions


def verdict_for(
    *,
    case_name: str,
    definitions: list[dict[str, Any]],
    register_status: str,
    expect: str,
) -> dict[str, Any]:
    definition_count = len(definitions)
    warnings: list[str] = []
    failures: list[str] = []

    if expect == "absent":
        if definition_count:
            failures.append("source_definition_already_exists")
        if register_status == "enabled":
            failures.append("enabled_register_already_exists")
        elif register_status == "commented":
            warnings.append("commented_register_mention_exists")
    elif expect == "unique":
        if definition_count != 1:
            failures.append("definition_count_not_one")
    elif expect == "at-most-one":
        if definition_count > 1:
            failures.append("duplicate_source_definitions")

    return {
        "case": case_name,
        "expect": expect,
        "ok": not failures,
        "definition_count": definition_count,
        "definitions": definitions,
        "definition_absent": definition_count == 0,
        "definition_unique": definition_count == 1,
        "definition_at_most_one": definition_count <= 1,
        "register_status": register_status,
        "warnings": warnings,
        "failures": failures,
    }


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    started = time.monotonic()
    repo_root = resolve_path(args.repo_root)
    index_args = argparse.Namespace(no_cache=args.no_cache, cache_dir=args.cache_dir)
    index, cache = load_or_build(repo_root, index_args)
    register_status = load_registration_status(repo_root)
    cases = [
        verdict_for(
            case_name=case_name,
            definitions=definitions_for(index, case_name),
            register_status=register_status.get(case_name, "unregistered"),
            expect=args.expect,
        )
        for case_name in args.case
    ]
    return {
        "ok": all(item["ok"] for item in cases),
        "repo_root": str(repo_root),
        "expect": args.expect,
        "scope": {
            "definitions": CASE_SOURCE_SCOPE,
            "registrations": REGISTER_SCOPE,
        },
        "strategy": "repo_evidence_index_cache",
        "cache": cache,
        "cases": cases,
        "timing": {
            "total_seconds": round(time.monotonic() - started, 3),
        },
    }


def render_text(report: dict[str, Any]) -> str:
    lines = ["PASS case uniqueness" if report.get("ok") else "FAIL case uniqueness"]
    lines.append(f"HYPTEST_HOME: {report.get('repo_root')}")
    lines.append(f"expect: {report.get('expect')}")
    scope = report.get("scope", {})
    lines.append(f"definition_scope: {scope.get('definitions')}")
    lines.append(f"register_scope: {scope.get('registrations')}")
    cache = report.get("cache", {})
    lines.append(
        f"cache: {'hit' if cache.get('hit') else 'miss'} {cache.get('path') or ''}".rstrip()
    )
    for item in report.get("cases", []):
        status = "PASS" if item.get("ok") else "FAIL"
        lines.append(
            f"- {status} `{item.get('case')}`: definitions={item.get('definition_count')} "
            f"register_status={item.get('register_status')}"
        )
        for definition in item.get("definitions", []):
            lines.append(
                f"  - definition: {definition.get('file')}:{definition.get('line')} "
                f"kind={definition.get('symbol_kind')}"
            )
        for warning in item.get("warnings", []):
            lines.append(f"  - warning: {warning}")
        for failure in item.get("failures", []):
            lines.append(f"  - failure: {failure}")
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    report = build_report(args)

    # Warn when cache miss: SKILL.md Non-Negotiables §3 要求 repo_evidence_index 预热后再跑；
    # cache miss 时实际发生的是 load_or_build 做了全仓冷扫（或 fallback 到 rg），
    # 违反了"走缓存索引快路径"的硬规则。打印 stderr 警告让调用者/agent 可见。
    cache = report.get("cache") or {}
    if not args.no_cache and not cache.get("hit"):
        print(
            "WARN check_case_uniqueness: cache miss — 建议先跑 "
            "`python3 $HYPTEST_WORKFLOW_SKILL_HOME/scripts/repo_evidence_index.py --repo-root $HYPTEST_HOME --json > /dev/null` "
            "预热，然后再跑本脚本；否则本轮属于全仓冷扫，NFS 上较慢且违反 "
            "SKILL.md Non-Negotiables §3 '走缓存索引快路径' 的硬规则。",
            file=sys.stderr,
        )

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_text(report))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
