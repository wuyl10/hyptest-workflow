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

from skill_config import default_spec_profile


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


def temp_parent() -> Path:
    path = Path(__file__).resolve().parent.parent / ".hyptest_workflow_skill" / "tmp" / "eval"
    path.mkdir(parents=True, exist_ok=True)
    return path


def run_eval_case(script_path: Path, case: Dict[str, object]) -> List[str]:
    failures: List[str] = []

    with tempfile.TemporaryDirectory(
        prefix="hyptest_writeback_eval_",
        dir=temp_parent(),
    ) as tmpdir:
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


def run_all_test_points_eval(script_path: Path) -> List[str]:
    failures: List[str] = []
    with tempfile.TemporaryDirectory(
        prefix="hyptest_writeback_all_eval_",
        dir=temp_parent(),
    ) as tmpdir:
        repo_root = Path(tmpdir)
        test_point_dir = repo_root / "test_point"
        test_point_dir.mkdir(parents=True, exist_ok=True)
        write_text(
            test_point_dir / "points.md",
            "### P1A. sample\n\n"
            "测试点：\n\n"
            "- sample\n\n"
            "构建场景：\n\n"
            "- sample\n\n"
            "已实现 case：\n\n"
            "- `ai_sample_case`\n",
        )
        write_text(repo_root / "test_register.c", "TEST_REGISTER(ai_sample_case)\n")
        completed = subprocess.run(
            [
                sys.executable,
                str(script_path),
                "--repo-root",
                str(repo_root),
                "--all-test-points",
                "--check-register",
                "--json",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            return [completed.stderr.strip() or completed.stdout.strip() or "all-test-points failed"]
        payload = json.loads(completed.stdout)
        if payload.get("checked_file_count") != 1:
            failures.append("expected all-test-points checked_file_count=1")
    return failures


def run_profile_warning_eval(script_path: Path) -> List[str]:
    failures: List[str] = []
    profile = default_spec_profile()
    with tempfile.TemporaryDirectory(
        prefix="hyptest_writeback_profile_eval_",
        dir=temp_parent(),
    ) as tmpdir:
        repo_root = Path(tmpdir)
        markdown_path = repo_root / "test_point.md"
        write_text(
            markdown_path,
            "### P1A. pbmt default warning\n\n"
            "测试点：\n\n"
            "- PBMT=IO Device access should be non-gate unless model support is explicit\n\n"
            "构建场景：\n\n"
            "- MMIO Device path\n\n"
            "已实现 case：\n\n"
            "- `ai_profile_warning_case`（default，已启用）\n",
        )
        write_text(repo_root / "test_register.c", "TEST_REGISTER(ai_profile_warning_case)\n")
        completed = subprocess.run(
            [
                sys.executable,
                str(script_path),
                "--repo-root",
                str(repo_root),
                "--file",
                str(markdown_path),
                "--check-register",
                "--spec-profile",
                profile,
                "--json",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            return [completed.stderr.strip() or completed.stdout.strip() or "profile warning eval failed"]
        payload = json.loads(completed.stdout)
        if payload.get("warning_count", 0) < 1:
            failures.append("expected profile-aware warning_count >= 1")
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

    total = len(eval_cases) + 2
    all_failures = run_all_test_points_eval(script_path)
    if all_failures:
        print("FAIL all-test-points")
        for failure in all_failures:
            print(f"  - {failure}")
    else:
        passed += 1
        print("PASS all-test-points")

    profile_failures = run_profile_warning_eval(script_path)
    if profile_failures:
        print("FAIL profile-warning")
        for failure in profile_failures:
            print(f"  - {failure}")
    else:
        passed += 1
        print("PASS profile-warning")

    print(f"summary: {passed}/{total} passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
