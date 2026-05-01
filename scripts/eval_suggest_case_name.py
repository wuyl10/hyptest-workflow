#!/usr/bin/env python3
"""Smoke-test suggest_case_name.py conflict checks."""

from __future__ import annotations

import json
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


def main() -> int:
    failures: list[str] = []
    with tempfile.TemporaryDirectory(prefix="hyptest_name_", dir=temp_parent()) as tmpdir:
        tmp = Path(tmpdir)
        repo = tmp / "repo"
        existing = "ai_micro_memblock_mprv_store_fault"
        write(repo / "compile_elf.py", "")
        write(repo / "get_result.py", "")
        write(repo / "test_register.c", f"TEST_REGISTER({existing})\n")
        write(
            repo / "ai_test_cases/name.c",
            f"bool {existing}() {{\n"
            "    TEST_START();\n"
            "    TEST_ASSERT(\"name\", true);\n"
            f"    TEST_END(\"{existing}\");\n"
            "}\n",
        )
        (repo / "manual_test_cases").mkdir(parents=True)
        write(
            repo / "test_point/name.md",
            "### P1A. memblock mprv store fault\n\n"
            "测试点：\n\n- memblock mprv store fault\n\n"
            "构建场景：\n\n- mpp u pte u page fault\n\n"
            "已实现 case：\n\n"
            f"- `{existing}`（default，已启用）\n",
        )
        preflight = {
            "target_test_point_excerpt": "memblock mprv mpp u pte u store page fault sfence",
            "commands": {
                "similar_cases": {
                    "payload": {
                        "focus_terms": ["memblock", "mprv", "mpp", "pte", "store", "fault", "sfence"],
                        "query_terms": ["memblock mprv"],
                    }
                }
            },
        }
        preflight_path = tmp / "preflight.json"
        write(preflight_path, json.dumps(preflight))
        completed = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_DIR / "suggest_case_name.py"),
                "--repo-root",
                str(repo),
                "--preflight-json",
                str(preflight_path),
                "--prefix",
                "ai_micro",
                "--limit",
                "4",
                "--json",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            failures.append(f"suggest_case_name returned {completed.returncode}: {completed.stderr or completed.stdout}")
            payload = {}
        else:
            try:
                payload = json.loads(completed.stdout)
            except json.JSONDecodeError as exc:
                failures.append(f"suggest_case_name did not emit JSON: {exc}")
                payload = {}
        if payload:
            suggestions = payload.get("suggestions", [])
            if not suggestions:
                failures.append("suggest_case_name should emit suggestions")
            if not any(item.get("usable") for item in suggestions):
                failures.append("suggest_case_name should include at least one usable name")
            if not all(str(item.get("name", "")).startswith("ai_micro_") for item in suggestions):
                failures.append("suggest_case_name should honor prefix")
            if not any("memblock" in str(item.get("name", "")) for item in suggestions):
                failures.append("suggest_case_name should use scenario terms")
            if payload.get("existing_case_count") != 1:
                failures.append("suggest_case_name should see existing case index")

    if failures:
        print("FAIL suggest case name eval")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("PASS suggest case name eval")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
