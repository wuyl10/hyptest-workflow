#!/usr/bin/env python3
"""Check hyptest repository migration assumptions after layout renames."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


LEGACY_CASE_DIR = "individual" + "_tests"
LEGACY_CASE_SINGULAR = "individual" + "_test"
LEGACY_CASE_HYPHEN = "individual" + "-tests"
LEGACY_CASE_WORDS = "individual" + " tests"
LEGACY_SPIKE_BIN_FIELD = "spike" + "_bin"
LEGACY_XIANGSHAN_PLATFORM = "--platform " + "xiangshan"
LEGACY_XIANGSHAN_PLAT = "--plat " + "xiangshan"

FORBIDDEN_TEXT = [
    (LEGACY_CASE_DIR, "removed legacy ELF/ASM directory"),
    (LEGACY_CASE_SINGULAR, "removed legacy ELF/ASM directory"),
    (LEGACY_CASE_HYPHEN, "removed legacy ELF/ASM directory"),
    (LEGACY_CASE_WORDS, "removed legacy ELF/ASM directory"),
    (LEGACY_SPIKE_BIN_FIELD, "old lowercase Spike binary field"),
    (LEGACY_XIANGSHAN_PLATFORM, "old xiangshan platform value"),
    (LEGACY_XIANGSHAN_PLAT, "old xiangshan plat value"),
]

SCAN_GLOBS = [
    "*.py",
    "*.md",
    "Makefile",
    ".gitignore",
    "test_point/*.md",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check hyptest repo for removed layout logic.")
    parser.add_argument("--repo-root", required=True, help="Path to hyptest repo root.")
    parser.add_argument("--json", action="store_true", help="Emit JSON report.")
    return parser.parse_args()


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def collect_files(repo_root: Path) -> list[Path]:
    files: list[Path] = []
    seen = set()
    for pattern in SCAN_GLOBS:
        for path in repo_root.glob(pattern):
            if path.is_file() and path not in seen:
                seen.add(path)
                files.append(path)
    return sorted(files)


def git_tracked_legacy(repo_root: Path) -> list[str]:
    completed = subprocess.run(
        ["git", "-C", str(repo_root), "ls-files", LEGACY_CASE_DIR],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return []
    return [line for line in completed.stdout.splitlines() if line.strip()]


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).expanduser().resolve()
    issues: list[str] = []
    warnings: list[str] = []

    if not repo_root.is_dir():
        print(f"repo-root not found: {repo_root}", file=sys.stderr)
        return 2

    required_case_dir_refs = {
        ".gitignore": "/case_elf_asm/",
        "compile_elf.py": 'Path("case_elf_asm")',
        "get_result.py": "case_elf_asm",
    }
    for rel, needle in required_case_dir_refs.items():
        path = repo_root / rel
        if not path.is_file():
            issues.append(f"missing required file `{rel}`")
            continue
        if needle not in read_text(path):
            issues.append(f"`{rel}` does not mention current case_elf_asm convention")

    legacy_dir = repo_root / LEGACY_CASE_DIR
    if legacy_dir.exists():
        issues.append(f"legacy directory exists: {LEGACY_CASE_DIR}/")

    for rel in git_tracked_legacy(repo_root):
        issues.append(f"legacy directory still tracked by git: {rel}")

    for path in collect_files(repo_root):
        rel = str(path.relative_to(repo_root))
        text = read_text(path)
        for needle, label in FORBIDDEN_TEXT:
            if needle in text:
                issues.append(f"{rel}: forbidden {label}: {needle}")

    # Plain English "individual" is allowed in test intent comments. Warn only
    # if it appears in the main scripts where it could confuse artifact naming.
    for rel in ["compile_elf.py", "get_result.py", "README.md"]:
        path = repo_root / rel
        if path.is_file() and "individual ELF" in read_text(path):
            warnings.append(f"{rel}: consider replacing ambiguous `individual ELF` wording")

    payload = {
        "ok": not issues,
        "repo_root": str(repo_root),
        "issues": issues,
        "warnings": warnings,
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(("PASS" if payload["ok"] else "FAIL") + " hyptest repo migration")
        for issue in issues:
            print(f"  - {issue}")
        for warning in warnings:
            print(f"  warning: {warning}")
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
