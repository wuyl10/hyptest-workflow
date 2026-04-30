#!/usr/bin/env python3
"""
Regression checks for check_case_lint.py.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parent


def temp_parent() -> Path:
    path = SKILL_ROOT / ".hyptest_skill_tmp"
    path.mkdir(parents=True, exist_ok=True)
    return path


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def run_lint(repo: Path, *extra: str) -> dict[str, object]:
    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_DIR / "check_case_lint.py"),
            "--repo-root",
            str(repo),
            "--strict-case-end",
            "--json",
            *extra,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode not in {0, 1}:
        raise RuntimeError(completed.stderr or completed.stdout)
    return json.loads(completed.stdout)


def git(repo: Path, *args: str) -> None:
    env = os.environ.copy()
    env.update(
        {
            "GIT_AUTHOR_NAME": "hyptest-eval",
            "GIT_AUTHOR_EMAIL": "hyptest-eval@example.com",
            "GIT_COMMITTER_NAME": "hyptest-eval",
            "GIT_COMMITTER_EMAIL": "hyptest-eval@example.com",
        }
    )
    completed = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr or completed.stdout)


def expect(condition: bool, failures: list[str], message: str) -> None:
    if not condition:
        failures.append(message)


def main() -> int:
    failures: list[str] = []
    with tempfile.TemporaryDirectory(prefix="hyptest_case_lint_eval_", dir=temp_parent()) as tmpdir:
        repo = Path(tmpdir)
        write(repo / "test_register.c", "TEST_REGISTER(ai_good_case)\nTEST_REGISTER(ai_bad_case)\n")
        write(
            repo / "ai_test_cases/good.c",
            "bool ai_good_case(void) {\n"
            "    TEST_START();\n"
            "    TEST_SETUP_EXCEPT();\n"
            "    TEST_ASSERT(\"good path\", excpt.triggered == false);\n"
            "    TEST_END(\"ai_good_case\");\n"
            "}\n",
        )
        write(
            repo / "ai_test_cases/bad.c",
            "TEST_REGISTER(ai_local_register)\n"
            "bool ai_bad_case(void) {\n"
            "    TEST_START();\n"
            "    TEST_ASSERT(\"bad path\", true);\n"
            "    TEST_END(\"ai_bad_case\");\n"
            "    TEST_END(\"ai_bad_case again\");\n"
            "}\n",
        )
        write(
            repo / "ai_test_cases/bad_name.c",
            "bool ai_bad_name_case(void) {\n"
            "    TEST_START();\n"
            "    TEST_ASSERT(\"bad name\", true);\n"
            "    TEST_END(\"ai_wrong_name\");\n"
            "}\n",
        )
        write(
            repo / "ai_test_cases/bad_start.c",
            "bool ai_bad_start_case(void) {\n"
            "    TEST_ASSERT(\"bad start\", true);\n"
            "    TEST_END(\"ai_bad_start_case\");\n"
            "}\n",
        )
        write(
            repo / "ai_test_cases/weak_assert.c",
            "bool ai_weak_assert_case(void) {\n"
            "    TEST_START();\n"
            "    TEST_ASSERT(\"fail\", true);\n"
            "    TEST_END(\"ai_weak_assert_case\");\n"
            "}\n",
        )
        write(
            repo / "ai_test_cases/no_assert.c",
            "bool ai_no_assert_case(void) {\n"
            "    TEST_START();\n"
            "    TEST_END(\"ai_no_assert_case\");\n"
            "}\n",
        )
        (repo / "manual_test_cases").mkdir()

        good = run_lint(repo, "--file", str(repo / "ai_test_cases/good.c"))
        expect(good["ok"] is True, failures, "good fixture should pass")

        all_cases = run_lint(repo)
        expect(all_cases["ok"] is False, failures, "bad fixture should fail")
        messages = [
            issue["message"]
            for result in all_cases["results"]
            for issue in result["issues"]
        ]
        expect(
            any("TEST_REGISTER belongs" in message for message in messages),
            failures,
            "bad fixture should catch source-local TEST_REGISTER",
        )
        expect(
            any("exactly one TEST_END" in message for message in messages),
            failures,
            "bad fixture should catch repeated TEST_END",
        )
        expect(
            any("TEST_END name" in message for message in messages),
            failures,
            "bad fixture should catch TEST_END name mismatch",
        )
        expect(
            any("exactly one TEST_START" in message for message in messages),
            failures,
            "bad fixture should catch missing TEST_START",
        )
        expect(
            any("too generic" in message for message in messages),
            failures,
            "bad fixture should warn on generic TEST_ASSERT messages",
        )
        expect(
            any("contains no TEST_ASSERT" in message for message in messages),
            failures,
            "bad fixture should warn on case-like functions without TEST_ASSERT",
        )
        warning_only = run_lint(repo, "--file", str(repo / "ai_test_cases/weak_assert.c"))
        expect(
            warning_only["ok"] is True and warning_only["warning_count"] >= 1,
            failures,
            "warning-only fixture should pass without --warnings-as-errors",
        )
        warning_strict = run_lint(
            repo,
            "--file",
            str(repo / "ai_test_cases/weak_assert.c"),
            "--warnings-as-errors",
        )
        expect(
            warning_strict["ok"] is False and warning_strict["effective_error_count"] >= 1,
            failures,
            "--warnings-as-errors should fail warning-only fixtures",
        )
        baseline_path = repo / "case_lint_baseline.json"
        baseline_write = run_lint(
            repo,
            "--file",
            str(repo / "ai_test_cases/weak_assert.c"),
            "--write-baseline",
            str(baseline_path),
        )
        expect(
            baseline_write["issue_count"] >= 1 and baseline_path.is_file(),
            failures,
            "--write-baseline should write current issues",
        )
        warning_with_baseline = run_lint(
            repo,
            "--file",
            str(repo / "ai_test_cases/weak_assert.c"),
            "--baseline",
            str(baseline_path),
            "--warnings-as-errors",
        )
        expect(
            warning_with_baseline["ok"] is True
            and warning_with_baseline["baseline_ignored_count"] >= 1
            and warning_with_baseline["active_issue_count"] == 0,
            failures,
            "baseline should suppress known warning-only issues even with --warnings-as-errors",
        )

        git(repo, "init", "-q")
        git(repo, "add", "test_register.c", "ai_test_cases/good.c")
        git(repo, "commit", "-q", "-m", "baseline")
        changed = run_lint(repo, "--changed-only")
        expect(
            changed["checked_file_count"] == 5,
            failures,
            "--changed-only should lint only changed/untracked case sources",
        )
        checked_paths = [result["path"] for result in changed["results"]]
        expect(
            checked_paths == [
                "ai_test_cases/bad.c",
                "ai_test_cases/bad_name.c",
                "ai_test_cases/bad_start.c",
                "ai_test_cases/no_assert.c",
                "ai_test_cases/weak_assert.c",
            ],
            failures,
            f"--changed-only checked unexpected paths: {checked_paths}",
        )

    if failures:
        print("FAIL check_case_lint eval")
        for failure in failures:
            print(f"  - {failure}")
        return 1

    print("PASS check_case_lint eval")
    return 0


if __name__ == "__main__":
    sys.exit(main())
