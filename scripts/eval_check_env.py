#!/usr/bin/env python3
"""
Run focused regression checks for check_env.py.
"""

from __future__ import annotations

import json
import os
import stat
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


def write(path: Path, text: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def make_executable(path: Path) -> None:
    write(path, "#!/bin/sh\nexit 0\n")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def make_repo(root: Path, *, missing: str | None = None) -> None:
    for rel in ("compile_elf.py", "get_result.py", "test_register.c"):
        if rel != missing:
            write(root / rel, "")
    for rel in ("ai_test_cases", "manual_test_cases", "test_point"):
        if rel != missing:
            (root / rel).mkdir(parents=True, exist_ok=True)


def run_check(
    repo_root: Path,
    platform: str,
    env: dict[str, str],
    *,
    task_mode: str | None = None,
) -> tuple[int, dict[str, object]]:
    full_env = os.environ.copy()
    full_env.update(env)
    command = [
            sys.executable,
            str(SCRIPT_DIR / "check_env.py"),
            "--repo-root",
            str(repo_root),
            "--platform",
            platform,
            "--json",
    ]
    if task_mode:
        command.extend(["--task-mode", task_mode])
    completed = subprocess.run(
        command,
        env=full_env,
        capture_output=True,
        text=True,
        check=False,
    )
    payload = json.loads(completed.stdout)
    return completed.returncode, payload


def expect(condition: bool, failures: list[str], message: str) -> None:
    if not condition:
        failures.append(message)


def main() -> int:
    failures: list[str] = []
    with tempfile.TemporaryDirectory(
        prefix="hyptest_env_eval_",
        dir=temp_parent(),
    ) as tmpdir:
        tmp = Path(tmpdir)
        repo = tmp / "repo"
        make_repo(repo)
        toolchain = tmp / "toolchain"
        toolchain.mkdir()
        make_executable(toolchain / "riscv64-unknown-elf-gcc")
        spike = tmp / "spike"
        make_executable(spike)
        linknan = tmp / "LinkNan"
        linknan.mkdir()
        difftest = tmp / "riscv64-spike-so"
        write(difftest, "so")

        base_env = {
            "PATH": f"{toolchain}:{os.environ.get('PATH', '')}",
            "CROSS_COMPILE": "riscv64-unknown-elf-",
        }

        rc, payload = run_check(repo, "spike", {**base_env, "SPIKE_BIN": str(spike)})
        expect(rc == 0 and payload["ok"] is True, failures, "valid spike env should pass")

        rc, payload = run_check(repo, "spike", base_env)
        expect(rc == 1 and payload["ok"] is False, failures, "missing SPIKE_BIN should fail")
        spike_check = next(
            item for item in payload["env_checks"] if item["name"] == "SPIKE_BIN"
        )
        expect(
            bool(spike_check.get("impact")),
            failures,
            "SPIKE_BIN check should explain command impact",
        )
        rc, payload = run_check(repo, "spike", base_env, task_mode="triage-only")
        expect(
            rc == 0 and payload["ok"] is True and payload.get("warnings"),
            failures,
            "triage-only should downgrade missing SPIKE_BIN to warning",
        )
        spike_check = next(
            item for item in payload["env_checks"] if item["name"] == "SPIKE_BIN"
        )
        expect(
            spike_check.get("required_for_task") is False,
            failures,
            "triage-only SPIKE_BIN should be marked not required_for_task",
        )

        bad_repo = tmp / "bad_repo"
        make_repo(bad_repo, missing="test_register.c")
        rc, payload = run_check(bad_repo, "spike", {**base_env, "SPIKE_BIN": str(spike)})
        expect(rc == 1, failures, "missing repo anchor should fail")

        rc, payload = run_check(
            repo,
            "linknan",
            {
                **base_env,
                "LINKNAN_HOME": str(linknan),
                "DIFFTEST_REF_SO": str(difftest),
            },
        )
        expect(rc == 0 and payload["ok"] is True, failures, "valid linknan env should pass")

        rc, payload = run_check(
            repo,
            "linknan",
            {
                **base_env,
                "LINKNAN_HOME": str(linknan),
                "DIFFTEST_REF_SO": str(linknan),
            },
        )
        expect(rc == 1, failures, "DIFFTEST_REF_SO pointing to a dir should fail")

    if failures:
        print("FAIL check_env eval")
        for failure in failures:
            print(f"  - {failure}")
        return 1

    print("PASS check_env eval")
    return 0


if __name__ == "__main__":
    sys.exit(main())
