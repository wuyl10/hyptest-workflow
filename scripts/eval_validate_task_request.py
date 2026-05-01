#!/usr/bin/env python3
"""Regression checks for validate_task_request.py."""

from __future__ import annotations

import json
import os
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
        env_request_md = tmp / "request_env.md"
        env_request_md.write_text(
            "repo_root: $HYPTEST_EVAL_REPO\n"
            "test_point_file: $HYPTEST_EVAL_REPO/test_point/p.md\n"
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
            normalized = ok_payload.get("normalized", {})
            if normalized.get("coverage_scope") != "repo":
                failures.append("new-case-only should infer coverage_scope=repo")
        ok_md = run("--request-md", str(request_md), "--json")
        if ok_md.returncode != 0:
            failures.append("request-md fixture should pass")
        old_env = os.environ.get("HYPTEST_EVAL_REPO")
        os.environ["HYPTEST_EVAL_REPO"] = str(repo)
        try:
            ok_env_md = run("--request-md", str(env_request_md), "--json")
        finally:
            if old_env is None:
                os.environ.pop("HYPTEST_EVAL_REPO", None)
            else:
                os.environ["HYPTEST_EVAL_REPO"] = old_env
        if ok_env_md.returncode != 0:
            failures.append("request-md fixture with env var paths should pass")
        else:
            env_payload = json.loads(ok_env_md.stdout)
            normalized = env_payload.get("normalized", {})
            if normalized.get("repo_root") != str(repo.resolve()):
                failures.append("env var repo_root should expand to the real repo path")
        supplement = run(
            "--repo-root",
            str(repo),
            "--test-point-file",
            str(repo / "test_point/p.md"),
            "--platform",
            "spike",
            "--task-mode",
            "supplement-existing-point",
            "--json",
        )
        if supplement.returncode != 0:
            failures.append("supplement-existing-point fixture should pass")
        else:
            supplement_payload = json.loads(supplement.stdout)
            if supplement_payload.get("normalized", {}).get("coverage_scope") != "file":
                failures.append("supplement-existing-point should infer coverage_scope=file")
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
