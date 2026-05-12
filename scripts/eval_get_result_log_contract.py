#!/usr/bin/env python3
"""Regression checks for check_get_result_log_contract.py."""

from __future__ import annotations

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


def run(repo: Path, log: Path | None = None) -> subprocess.CompletedProcess[str]:
    command = [
        sys.executable,
        str(SCRIPT_DIR / "check_get_result_log_contract.py"),
        "--repo-root",
        str(repo),
    ]
    if log:
        command.extend(["--sample-log", str(log)])
    return subprocess.run(command, capture_output=True, text=True, check=False)


def main() -> int:
    failures: list[str] = []
    with tempfile.TemporaryDirectory(prefix="hyptest_get_result_contract_", dir=temp_parent()) as tmpdir:
        tmp = Path(tmpdir)
        good = tmp / "good"
        write(
            good / "get_result.py",
            "# 总 log 和终端结尾会统计 pass/fail/timeout/missing 以及 forbidden/untested marker 数\n"
            "missing_required found_forbidden untested_occurrences timeout pass fail missing forbidden untested status_counts\n",
        )
        log = tmp / "result.log"
        write(
            log,
            "summary: pass=1 fail=2 timeout=3 missing=4 forbidden=5 untested=6\n"
            "status_counts:\n"
            "  MARKER_MISMATCH: 2\n"
            "  PASS: 1\n"
            "case_a: missing_required=['PASSED'], found_forbidden=['FAILED']\n",
        )
        good_result = run(good, log)
        if good_result.returncode != 0:
            failures.append("good get_result/log fixture should pass")

        bad = tmp / "bad"
        write(bad / "get_result.py", "pass only\n")
        bad_result = run(bad)
        if bad_result.returncode == 0:
            failures.append("bad get_result fixture should fail")
        if "timeout" not in bad_result.stdout:
            failures.append("bad fixture should report missing summary tokens")

    if failures:
        print("FAIL get_result log contract eval")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("PASS get_result log contract eval")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
