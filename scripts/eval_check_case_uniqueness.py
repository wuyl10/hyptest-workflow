#!/usr/bin/env python3
"""Smoke-test check_case_uniqueness.py exact-name checks."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parent


def temp_parent() -> Path:
    path = SKILL_ROOT / ".hyptest_workflow_skill" / "tmp" / "eval"
    path.mkdir(parents=True, exist_ok=True)
    return path


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True, check=False)


def load_payload(completed: subprocess.CompletedProcess[str], failures: list[str], label: str) -> dict[str, object]:
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        failures.append(
            f"{label} did not emit JSON rc={completed.returncode}: {exc}; "
            f"stdout={completed.stdout!r} stderr={completed.stderr!r}"
        )
        return {}


def main() -> int:
    failures: list[str] = []
    with tempfile.TemporaryDirectory(prefix="hyptest_case_unique_", dir=temp_parent()) as tmpdir:
        repo = Path(tmpdir) / "repo"
        existing = "ai_arch_unique_smoke_existing"
        commented = "ai_arch_unique_smoke_commented"
        absent = "ai_arch_unique_smoke_absent"
        write(
            repo / "test_register.c",
            f"TEST_REGISTER({existing})\n"
            f"// TEST_REGISTER({commented})\n",
        )
        write(
            repo / "ai_test_cases/unique_smoke.c",
            f"bool {existing}() {{\n"
            "    TEST_START();\n"
            "    TEST_ASSERT(\"existing\", true);\n"
            f"    TEST_END(\"{existing}\");\n"
            "}\n",
        )
        (repo / "manual_test_cases").mkdir(parents=True)
        write(repo / "test_point/unique_smoke.md", "### P1A. unique smoke\n\n已实现 case：\n\n")

        base = [
            sys.executable,
            str(SCRIPT_DIR / "check_case_uniqueness.py"),
            "--repo-root",
            str(repo),
            "--json",
        ]

        absent_payload = load_payload(
            run([*base, "--case", absent, "--expect", "absent"]),
            failures,
            "absent",
        )
        if absent_payload:
            if not absent_payload.get("ok"):
                failures.append("absent candidate should pass --expect absent")
            if absent_payload.get("cache", {}).get("hit"):
                failures.append("first uniqueness run should miss cache")

        existing_absent = run([*base, "--case", existing, "--expect", "absent"])
        existing_absent_payload = load_payload(existing_absent, failures, "existing_absent")
        if existing_absent.returncode == 0 or existing_absent_payload.get("ok"):
            failures.append("existing case should fail --expect absent")

        existing_unique_payload = load_payload(
            run([*base, "--case", existing, "--expect", "unique"]),
            failures,
            "existing_unique",
        )
        if existing_unique_payload:
            if not existing_unique_payload.get("ok"):
                failures.append("existing case should pass --expect unique")
            if not existing_unique_payload.get("cache", {}).get("hit"):
                failures.append("later uniqueness run should hit repo evidence cache")

        commented_payload = load_payload(
            run([*base, "--case", commented, "--expect", "absent"]),
            failures,
            "commented",
        )
        if commented_payload:
            cases = commented_payload.get("cases", [])
            warnings = cases[0].get("warnings", []) if cases else []
            if not commented_payload.get("ok"):
                failures.append("commented-only register mention should not fail absent source check")
            if "commented_register_mention_exists" not in warnings:
                failures.append("commented-only register mention should be reported as a warning")

    if failures:
        print("FAIL check case uniqueness eval")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("PASS check case uniqueness eval")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
