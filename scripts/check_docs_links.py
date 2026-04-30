#!/usr/bin/env python3
"""
Check local documentation references inside the hyptest-workflow skill.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


DOC_EXTENSIONS = {".md", ".yaml", ".yml"}
REFERENCE_RE = re.compile(
    r"`((?:references|scripts|assets|agents)/[^`<>\s]+|SKILL\.md|README\.md|\.gitignore)`"
)


def skill_root() -> Path:
    return Path(__file__).resolve().parent.parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check skill documentation local references.")
    parser.add_argument("--json", action="store_true", help="Emit JSON report.")
    return parser.parse_args()


def iter_doc_files(root: Path) -> list[Path]:
    paths: list[Path] = [root / "SKILL.md", root / "README.md"]
    paths.extend(path for path in (root / "agents").glob("*.yaml"))
    paths.extend(path for path in (root / "references").rglob("*.md"))
    return sorted(path for path in paths if path.is_file())


def should_skip(raw: str) -> bool:
    if "<" in raw or ">" in raw:
        return True
    if "*" in raw:
        return True
    if raw.startswith("src/") or raw.startswith("test_point/"):
        return True
    return False


def check_file(root: Path, path: Path) -> list[str]:
    issues: list[str] = []
    text = path.read_text(encoding="utf-8", errors="ignore")
    for match in REFERENCE_RE.finditer(text):
        raw = match.group(1).rstrip(".,;:")
        if should_skip(raw):
            continue
        target = (root / raw).resolve()
        if not target.exists():
            rel = path.relative_to(root)
            issues.append(f"{rel}: missing local reference `{raw}`")
    return issues


def main() -> int:
    args = parse_args()
    root = skill_root()
    issues: list[str] = []
    checked = []
    for path in iter_doc_files(root):
        checked.append(str(path.relative_to(root)))
        issues.extend(check_file(root, path))

    payload = {
        "ok": not issues,
        "checked_file_count": len(checked),
        "checked_files": checked,
        "issues": issues,
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(("PASS" if payload["ok"] else "FAIL") + " docs links")
        for issue in issues:
            print(f"  - {issue}")
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
