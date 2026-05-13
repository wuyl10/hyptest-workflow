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


def run_reason_code_eval(script_path: Path) -> List[str]:
    """Validate --check-reason-code and --check-failure-classified flags."""
    failures: List[str] = []
    with tempfile.TemporaryDirectory(
        prefix="hyptest_writeback_reason_eval_",
        dir=temp_parent(),
    ) as tmpdir:
        repo_root = Path(tmpdir)
        test_point_dir = repo_root / "test_point"
        test_point_dir.mkdir(parents=True, exist_ok=True)
        write_text(repo_root / "test_register.c", "// TEST_REGISTER(ai_manual_case);\n")

        # Case A: non-default status WITHOUT reason_code → should FAIL on --check-reason-code.
        md_no_rc = (
            "### P1A. sample manual\n\n"
            "测试点：\n\n- sample\n\n"
            "构建场景：\n\n- sample\n\n"
            "已实现 case：\n\n"
            "- `ai_manual_case`（已注释，manual）\n"
        )
        no_rc_file = test_point_dir / "no_rc.md"
        write_text(no_rc_file, md_no_rc)
        completed = subprocess.run(
            [
                sys.executable, str(script_path),
                "--repo-root", str(repo_root),
                "--file", str(no_rc_file),
                "--check-register", "--check-reason-code",
                "--json",
            ],
            capture_output=True, text=True, check=False,
        )
        if completed.returncode == 0:
            failures.append("non-default without reason_code should fail --check-reason-code")
        elif "reason_code" not in completed.stdout:
            failures.append("--check-reason-code error message should mention reason_code")

        # Case B: non-default status WITH valid D-MANUAL-NONGATE reason_code → should PASS.
        md_valid_rc = md_no_rc + "\nreason_code: D-MANUAL-NONGATE\n"
        valid_file = test_point_dir / "valid_rc.md"
        write_text(valid_file, md_valid_rc)
        completed = subprocess.run(
            [
                sys.executable, str(script_path),
                "--repo-root", str(repo_root),
                "--file", str(valid_file),
                "--check-register", "--check-reason-code",
                "--json",
            ],
            capture_output=True, text=True, check=False,
        )
        if completed.returncode != 0:
            failures.append(
                "non-default with D-MANUAL-NONGATE should pass --check-reason-code: "
                + (completed.stdout or completed.stderr)
            )

        # Case C: invalid (fabricated) reason_code → should FAIL.
        md_bad_rc = md_no_rc + "\nreason_code: D-MANUAL-INVENTED-BY-AGENT\n"
        bad_file = test_point_dir / "bad_rc.md"
        write_text(bad_file, md_bad_rc)
        completed = subprocess.run(
            [
                sys.executable, str(script_path),
                "--repo-root", str(repo_root),
                "--file", str(bad_file),
                "--check-register", "--check-reason-code",
                "--json",
            ],
            capture_output=True, text=True, check=False,
        )
        if completed.returncode == 0:
            failures.append("fabricated reason_code should fail --check-reason-code")

        # Case D: OTHER-PROPOSE escape hatch → should PASS but emit a warning.
        md_other_propose = md_no_rc + "\nreason_code: OTHER-PROPOSE: chain BP not in catalog\n"
        other_file = test_point_dir / "other_rc.md"
        write_text(other_file, md_other_propose)
        completed = subprocess.run(
            [
                sys.executable, str(script_path),
                "--repo-root", str(repo_root),
                "--file", str(other_file),
                "--check-register", "--check-reason-code",
                "--json",
            ],
            capture_output=True, text=True, check=False,
        )
        if completed.returncode != 0:
            failures.append(
                "OTHER-PROPOSE: should pass but emit warning; got failure: "
                + (completed.stdout or completed.stderr)
            )
        else:
            payload = json.loads(completed.stdout)
            warnings = payload.get("results", [{}])[0].get("warnings", [])
            if not any(w.get("warning_code") == "reason_code_other_propose" for w in warnings):
                failures.append("OTHER-PROPOSE: should emit reason_code_other_propose warning")

        # Case E: --check-failure-classified on non-default with D-MANUAL-NONGATE → should PASS
        # (D-MANUAL is valid classifier evidence).
        completed = subprocess.run(
            [
                sys.executable, str(script_path),
                "--repo-root", str(repo_root),
                "--file", str(valid_file),
                "--check-register", "--check-reason-code", "--check-failure-classified",
                "--json",
            ],
            capture_output=True, text=True, check=False,
        )
        if completed.returncode != 0:
            failures.append(
                "D-MANUAL-NONGATE should satisfy --check-failure-classified: "
                + (completed.stdout or completed.stderr)
            )

        # Case F: D-MANUAL-NANHU-NOT-IMPL → legal code but emits a dedicated warning
        # (Non-Negotiable §3 第 4 条: Nanhu 未实现的 corner 不应直接编 case).
        md_nanhu_not_impl = md_no_rc + "\nreason_code: D-MANUAL-NANHU-NOT-IMPL\n"
        nanhu_file = test_point_dir / "nanhu_not_impl.md"
        write_text(nanhu_file, md_nanhu_not_impl)
        completed = subprocess.run(
            [
                sys.executable, str(script_path),
                "--repo-root", str(repo_root),
                "--file", str(nanhu_file),
                "--check-register", "--check-reason-code",
                "--json",
            ],
            capture_output=True, text=True, check=False,
        )
        if completed.returncode != 0:
            failures.append(
                "D-MANUAL-NANHU-NOT-IMPL should be a legal code (pass), got failure: "
                + (completed.stdout or completed.stderr)
            )
        else:
            payload = json.loads(completed.stdout)
            warnings = payload.get("results", [{}])[0].get("warnings", [])
            if not any(w.get("warning_code") == "reason_code_nanhu_not_impl" for w in warnings):
                failures.append(
                    "D-MANUAL-NANHU-NOT-IMPL should emit reason_code_nanhu_not_impl warning"
                )

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

    total = len(eval_cases) + 3
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

    reason_failures = run_reason_code_eval(script_path)
    if reason_failures:
        print("FAIL reason-code-enforcement")
        for failure in reason_failures:
            print(f"  - {failure}")
    else:
        passed += 1
        print("PASS reason-code-enforcement")

    print(f"summary: {passed}/{total} passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
