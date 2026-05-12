#!/usr/bin/env python3
"""Summarize a hyptest repository without modifying it."""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path

from skill_config import CANONICAL_ENV_NAMES, hyptest_env_name, process_env_value, resolve_path


CASE_FUNC_RE = re.compile(r"^\s*(?:static\s+)?bool\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(", re.MULTILINE)
REGISTER_RE = re.compile(r"TEST_REGISTER\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*\)")
ENTRY_RE = re.compile(r"^###\s+P[0-9A-Za-z]", re.MULTILINE)
IMPLEMENTED_CASE_RE = re.compile(r"^\s*-\s*`([A-Za-z_][A-Za-z0-9_]*)`", re.MULTILINE)
# Reference files and subdirs under test_point/ that do not carry PnX entries.
NON_ENTRY_REFERENCE_STEMS = frozenset({"manual_reference", "critical_issues_log"})
NON_ENTRY_REFERENCE_DIRS = frozenset({"reference_tables"})


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Print a read-only hyptest repository snapshot.")
    parser.add_argument("--repo-root", required=True, help="Path to hyptest repo root.")
    parser.add_argument("--json", action="store_true", help="Emit JSON report.")
    return parser.parse_args()


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def count_case_sources(root: Path, rel: str) -> dict[str, object]:
    base = root / rel
    files = sorted(base.rglob("*.c")) if base.is_dir() else []
    case_names: set[str] = set()
    for path in files:
        case_names.update(CASE_FUNC_RE.findall(read(path)))
    return {
        "dir": rel,
        "exists": base.is_dir(),
        "file_count": len(files),
        "case_count": len(case_names),
    }


def registration_counts(root: Path) -> dict[str, object]:
    path = root / "test_register.c"
    if not path.is_file():
        return {"exists": False, "enabled_count": 0, "commented_count": 0, "total_mentions": 0}
    enabled = 0
    commented = 0
    for line in read(path).splitlines():
        matches = REGISTER_RE.findall(line)
        if not matches:
            continue
        stripped = line.strip()
        if stripped.startswith("//") or stripped.startswith("/*"):
            commented += len(matches)
        else:
            enabled += len(matches)
    return {
        "exists": True,
        "enabled_count": enabled,
        "commented_count": commented,
        "total_mentions": enabled + commented,
    }


def test_point_counts(root: Path) -> dict[str, object]:
    base = root / "test_point"
    files: list[Path] = []
    if base.is_dir():
        for p in sorted(base.rglob("*.md")):
            if p.stem.lower() in NON_ENTRY_REFERENCE_STEMS:
                continue
            try:
                top = p.relative_to(base).parts[0] if p.relative_to(base).parts else ""
            except ValueError:
                top = ""
            if top in NON_ENTRY_REFERENCE_DIRS:
                continue
            files.append(p)
    entry_count = 0
    implemented_case_count = 0
    for path in files:
        text = read(path)
        entry_count += len(ENTRY_RE.findall(text))
        implemented_case_count += len(IMPLEMENTED_CASE_RE.findall(text))
    return {
        "dir": "test_point",
        "exists": base.is_dir(),
        "file_count": len(files),
        "entry_count": entry_count,
        "implemented_case_line_count": implemented_case_count,
    }


def generated_artifacts(root: Path) -> dict[str, object]:
    case_elf = root / "case_elf_asm"
    artifact_map = case_elf / "artifact_name_map.json"
    elf_count = len(list(case_elf.rglob("*.ELF"))) if case_elf.is_dir() else 0
    asm_count = len(list(case_elf.rglob("*.S"))) if case_elf.is_dir() else 0
    return {
        "case_elf_asm_exists": case_elf.is_dir(),
        "case_elf_asm_elf_count": elf_count,
        "case_elf_asm_asm_count": asm_count,
        "artifact_name_map_exists": artifact_map.is_file(),
    }


def latest_result_logs(root: Path) -> list[str]:
    base = root / ".tmp" / "result_log"
    if not base.is_dir():
        return []
    logs = sorted(base.rglob("*.log"), key=lambda path: path.stat().st_mtime, reverse=True)
    return [str(path.relative_to(root)) for path in logs[:5]]


def env_summary() -> dict[str, object]:
    return {
        hyptest_env_name(name): bool(process_env_value(name))
        for name in CANONICAL_ENV_NAMES
    }


def build_snapshot(root: Path) -> dict[str, object]:
    return {
        "repo_root": str(root),
        "repo_exists": root.is_dir(),
        "anchors": {
            rel: (root / rel).exists()
            for rel in ["compile_elf.py", "get_result.py", "test_register.c"]
        },
        "case_sources": [
            count_case_sources(root, "ai_test_cases"),
            count_case_sources(root, "manual_test_cases"),
        ],
        "registration": registration_counts(root),
        "test_points": test_point_counts(root),
        "generated_artifacts": generated_artifacts(root),
        "latest_result_logs": latest_result_logs(root),
        "env_set": env_summary(),
    }


def main() -> int:
    args = parse_args()
    root = resolve_path(args.repo_root)
    payload = build_snapshot(root)
    ok = bool(payload["repo_exists"]) and all(payload["anchors"].values())
    payload["ok"] = ok

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(("PASS" if ok else "FAIL") + " hyptest repo snapshot")
        print(f"HYPTEST_HOME: {payload['repo_root']}")
        print("anchors:")
        for rel, exists in payload["anchors"].items():
            print(f"  {'ok' if exists else 'missing'}: {rel}")
        print("case sources:")
        for item in payload["case_sources"]:
            print(f"  {item['dir']}: files={item['file_count']} cases={item['case_count']}")
        reg = payload["registration"]
        print(
            "registration: "
            f"enabled={reg['enabled_count']} commented={reg['commented_count']} total={reg['total_mentions']}"
        )
        tp = payload["test_points"]
        print(
            "test_points: "
            f"files={tp['file_count']} entries={tp['entry_count']} implemented_lines={tp['implemented_case_line_count']}"
        )
        gen = payload["generated_artifacts"]
        print(
            "case_elf_asm: "
            f"exists={gen['case_elf_asm_exists']} elf={gen['case_elf_asm_elf_count']} asm={gen['case_elf_asm_asm_count']}"
        )
        if payload["latest_result_logs"]:
            print("latest logs:")
            for rel in payload["latest_result_logs"]:
                print(f"  {rel}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
