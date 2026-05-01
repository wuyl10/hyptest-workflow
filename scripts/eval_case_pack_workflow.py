#!/usr/bin/env python3
"""Smoke-test case_preflight_pack.py and case_postcheck_pack.py contracts."""

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


def run(command: list[str], *, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True, check=False, env=env)


def load_json_output(completed: subprocess.CompletedProcess[str], failures: list[str], name: str) -> dict[str, object]:
    if completed.returncode != 0:
        failures.append(
            f"{name} returned {completed.returncode}: "
            + (completed.stderr.strip() or completed.stdout.strip())
        )
        return {}
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        failures.append(f"{name} did not emit JSON: {exc}")
        return {}


def main() -> int:
    failures: list[str] = []
    profile = default_spec_profile()
    with tempfile.TemporaryDirectory(prefix="hyptest_case_pack_", dir=temp_parent()) as tmpdir:
        tmp = Path(tmpdir)
        repo = tmp / "repo"
        toolchain = tmp / "toolchain"
        toolchain.mkdir()
        make_executable(toolchain / "riscv64-unknown-elf-gcc")
        spike = tmp / "spike"
        make_executable(spike)

        case_name = "ai_arch_pack_smoke_case"
        write(repo / "compile_elf.py", "")
        write(repo / "get_result.py", "")
        write(repo / "test_register.c", f"TEST_REGISTER({case_name})\n")
        write(
            repo / "ai_test_cases/pack_smoke.c",
            f"bool {case_name}() {{\n"
            "    TEST_START();\n"
            "    TEST_SETUP_EXCEPT();\n"
            "    TEST_ASSERT(\"pack smoke\", true);\n"
            f"    TEST_END(\"{case_name}\");\n"
            "}\n",
        )
        (repo / "manual_test_cases").mkdir(parents=True)
        write(
            repo / "test_point/pack_smoke.md",
            "### P1A. pack smoke\n\n"
            "测试点：\n\n"
            "- pack smoke path\n\n"
            "构建场景：\n\n"
            "- pack smoke assertion\n\n"
            "已实现 case：\n\n"
            f"- `{case_name}`（default，已启用）\n",
        )
        write(repo / f"case_elf_asm/spike/{case_name}.ELF", "elf\n")
        write(repo / f"case_elf_asm/spike/{case_name}.asm", "asm\n")
        write(repo / f"result_log/spike/{case_name}_smoke.log", "PASS\nHIT GOOD TRAP\n")

        env = os.environ.copy()
        for name in (
            "SPIKE_BIN", "LINKNAN_HOME", "NANHU_HOME", "DIFFTEST_REF_SO",
            "CROSS_COMPILE", "TMPDIR",
        ):
            env.pop(name, None)
        env.update(
            {
                "PATH": f"{toolchain}:{os.environ.get('PATH', '')}",
                "HYPTEST_CROSS_COMPILE": "riscv64-unknown-elf-",
                "HYPTEST_SPIKE_BIN": str(spike),
            }
        )

        test_point = repo / "test_point/pack_smoke.md"
        preflight = run(
            [
                sys.executable,
                str(SCRIPT_DIR / "case_preflight_pack.py"),
                "--repo-root",
                str(repo),
                "--test-point-file",
                str(test_point),
                "--platform",
                "spike",
                "--spec-profile",
                profile,
                "--task-mode",
                "new-case-only",
                "--new-case-count",
                "1",
                "--query",
                "pack smoke",
                "--json",
            ],
            env=env,
        )
        preflight_payload = load_json_output(preflight, failures, "case_preflight_pack")
        if preflight_payload:
            if not preflight_payload.get("ok"):
                failures.append("case_preflight_pack ok=false for smoke repo")
            if preflight_payload.get("coverage_scope") != "repo":
                failures.append("case_preflight_pack should infer coverage_scope=repo for new-case-only")
            if preflight_payload.get("cache", {}).get("hit"):
                failures.append("first case_preflight_pack run should not be a pack-cache hit")
            similar = preflight_payload.get("commands", {}).get("similar_cases", {})
            if not similar.get("payload", {}).get("reading_pack"):
                failures.append("case_preflight_pack missing similar_cases reading_pack")

        preflight_cached = run(
            [
                sys.executable,
                str(SCRIPT_DIR / "case_preflight_pack.py"),
                "--repo-root",
                str(repo),
                "--test-point-file",
                str(test_point),
                "--platform",
                "spike",
                "--spec-profile",
                profile,
                "--task-mode",
                "new-case-only",
                "--new-case-count",
                "1",
                "--query",
                "pack smoke",
                "--json",
            ],
            env=env,
        )
        preflight_cached_payload = load_json_output(
            preflight_cached,
            failures,
            "case_preflight_pack_cached",
        )
        if preflight_cached_payload:
            cache = preflight_cached_payload.get("cache", {})
            if not cache.get("hit"):
                failures.append("second case_preflight_pack run should be a pack-cache hit")
            if not preflight_cached_payload.get("commands", {}).get("similar_cases", {}).get("payload", {}).get("reading_pack"):
                failures.append("cached case_preflight_pack missing reading_pack")

        env_changed = env.copy()
        env_changed["HYPTEST_SPIKE_BIN"] = str(tmp / "different_spike")
        make_executable(tmp / "different_spike")
        preflight_env_changed = run(
            [
                sys.executable,
                str(SCRIPT_DIR / "case_preflight_pack.py"),
                "--repo-root",
                str(repo),
                "--test-point-file",
                str(test_point),
                "--platform",
                "spike",
                "--spec-profile",
                profile,
                "--task-mode",
                "new-case-only",
                "--new-case-count",
                "1",
                "--query",
                "pack smoke",
                "--json",
            ],
            env=env_changed,
        )
        preflight_env_changed_payload = load_json_output(
            preflight_env_changed,
            failures,
            "case_preflight_pack_env_changed",
        )
        if preflight_env_changed_payload:
            cache = preflight_env_changed_payload.get("cache", {})
            if cache.get("hit"):
                failures.append("case_preflight_pack cache must miss after HYPTEST_SPIKE_BIN changes")
            if not cache.get("environment_digest"):
                failures.append("case_preflight_pack cache should expose environment_digest")
            if not cache.get("script_digest"):
                failures.append("case_preflight_pack cache should expose script_digest")

        postcheck = run(
            [
                sys.executable,
                str(SCRIPT_DIR / "case_postcheck_pack.py"),
                "--repo-root",
                str(repo),
                "--test-point-file",
                str(test_point),
                "--case",
                case_name,
                "--platform",
                "spike",
                "--spec-profile",
                profile,
                "--json",
            ],
            env=env,
        )
        postcheck_payload = load_json_output(postcheck, failures, "case_postcheck_pack")
        if postcheck_payload:
            if not postcheck_payload.get("ok"):
                failures.append("case_postcheck_pack ok=false for smoke repo")
            cases = postcheck_payload.get("cases", [])
            if not cases or not cases[0].get("definition_unique"):
                failures.append("case_postcheck_pack did not prove definition uniqueness")
            if cases and not cases[0].get("artifacts", {}).get("elf"):
                failures.append("case_postcheck_pack missing ELF artifact")
            if cases and not cases[0].get("latest_logs"):
                failures.append("case_postcheck_pack missing latest log evidence")
            if cases and cases[0].get("latest_logs"):
                strategy = cases[0]["latest_logs"][0].get("search_strategy")
                if strategy != "fast-glob":
                    failures.append(f"case_postcheck_pack should use fast-glob for exact log names, got {strategy}")

        preflight_only = run(
            [
                sys.executable,
                str(SCRIPT_DIR / "case_preflight_pack.py"),
                "--repo-root",
                str(repo),
                "--test-point-file",
                str(test_point),
                "--platform",
                "spike",
                "--spec-profile",
                profile,
                "--task-mode",
                "preflight-only",
                "--query",
                "pack smoke",
                "--no-pack-cache",
                "--json",
            ],
            env=env,
        )
        preflight_only_payload = load_json_output(
            preflight_only,
            failures,
            "case_preflight_pack_preflight_only",
        )
        if preflight_only_payload:
            if not preflight_only_payload.get("ok"):
                failures.append("case_preflight_pack preflight-only ok=false for smoke repo")
            if preflight_only_payload.get("coverage_scope") != "repo":
                failures.append("case_preflight_pack preflight-only should infer coverage_scope=repo")

    if failures:
        print("FAIL case pack workflow eval")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("PASS case pack workflow eval")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
