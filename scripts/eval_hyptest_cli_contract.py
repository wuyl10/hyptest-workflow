#!/usr/bin/env python3
"""Regression checks for check_hyptest_cli_contract.py."""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parent
NONCURRENT_CASE_DIR = "individual" + "_tests"
NONCURRENT_XIANGSHAN_PLATFORM = "--platform " + "xiangshan"


def temp_parent() -> Path:
    path = SKILL_ROOT / ".hyptest_workflow_skill" / "tmp" / "eval"
    path.mkdir(parents=True, exist_ok=True)
    return path


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def run(repo: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT_DIR / "check_hyptest_cli_contract.py"), "--repo-root", str(repo)],
        capture_output=True,
        text=True,
        check=False,
    )


def main() -> int:
    failures: list[str] = []
    with tempfile.TemporaryDirectory(prefix="hyptest_cli_contract_", dir=temp_parent()) as tmpdir:
        tmp = Path(tmpdir)
        good = tmp / "good"
        write(
            good / "compile_elf.py",
            'REPO_ROOT = Path(__file__).resolve().parent\n'
            'OUTPUT_DIR = REPO_ROOT / "case_elf_asm"\n'
            'DEFAULT_TMP_ROOT = REPO_ROOT / ".tmp" / "hyptest_compile"\n'
            'TEST_REGISTER_RE = r"\\s*(?://.*)?$"\n'
            'parser.add_argument("--plat")\n'
            'parser.add_argument("--cross-compile")\n'
            'parser.add_argument("--include-commented")\n'
            'VALID_PLATS = ["spike", "nemu", "linknan"]\n'
            'ARTIFACT_MAP_FILE = "artifact_name_map.json"\n',
        )
        write(
            good / "get_result.py",
            'PLATFORMS = ("spike", "linknan")\n'
            'parser.add_argument(\n        "--platform"\n)\n'
            'DEFAULT_ELF_DIRS = {"spike": REPO_ROOT / "case_elf_asm" / "spike"}\n'
            'DEFAULT_LOG_DIRS = {"spike": REPO_ROOT / ".tmp" / "result_log" / "spike"}\n'
            'TEST_REGISTER_RE = r"\\s*(?://.*)?$"\n'
            'ARTIFACT_MAP_FILE = "artifact_name_map.json"\n'
            'cmd = "${SPIKE_BIN:?set SPIKE_BIN to the spike executable}"\n'
            'cmd += "${LINKNAN_HOME:?set LINKNAN_HOME to the LinkNan repository root}"\n'
            'cmd += "${DIFFTEST_REF_SO:?set DIFFTEST_REF_SO to riscv64-spike-so}"\n',
        )
        write(good / "test_register.c", "TEST_REGISTER(ai_smoke);\n")
        good_result = run(good)
        if good_result.returncode != 0:
            failures.append("good fixture should pass")

        bad = tmp / "bad"
        write(
            bad / "compile_elf.py",
            f'OUTPUT_DIR = Path("{NONCURRENT_CASE_DIR}")\n'
            'parser.add_argument("--plat")\n',
        )
        write(
            bad / "get_result.py",
            'PLATFORMS = ("spike", "xiangshan")\n'
            f"# {NONCURRENT_XIANGSHAN_PLATFORM}\n"
            'SPIKE_BIN = "/nfs/home/user/spike"\n',
        )
        write(bad / "test_register.c", "TEST_REGISTER(ai_bad);\n")
        bad_result = run(bad)
        if bad_result.returncode == 0:
            failures.append("bad fixture should fail")
        if NONCURRENT_CASE_DIR not in bad_result.stdout or "xiangshan" not in bad_result.stdout:
            failures.append("bad fixture should report non-current directory and platform")

    if failures:
        print("FAIL hyptest CLI contract eval")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("PASS hyptest CLI contract eval")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
