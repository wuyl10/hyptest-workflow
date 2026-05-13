#!/usr/bin/env python3
"""Smoke-test workflow_paths.py and workflow_memory.py."""

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
    path = SKILL_ROOT / ".hyptest_workflow_skill" / "tmp" / "eval"
    path.mkdir(parents=True, exist_ok=True)
    return path


def run(command: list[str], *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=str(SKILL_ROOT), env=env, capture_output=True, text=True, check=False)


def load_json(completed: subprocess.CompletedProcess[str], failures: list[str], label: str) -> dict[str, object]:
    if completed.returncode != 0:
        failures.append(f"{label} returned {completed.returncode}: {completed.stderr or completed.stdout}")
        return {}
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        failures.append(f"{label} did not emit JSON: {exc}")
        return {}
    return payload if isinstance(payload, dict) else {}


def expect(condition: bool, failures: list[str], message: str) -> None:
    if not condition:
        failures.append(message)


def main() -> int:
    failures: list[str] = []
    with tempfile.TemporaryDirectory(prefix="hyptest_paths_memory_", dir=temp_parent()) as tmpdir:
        repo = Path(tmpdir) / "repo"
        repo.mkdir()
        env = os.environ.copy()
        for name in (
            "HYPTEST_WORKFLOW_ROOT",
            "HYPTEST_CACHE_DIR",
            "HYPTEST_REPORT_DIR",
            "HYPTEST_MEMORY_DIR",
            "HYPTEST_WORKFLOW_TMPDIR",
        ):
            env.pop(name, None)

        paths = load_json(
            run(
                [
                    sys.executable,
                    str(SCRIPT_DIR / "workflow_paths.py"),
                    "--repo-root",
                    str(repo),
                    "--json",
                ],
                env=env,
            ),
            failures,
            "workflow_paths",
        )
        if paths:
            expect(
                paths.get("workflow_root") == str(repo / ".hyptest_workflow_skill"),
                failures,
                "workflow root should default to .hyptest_workflow_skill",
            )
            expect(
                paths.get("cache_dir") == str(repo / ".hyptest_workflow_skill/cache"),
                failures,
                "cache dir should default to .hyptest_workflow_skill/cache",
            )
            expect(
                paths.get("report_dir") == str(repo / ".hyptest_workflow_skill/reports"),
                failures,
                "report dir should default to .hyptest_workflow_skill/reports",
            )
            expect(
                paths.get("memory_dir") == str(repo / ".hyptest_workflow_skill/memory"),
                failures,
                "memory dir should default to .hyptest_workflow_skill/memory",
            )

        custom_memory = repo / "custom_memory"
        append = load_json(
            run(
                [
                    sys.executable,
                    str(SCRIPT_DIR / "workflow_memory.py"),
                    "--repo-root",
                    str(repo),
                    "--memory-dir",
                    str(custom_memory),
                    "--json",
                    "append",
                    "--case",
                    "ai_memory_smoke",
                    "--module",
                    "memblock",
                    "--platform",
                    "spike",
                    "--phase",
                    "compile",
                    "--status",
                    "confirmed",
                    "--symptom",
                    "missing TEST_SETUP_EXCEPT caused compile warning",
                    "--reason-code",
                    "case_harness_bug",
                    "--tag",
                    "setup_except",
                    "--fix",
                    "added setup before checking exception state",
                ],
                env=env,
            ),
            failures,
            "workflow_memory_append",
        )
        if append:
            expect((custom_memory / "events.jsonl").is_file(), failures, "append should create events.jsonl")
            expect(append.get("record", {}).get("status") == "confirmed", failures, "append should preserve status")

        query = load_json(
            run(
                [
                    sys.executable,
                    str(SCRIPT_DIR / "workflow_memory.py"),
                    "--repo-root",
                    str(repo),
                    "--memory-dir",
                    str(custom_memory),
                    "--json",
                    "query",
                    "--term",
                    "setup_except",
                ],
                env=env,
            ),
            failures,
            "workflow_memory_query",
        )
        if query:
            expect(query.get("count") == 1, failures, "query should find the appended memory record")
            expect(query.get("records", [{}])[0].get("case") == "ai_memory_smoke", failures, "query should return appended case")

        summary = load_json(
            run(
                [
                    sys.executable,
                    str(SCRIPT_DIR / "workflow_memory.py"),
                    "--repo-root",
                    str(repo),
                    "--memory-dir",
                    str(custom_memory),
                    "--json",
                    "summarize",
                ],
                env=env,
            ),
            failures,
            "workflow_memory_summarize",
        )
        if summary:
            expect(summary.get("count") == 1, failures, "summary should count appended memory record")
            expect(summary.get("phase_counts", [{}])[0].get("value") == "compile", failures, "summary should count compile phase")

    if failures:
        print("FAIL workflow paths/memory eval")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("PASS workflow paths/memory eval")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
