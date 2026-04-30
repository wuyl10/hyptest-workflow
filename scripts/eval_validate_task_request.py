#!/usr/bin/env python3
"""Regression checks for validate_task_request.py."""

from __future__ import annotations

import json
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


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT_DIR / "validate_task_request.py"), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def main() -> int:
    failures: list[str] = []
    profile = default_spec_profile()
    with tempfile.TemporaryDirectory(prefix="hyptest_request_eval_", dir=temp_parent()) as tmpdir:
        tmp = Path(tmpdir)
        repo = tmp / "repo"
        write(repo / "compile_elf.py", "")
        write(repo / "get_result.py", "")
        write(repo / "test_register.c", "")
        write(repo / "test_point/p.md", "### P1A\n")
        request_json = tmp / "request.json"
        request_json.write_text(
            json.dumps(
                {
                    "repo_root": str(repo),
                    "test_point_file": str(repo / "test_point/p.md"),
                    "platform": "spike",
                    "spec_profile": profile,
                    "task_mode": "new-case-only",
                    "new_case_count": "1-3",
                    "coverage_scope": "repo",
                }
            ),
            encoding="utf-8",
        )
        request_md = tmp / "request.md"
        request_md.write_text(
            f"repo_root: {repo}\n"
            f"test_point_file: {repo / 'test_point/p.md'}\n"
            "platform: spike\n"
            "task_mode: run-only\n"
            "case_name: ai_smoke\n",
            encoding="utf-8",
        )
        ok_json = run("--request-json", str(request_json), "--json")
        if ok_json.returncode != 0:
            failures.append("request-json fixture should pass")
        else:
            ok_payload = json.loads(ok_json.stdout)
            if not ok_payload.get("next_commands"):
                failures.append("request-json fixture should include next_commands")
            elif profile not in "\n".join(ok_payload["next_commands"]):
                failures.append("next_commands should include resolved task profile")
        ok_md = run("--request-md", str(request_md), "--json")
        if ok_md.returncode != 0:
            failures.append("request-md fixture should pass")
        bad_platform = run("--request-json", str(request_json), "--platform", "xiangshan", "--json")
        if bad_platform.returncode == 0 or "platform=xiangshan" not in bad_platform.stdout:
            failures.append("explicit bad platform should fail and override request-json")
        try:
            bad_payload = json.loads(bad_platform.stdout)
        except json.JSONDecodeError:
            failures.append("bad platform JSON output should be parseable")
        else:
            if bad_payload.get("normalized", {}).get("platform") != "linknan":
                failures.append("bad platform should normalize platform to linknan")
            details = bad_payload.get("issue_details", [])
            if not details or not details[0].get("suggested_fix"):
                failures.append("bad platform should include suggested_fix")

    if failures:
        print("FAIL validate_task_request eval")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("PASS validate_task_request eval")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
