#!/usr/bin/env python3
"""Smoke-test repo_evidence_index.py cache and coverage summary."""

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
    if completed.returncode != 0:
        failures.append(f"{label} returned {completed.returncode}: {completed.stderr or completed.stdout}")
        return {}
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        failures.append(f"{label} did not emit JSON: {exc}")
        return {}


def main() -> int:
    failures: list[str] = []
    with tempfile.TemporaryDirectory(prefix="hyptest_repo_index_", dir=temp_parent()) as tmpdir:
        repo = Path(tmpdir) / "repo"
        case = "ai_arch_repo_index_smoke_case"
        write(repo / "compile_elf.py", "")
        write(repo / "get_result.py", "")
        write(repo / "test_register.c", f"TEST_REGISTER({case})\n")
        write(
            repo / "ai_test_cases/repo_index.c",
            f"bool {case}() {{\n"
            "    TEST_START();\n"
            "    TEST_ASSERT(\"repo index\", true);\n"
            f"    TEST_END(\"{case}\");\n"
            "}\n",
        )
        (repo / "manual_test_cases").mkdir(parents=True)
        write(
            repo / "test_point/repo_index.md",
            "### P1A. repo index smoke\n\n"
            "测试点：\n\n- repo index unique term\n\n"
            "已实现 case：\n\n"
            f"- `{case}`（default，已启用）\n",
        )
        command = [
            sys.executable,
            str(SCRIPT_DIR / "repo_evidence_index.py"),
            "--repo-root",
            str(repo),
            "--query",
            "unique term",
            "--json",
        ]
        first = load_payload(run(command), failures, "repo_evidence_index_first")
        if first:
            if first.get("cache", {}).get("hit"):
                failures.append("first repo_evidence_index run should miss cache")
            summary = first.get("summary", {})
            if summary.get("case_count") != 1:
                failures.append("repo_evidence_index should count one case")
            if summary.get("test_point_entry_count") != 1:
                failures.append("repo_evidence_index should count one test_point entry")
            if not first.get("test_point_hits"):
                failures.append("repo_evidence_index should return query test_point hits")
        second = load_payload(run(command), failures, "repo_evidence_index_second")
        if second and not second.get("cache", {}).get("hit"):
            failures.append("second repo_evidence_index run should hit cache")

    if failures:
        print("FAIL repo evidence index eval")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("PASS repo evidence index eval")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
