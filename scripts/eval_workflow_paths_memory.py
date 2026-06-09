#!/usr/bin/env python3
"""Smoke-test workflow_paths.py and workflow_memory.py."""

from __future__ import annotations

import json
import os
import re
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


def assert_memory_docs(failures: list[str]) -> None:
    reference_paths = [
        SKILL_ROOT / "SKILL.md",
        SKILL_ROOT / "references" / "workflow_state.md",
        SKILL_ROOT / "references" / "repo_layout.md",
    ]
    combined = "\n".join(path.read_text(encoding="utf-8", errors="ignore") for path in reference_paths)
    lowered = combined.lower()
    normalized = re.sub(r"\s+", " ", lowered.replace("`", ""))
    skill_text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8", errors="ignore")
    tabbed_skill_lines = [
        f"{line_no}: {line}"
        for line_no, line in enumerate(skill_text.splitlines(), start=1)
        if line.startswith("\t")
    ]
    expect(
        not tabbed_skill_lines,
        failures,
        "workflow SKILL should not use tab-indented prose lines: " + "; ".join(tabbed_skill_lines[:3]),
    )
    forbidden_patterns = [
        (
            r"workflow_memory\.py\s+(?:append|query|summarize)?[^。；;\n]*--topic",
            "workflow_memory.py docs should not use unsupported --topic",
        ),
        (r"query\s+了哪些\s+topic", "workflow SKILL should not describe memory query output as topic-based"),
        (r"topic\s+精确匹配", "workflow SKILL should not describe workflow memory matching as topic-based"),
        (
            r"(?:自动|一并|同时|顺手)[^。；;\n]{0,24}(?:删除|清理)[^。；;\n]{0,24}(?:memory|JSON\s*行|events\.jsonl)",
            "workflow SKILL should not imply automatic memory JSON deletion",
        ),
        (
            r"(?:删除|清理)[^。；;\n]{0,24}(?:memory|JSON\s*行|events\.jsonl)[^。；;\n]{0,24}(?:无需|不用|不需要)(?:用户确认|audit|人工确认)",
            "workflow SKILL should not allow memory JSON deletion without user/audit confirmation",
        ),
        (r"mark stale (?:records|entries) [`']?obsolete[`']?", "docs should not tell users to mark stale memory obsolete"),
        (r"mark stale (?:records|entries).*obsolete", "docs should not tell users to mark stale memory obsolete"),
    ]
    for pattern, message in forbidden_patterns:
        expect(re.search(pattern, combined, flags=re.IGNORECASE) is None, failures, message)
    expect(
        "there is no obsolete memory status" in normalized,
        failures,
        "repo layout should state obsolete memory status does not exist",
    )
    expect(
        "audited stale cleanup deletes jsonl lines" in lowered
        or "audit 确认" in combined
        or "audit confirms" in lowered,
        failures,
        "memory docs should describe audited stale cleanup by deleting JSONL lines",
    )
    expect(
        "--term" in combined and "check_manual_reference_topic.py --topic" in combined,
        failures,
        "workflow SKILL should distinguish workflow_memory --term from Manual_Reference --topic",
    )
    expect(
        "只有用户确认具体 entry" in combined or "用户明确确认删除哪些 entry" in combined,
        failures,
        "workflow SKILL should mention user-confirmed memory deletion boundary",
    )


def main() -> int:
    failures: list[str] = []
    assert_memory_docs(failures)
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
            boundary = str(summary.get("quality_boundary", ""))
            lowered_boundary = boundary.lower()
            expect(
                "no obsolete status" in lowered_boundary,
                failures,
                "summary should say obsolete status does not exist",
            )
            expect(
                "mark stale entries obsolete" not in lowered_boundary,
                failures,
                "summary should not tell users to mark stale entries obsolete",
            )
            expect(
                "deletes jsonl lines directly" in lowered_boundary
                or "deleted directly" in lowered_boundary,
                failures,
                "summary should say stale entries are deleted directly",
            )

    if failures:
        print("FAIL workflow paths/memory eval")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("PASS workflow paths/memory eval")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
