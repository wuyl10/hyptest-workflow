#!/usr/bin/env python3
"""Check get_result.py source/log contract expected by workflow consumers."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


REQUIRED_SOURCE_TOKENS = [
    "pass",
    "fail",
    "timeout",
    "missing",
    "forbidden",
    "untested",
    "missing_required",
    "found_forbidden",
    "untested_occurrences",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check hyptest get_result.py summary/log contract.")
    parser.add_argument("--repo-root", required=True, help="Path to hyptest repo root.")
    parser.add_argument("--sample-log", help="Optional result log to validate.")
    parser.add_argument("--json", action="store_true", help="Emit JSON report.")
    return parser.parse_args()


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def check_source(repo_root: Path) -> list[str]:
    issues: list[str] = []
    path = repo_root / "get_result.py"
    if not path.is_file():
        return [f"missing get_result.py under {repo_root}"]
    text = read(path).lower()
    for token in REQUIRED_SOURCE_TOKENS:
        if token.lower() not in text:
            issues.append(f"get_result.py missing expected summary token `{token}`")
    if "总 log 和终端结尾会统计" not in read(path):
        issues.append("get_result.py should document final summary counters in the header")
    return issues


def check_log(path: Path) -> list[str]:
    issues: list[str] = []
    text = read(path)
    lowered = text.lower()
    for token in ["pass", "fail", "timeout", "missing", "forbidden", "untested"]:
        if token not in lowered:
            issues.append(f"sample log missing summary token `{token}`")
    if not re.search(r"\b(PASSED|FAILED|timeout|missing_required|found_forbidden)\b", text):
        issues.append("sample log does not contain recognizable case result markers")
    return issues


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).expanduser().resolve()
    issues = check_source(repo_root)
    if args.sample_log:
        log_path = Path(args.sample_log).expanduser().resolve()
        if not log_path.is_file():
            issues.append(f"sample log not found: {log_path}")
        else:
            issues.extend(check_log(log_path))

    payload = {
        "ok": not issues,
        "repo_root": str(repo_root),
        "sample_log": args.sample_log,
        "issues": issues,
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(("PASS" if payload["ok"] else "FAIL") + " get_result log contract")
        for issue in issues:
            print(f"  - {issue}")
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
