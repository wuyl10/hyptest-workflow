#!/usr/bin/env python3
"""
Run a focused regression suite for check_writeback_format.py.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, List


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate check_writeback_format.py against fixed fixtures."
    )
    parser.add_argument(
        "--fixture",
        default=str(
            Path(__file__).resolve().parent.parent
            / "assets/evals/check_writeback_format_eval.json"
        ),
        help="Path to the evaluation fixture JSON",
    )
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Stop on the first failing eval case",
    )
    return parser.parse_args()


def read_fixture(path: Path) -> List[Dict[str, object]]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def normalize_fixture_text(raw: str) -> str:
    return raw.replace("\\n", "\n")


def run_eval_case(script_path: Path, case: Dict[str, object]) -> List[str]:
    failures: List[str] = []

    with tempfile.TemporaryDirectory(prefix="hyptest_writeback_eval_") as tmpdir:
        repo_root = Path(tmpdir)
        markdown_path = repo_root / "test_point.md"
        write_text(markdown_path, normalize_fixture_text(str(case["markdown_text"])))

        if "register_text" in case:
            write_text(
                repo_root / "test_register.c",
                normalize_fixture_text(str(case["register_text"])),
            )

        command = [
            sys.executable,
            str(script_path),
            "--file",
            str(markdown_path),
            "--json",
        ]
        if case.get("check_register"):
            command.extend(["--repo-root", str(repo_root), "--check-register"])

        completed = subprocess.run(command, capture_output=True, text=True, check=False)
        if completed.returncode not in {0, 1}:
            return [
                f"command failed with code {completed.returncode}",
                completed.stderr.strip() or completed.stdout.strip() or "no output",
            ]

        payload = json.loads(completed.stdout)
        if payload.get("checked_file_count") != 1:
            failures.append(
                f"expected checked_file_count 1, got {payload.get('checked_file_count')}"
            )
            return failures

        result = payload["results"][0]
        expected_ok = bool(case["expected_ok"])
        if bool(result.get("ok")) != expected_ok:
            failures.append(f"expected ok={expected_ok}, got {result.get('ok')}")

        issues = [str(item) for item in result.get("issues", [])]

        expected_issue_count = case.get("expected_issue_count")
        if expected_issue_count is not None and len(issues) != int(expected_issue_count):
            failures.append(
                f"expected issue_count {expected_issue_count}, got {len(issues)}"
            )

        for needle in case.get("expected_issue_substrings", []):
            if not any(str(needle) in issue for issue in issues):
                failures.append(f"missing expected issue substring: {needle}")

        for needle in case.get("unexpected_issue_substrings", []):
            if any(str(needle) in issue for issue in issues):
                failures.append(f"unexpected issue substring present: {needle}")

    return failures


def main() -> int:
    args = parse_args()
    fixture_path = Path(args.fixture).expanduser().resolve()
    script_path = Path(__file__).resolve().parent / "check_writeback_format.py"
    eval_cases = read_fixture(fixture_path)

    passed = 0
    for case in eval_cases:
        failures = run_eval_case(script_path, case)
        label = str(case.get("id", "unnamed"))
        description = str(case.get("description", "")).strip()
        if failures:
            print(f"FAIL {label}")
            if description:
                print(f"  desc: {description}")
            for failure in failures:
                print(f"  - {failure}")
            if args.fail_fast:
                return 1
            continue

        passed += 1
        print(f"PASS {label}")
        if description:
            print(f"  desc: {description}")

    total = len(eval_cases)
    print(f"summary: {passed}/{total} passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
