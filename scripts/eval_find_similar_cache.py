#!/usr/bin/env python3
"""
Run focused regression checks for find_similar_cases.py cache behavior.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
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


def make_repo(root: Path) -> None:
    write(root / "test_register.c", "TEST_REGISTER(ai_arch_cache_probe_case)\n")
    write(
        root / "ai_test_cases/cache_probe.c",
        "bool ai_arch_cache_probe_case() {\n"
        "    TEST_START();\n"
        "    TEST_ASSERT(\"cache probe\", true);\n"
        "    TEST_END(\"ai_arch_cache_probe_case\");\n"
        "}\n",
    )
    (root / "manual_test_cases").mkdir(parents=True, exist_ok=True)


def run_find(repo_root: Path, cache_dir: Path, *, no_cache: bool = False) -> dict[str, object]:
    command = [
        sys.executable,
        str(SCRIPT_DIR / "find_similar_cases.py"),
        "--repo-root",
        str(repo_root),
        "--cache-dir",
        str(cache_dir),
        "--query",
        "cache",
        "--query",
        "probe",
        "--limit",
        "1",
        "--json",
    ]
    if no_cache:
        command.append("--no-cache")
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr or completed.stdout)
    return json.loads(completed.stdout)


def expect(condition: bool, failures: list[str], message: str) -> None:
    if not condition:
        failures.append(message)


def main() -> int:
    failures: list[str] = []
    with tempfile.TemporaryDirectory(
        prefix="hyptest_similar_cache_eval_",
        dir=temp_parent(),
    ) as tmpdir:
        tmp = Path(tmpdir)
        repo = tmp / "repo"
        cache_dir = tmp / "cache"
        make_repo(repo)

        first = run_find(repo, cache_dir)
        second = run_find(repo, cache_dir)
        expect(first["cache"]["enabled"] is True, failures, "first run should have cache enabled")
        expect(first["cache"]["hit"] is False, failures, "first run should be cache miss")
        expect(second["cache"]["hit"] is True, failures, "second run should be cache hit")

        time.sleep(0.001)
        write(repo / "test_register.c", "TEST_REGISTER(ai_arch_cache_probe_case)\n// touch\n")
        third = run_find(repo, cache_dir)
        expect(third["cache"]["hit"] is False, failures, "source change should invalidate cache")

        no_cache = run_find(repo, cache_dir, no_cache=True)
        expect(no_cache["cache"]["enabled"] is False, failures, "--no-cache should disable cache")

    if failures:
        print("FAIL find_similar cache eval")
        for failure in failures:
            print(f"  - {failure}")
        return 1

    print("PASS find_similar cache eval")
    return 0


if __name__ == "__main__":
    sys.exit(main())
