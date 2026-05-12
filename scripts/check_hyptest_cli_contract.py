#!/usr/bin/env python3
"""Check the hyptest repo CLI contract expected by hyptest-workflow."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from skill_config import resolve_path


NONCURRENT_CASE_DIR = "individual" + "_tests"
NONCURRENT_XIANGSHAN_PLATFORM = "--platform " + "xiangshan"
NONCURRENT_XIANGSHAN_PLAT = "--plat " + "xiangshan"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check hyptest CLI/platform/artifact contract.")
    parser.add_argument("--repo-root", required=True, help="Path to hyptest repo root.")
    parser.add_argument("--json", action="store_true", help="Emit JSON report.")
    return parser.parse_args()


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def require_file(repo_root: Path, rel: str, issues: list[str]) -> Path | None:
    path = repo_root / rel
    if not path.is_file():
        issues.append(f"missing `{rel}`")
        return None
    return path


def has_regex(text: str, pattern: str) -> bool:
    return re.search(pattern, text, flags=re.S) is not None


def main() -> int:
    args = parse_args()
    repo_root = resolve_path(args.repo_root)
    issues: list[str] = []
    warnings: list[str] = []

    if not repo_root.is_dir():
        print(f"repo-root not found: {repo_root}", file=sys.stderr)
        return 2

    compile_path = require_file(repo_root, "compile_elf.py", issues)
    result_path = require_file(repo_root, "get_result.py", issues)
    register_path = require_file(repo_root, "test_register.c", issues)

    if compile_path:
        text = read(compile_path)
        checks = [
            ("OUTPUT_DIR must use case_elf_asm", 'OUTPUT_DIR = REPO_ROOT / "case_elf_asm"'),
            ("compile_elf.py should expose --plat", 'parser.add_argument("--plat"'),
            ("compile_elf.py should support linknan platform", '"linknan"'),
            ("compile_elf.py should support spike platform", '"spike"'),
            ("compile_elf.py should persist artifact_name_map.json", "ARTIFACT_MAP_FILE"),
            ("compile_elf.py should default compile temp files under .tmp/hyptest_compile", 'REPO_ROOT / ".tmp" / "hyptest_compile"'),
            ("compile_elf.py should allow overriding CROSS_COMPILE", "--cross-compile"),
            ("compile_elf.py should expose --include-commented", "--include-commented"),
            ("compile_elf.py should parse TEST_REGISTER lines with trailing comments", r"\s*(?://.*)?$"),
        ]
        for label, needle in checks:
            if needle not in text:
                issues.append(f"compile_elf.py: {label}")
        if NONCURRENT_CASE_DIR in text:
            issues.append(f"compile_elf.py: forbidden artifact directory `{NONCURRENT_CASE_DIR}`")

    if result_path:
        text = read(result_path)
        checks = [
            ("get_result.py should expose --platform", 'parser.add_argument(\n        "--platform"'),
            ("get_result.py should restrict platform names to spike/linknan", 'PLATFORMS = ("spike", "linknan")'),
            ("get_result.py should use case_elf_asm defaults", "case_elf_asm"),
            ("get_result.py should require SPIKE_BIN", "SPIKE_BIN"),
            ("get_result.py should require LINKNAN_HOME", "LINKNAN_HOME"),
            ("get_result.py should require DIFFTEST_REF_SO", "DIFFTEST_REF_SO"),
            ("get_result.py should use artifact_name_map.json", "ARTIFACT_MAP_FILE"),
            ("get_result.py should default result logs under .tmp/result_log", 'REPO_ROOT / ".tmp" / "result_log"'),
            ("get_result.py should parse TEST_REGISTER lines with trailing comments", r"\s*(?://.*)?$"),
        ]
        for label, needle in checks:
            if needle not in text:
                issues.append(f"get_result.py: {label}")
        if NONCURRENT_CASE_DIR in text:
            issues.append(f"get_result.py: forbidden artifact directory `{NONCURRENT_CASE_DIR}`")
        if NONCURRENT_XIANGSHAN_PLATFORM in text or NONCURRENT_XIANGSHAN_PLAT in text:
            issues.append("get_result.py: forbidden xiangshan platform CLI")
        if "/nfs/home/" in text:
            issues.append("get_result.py: reusable runner should not contain personal /nfs/home paths")
        if not has_regex(text, r'\$\{\{?SPIKE_BIN:\?set SPIKE_BIN'):
            warnings.append("get_result.py: SPIKE_BIN missing explicit shell error text")
        if not has_regex(text, r'\$\{\{?LINKNAN_HOME:\?set LINKNAN_HOME'):
            warnings.append("get_result.py: LINKNAN_HOME missing explicit shell error text")
        if not has_regex(text, r'\$\{\{?DIFFTEST_REF_SO:\?set DIFFTEST_REF_SO'):
            warnings.append("get_result.py: DIFFTEST_REF_SO missing explicit shell error text")

    if register_path:
        text = read(register_path)
        if "TEST_REGISTER(" not in text:
            issues.append("test_register.c: no TEST_REGISTER entries found")

    payload = {
        "ok": not issues,
        "repo_root": str(repo_root),
        "issues": issues,
        "warnings": warnings,
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(("PASS" if payload["ok"] else "FAIL") + " hyptest CLI contract")
        for issue in issues:
            print(f"  - {issue}")
        for warning in warnings:
            print(f"  warning: {warning}")
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
