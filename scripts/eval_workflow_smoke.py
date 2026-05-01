#!/usr/bin/env python3
"""
Run a minimal tool-chain smoke test for the hyptest-workflow skill.
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

from skill_config import default_spec_profile


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parent


def temp_parent() -> Path:
    path = SKILL_ROOT / ".hyptest_skill_tmp"
    path.mkdir(parents=True, exist_ok=True)
    return path


def write(path: Path, text: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def make_executable(path: Path) -> None:
    write(path, "#!/bin/sh\nexit 0\n")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def run(command: list[str], *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    merged_env = os.environ.copy()
    for name in (
        "SPIKE_BIN", "LINKNAN_HOME", "NANHU_HOME", "DIFFTEST_REF_SO",
        "CROSS_COMPILE", "TMPDIR",
    ):
        merged_env.pop(name, None)
    if env:
        merged_env.update(env)
    return subprocess.run(command, capture_output=True, text=True, check=False, env=merged_env)


def main() -> int:
    failures: list[str] = []
    profile = default_spec_profile()
    with tempfile.TemporaryDirectory(prefix="hyptest_workflow_smoke_", dir=temp_parent()) as tmpdir:
        tmp = Path(tmpdir)
        repo = tmp / "repo"
        toolchain = tmp / "toolchain"
        toolchain.mkdir()
        make_executable(toolchain / "riscv64-unknown-elf-gcc")
        spike = tmp / "spike"
        make_executable(spike)

        write(repo / "compile_elf.py", "")
        write(repo / "get_result.py", "")
        write(repo / "test_register.c", "TEST_REGISTER(ai_arch_smoke_case)\n")
        (repo / "manual_test_cases").mkdir(parents=True)
        write(
            repo / "ai_test_cases/smoke.c",
            "bool ai_arch_smoke_case() {\n"
            "    TEST_START();\n"
            "    TEST_SETUP_EXCEPT();\n"
            "    TEST_ASSERT(\"smoke\", true);\n"
            "    TEST_END(\"ai_arch_smoke_case\");\n"
            "}\n",
        )
        write(
            repo / "test_point/smoke.md",
            "### P1A. smoke\n\n"
            "测试点：\n\n"
            "- smoke path\n\n"
            "构建场景：\n\n"
            "- smoke assertion\n\n"
            "已实现 case：\n\n"
            "- `ai_arch_smoke_case`（default，已启用）\n",
        )

        env = {
            "PATH": f"{toolchain}:{os.environ.get('PATH', '')}",
            "HYPTEST_CROSS_COMPILE": "riscv64-unknown-elf-",
            "HYPTEST_SPIKE_BIN": str(spike),
        }

        steps = [
            [
                sys.executable,
                str(SCRIPT_DIR / "check_env.py"),
                "--repo-root",
                str(repo),
                "--platform",
                "spike",
                "--json",
            ],
            [
                sys.executable,
                str(SCRIPT_DIR / "find_similar_cases.py"),
                "--repo-root",
                str(repo),
                "--query",
                "smoke",
                "--limit",
                "1",
                "--json",
            ],
            [
                sys.executable,
                str(SCRIPT_DIR / "check_writeback_format.py"),
                "--repo-root",
                str(repo),
                "--all-test-points",
                "--check-register",
                "--json",
            ],
            [
                sys.executable,
                str(SCRIPT_DIR / "check_spec_profile.py"),
                "--spec-profile",
                profile,
                "--strict",
                "--json",
            ],
        ]
        for command in steps:
            completed = run(command, env=env)
            if completed.returncode != 0:
                failures.append(
                    "command failed: "
                    + " ".join(command)
                    + "\n"
                    + (completed.stderr.strip() or completed.stdout.strip())
                )
                continue
            if command[1].endswith("find_similar_cases.py"):
                payload = json.loads(completed.stdout)
                if payload.get("result_count") != 1:
                    failures.append("find_similar_cases did not return the smoke case")

    if failures:
        print("FAIL workflow smoke")
        for failure in failures:
            print(f"  - {failure}")
        return 1

    print("PASS workflow smoke")
    return 0


if __name__ == "__main__":
    sys.exit(main())
