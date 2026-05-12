#!/usr/bin/env python3
"""Regression checks for validate_task_request.py."""

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
    path = SKILL_ROOT / ".hyptest_workflow_skill" / "tmp" / "eval"
    path.mkdir(parents=True, exist_ok=True)
    return path


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def make_executable(path: Path) -> None:
    write(path, "#!/bin/sh\nexit 0\n")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def run(
    *args: str,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    for name in (
        "HYPTEST_HOME",
        "HYPTEST_EVAL_HOME",
        "HYPTEST_SPIKE_BIN",
        "HYPTEST_LINKNAN_HOME",
        "HYPTEST_DIFFTEST_REF_SO",
        "HYPTEST_CROSS_COMPILE",
        "HYPTEST_TMPDIR",
        "HYPTEST_REPO",
        "HYPTEST_NANHU_HOME",
        "SPIKE_BIN",
        "LINKNAN_HOME",
        "NANHU_HOME",
        "DIFFTEST_REF_SO",
        "CROSS_COMPILE",
        "TMPDIR",
    ):
        env.pop(name, None)
    env.update(extra_env or {})
    return subprocess.run(
        [sys.executable, str(SCRIPT_DIR / "validate_task_request.py"), *args],
        env=env,
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
        spike = tmp / "spike"
        make_executable(spike)
        linknan = tmp / "LinkNan"
        nanhu = linknan / "dependencies" / "nanhu" / "src" / "main"
        nanhu.mkdir(parents=True)
        difftest = tmp / "riscv64-spike-so"
        write(difftest, "so")
        request_json = tmp / "request.json"
        request_json.write_text(
            json.dumps(
                {
                    "HYPTEST_HOME": str(repo),
                    "test_point_file": str(repo / "test_point/p.md"),
                    "platform": "spike",
                    "spec_profile": profile,
                    "task_mode": "new-case-only",
                    "new_case_count": "1-3",
                    "HYPTEST_SPIKE_BIN": str(spike),
                }
            ),
            encoding="utf-8",
        )
        template_profile_request_json = tmp / "request_template_profile.json"
        template_profile_request_json.write_text(
            json.dumps(
                {
                    "HYPTEST_HOME": str(repo),
                    "test_point_file": str(repo / "test_point/p.md"),
                    "platform": "spike",
                    "spec_profile": "template",
                    "task_mode": "preflight-only",
                }
            ),
            encoding="utf-8",
        )
        request_md = tmp / "request.md"
        request_md.write_text(
            f"HYPTEST_HOME: {repo}\n"
            f"test_point_file: {repo / 'test_point/p.md'}\n"
            "platform: spike\n"
            "task_mode: run-only\n"
            "case_name: ai_smoke\n"
            f"HYPTEST_SPIKE_BIN: {spike}\n",
            encoding="utf-8",
        )
        env_request_md = tmp / "request_env.md"
        env_request_md.write_text(
            "HYPTEST_HOME: $HYPTEST_EVAL_HOME\n"
            "test_point_file: $HYPTEST_EVAL_HOME/test_point/p.md\n"
            "platform: spike\n"
            "task_mode: run-only\n"
            "case_name: ai_smoke\n",
            encoding="utf-8",
        )
        env_fallback_request_md = tmp / "request_env_fallback.md"
        env_fallback_request_md.write_text(
            "test_point_file: test_point/p.md\n"
            "platform: spike\n"
            "task_mode: run-only\n"
            "case_name: ai_smoke\n",
            encoding="utf-8",
        )
        alias_request_md = tmp / "request_alias.md"
        alias_request_md.write_text(
            f"- HYPTEST_HOME: {repo}\n"
            "- test_point_file: test_point/p.md\n"
            "- platform: spike\n"
            "- task_mode: run-only\n"
            "- case_name: ai_smoke\n"
            f"- HYPTEST_SPIKE_BIN: {spike}\n"
            "- HYPTEST_CROSS_COMPILE: riscv64-unknown-elf-\n",
            encoding="utf-8",
        )
        natural_spike_only_md = tmp / "request_natural_spike_only.md"
        natural_spike_only_md.write_text(
            f"HYPTEST_HOME: {repo}\n"
            "test_point_file: test_point/p.md\n"
            "platform: spike\n"
            "task_mode: run-only\n"
            "case_name: ai_smoke\n"
            f"HYPTEST_SPIKE_BIN: {spike}\n"
            "本轮只跑 spike，不需要 LinkNan/difftest-ref。\n",
            encoding="utf-8",
        )
        old_prompt_fields_md = tmp / "request_old_prompt_fields.md"
        old_prompt_fields_md.write_text(
            f"repo_root: {repo}\n"
            "test_point_file: test_point/p.md\n"
            "platform: spike\n"
            "task_mode: run-only\n"
            "case_name: ai_smoke\n"
            f"SPIKE_BIN: {spike}\n",
            encoding="utf-8",
        )
        old_repo_env_request_md = tmp / "request_old_repo_env.md"
        old_repo_env_request_md.write_text(
            "test_point_file: test_point/p.md\n"
            "platform: spike\n"
            "task_mode: run-only\n"
            "case_name: ai_smoke\n",
            encoding="utf-8",
        )
        preflight_only_md = tmp / "request_preflight_only.md"
        preflight_only_md.write_text(
            f"HYPTEST_HOME: {repo}\n"
            "test_point_file: test_point/p.md\n"
            "platform: spike\n"
            "task_mode: preflight-only\n",
            encoding="utf-8",
        )
        spike_with_linknan_source_md = tmp / "request_spike_with_linknan_source.md"
        spike_with_linknan_source_md.write_text(
            f"HYPTEST_HOME: {repo}\n"
            "test_point_file: test_point/p.md\n"
            "platform: spike\n"
            "task_mode: run-only\n"
            "case_name: ai_smoke\n"
            f"HYPTEST_SPIKE_BIN: {spike}\n"
            f"HYPTEST_LINKNAN_HOME: {linknan}\n",
            encoding="utf-8",
        )
        broken_spike_with_linknan_source_md = tmp / "request_broken_spike_with_linknan_source.md"
        broken_spike_linknan = tmp / "BrokenSpikeSourceLinkNan"
        broken_spike_linknan.mkdir()
        broken_spike_with_linknan_source_md.write_text(
            f"HYPTEST_HOME: {repo}\n"
            "test_point_file: test_point/p.md\n"
            "platform: spike\n"
            "task_mode: run-only\n"
            "case_name: ai_smoke\n"
            f"HYPTEST_SPIKE_BIN: {spike}\n"
            f"HYPTEST_LINKNAN_HOME: {broken_spike_linknan}\n",
            encoding="utf-8",
        )
        linknan_request_md = tmp / "request_linknan.md"
        linknan_request_md.write_text(
            f"HYPTEST_HOME: {repo}\n"
            "test_point_file: test_point/p.md\n"
            "platform: linknan\n"
            "task_mode: run-only\n"
            "case_name: ai_smoke\n"
            f"HYPTEST_LINKNAN_HOME: {linknan}\n"
            f"HYPTEST_DIFFTEST_REF_SO: {difftest}\n",
            encoding="utf-8",
        )
        linknan_missing_spike_marker_md = tmp / "request_linknan_missing_spike_marker.md"
        linknan_missing_spike_marker_md.write_text(
            f"HYPTEST_HOME: {repo}\n"
            "test_point_file: test_point/p.md\n"
            "platform: linknan\n"
            "task_mode: run-only\n"
            "case_name: ai_smoke\n"
            f"HYPTEST_LINKNAN_HOME: {linknan}\n"
            f"HYPTEST_DIFFTEST_REF_SO: {difftest}\n",
            encoding="utf-8",
        )
        bad_spike_placeholder_md = tmp / "request_bad_spike_placeholder.md"
        bad_spike_placeholder_md.write_text(
            f"HYPTEST_HOME: {repo}\n"
            "test_point_file: test_point/p.md\n"
            "platform: spike\n"
            "task_mode: run-only\n"
            "case_name: ai_smoke\n"
            "HYPTEST_SPIKE_BIN: not needed\n",
            encoding="utf-8",
        )
        bad_linknan_placeholder_md = tmp / "request_bad_linknan_placeholder.md"
        bad_linknan_placeholder_md.write_text(
            f"HYPTEST_HOME: {repo}\n"
            "test_point_file: test_point/p.md\n"
            "platform: linknan\n"
            "task_mode: run-only\n"
            "case_name: ai_smoke\n"
            "HYPTEST_LINKNAN_HOME: not needed\n"
            "HYPTEST_DIFFTEST_REF_SO: not needed\n",
            encoding="utf-8",
        )
        unresolved_template_md = tmp / "request_unresolved_template.md"
        unresolved_template_md.write_text(
            "HYPTEST_HOME: <riscv-hyp-tests-nhv5.1 仓库根目录>\n"
            "test_point_file: test_point/<xxx>.md\n"
            "platform: spike\n"
            "spec_profile: <当前项目 spec_profile>\n"
            "task_mode: preflight-only\n",
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
            env_overrides = normalized.get("env_overrides", {})
            if env_overrides.get("SPIKE_BIN") != str(spike):
                failures.append("request-json should capture HYPTEST_SPIKE_BIN as SPIKE_BIN env override")
            next_commands = "\n".join(ok_payload.get("next_commands", []))
            if f"--env HYPTEST_SPIKE_BIN={spike}" not in next_commands:
                failures.append("next_commands should pass prompt HYPTEST_SPIKE_BIN via --env")
        template_profile = run("--request-json", str(template_profile_request_json), "--json")
        if template_profile.returncode != 0:
            failures.append("request-json spec_profile should override argparse default profile")
        else:
            template_payload = json.loads(template_profile.stdout)
            if template_payload.get("normalized", {}).get("spec_profile") != "template":
                failures.append("request-json spec_profile=template should be preserved")
            if "template.md" not in str(template_payload.get("normalized", {}).get("spec_profile_path")):
                failures.append("request-json spec_profile=template should resolve template.md")
        ok_md = run("--request-md", str(request_md), "--json")
        if ok_md.returncode != 0:
            failures.append("request-md fixture should pass")
        ok_env_md = run(
            "--request-md",
            str(env_request_md),
            "--env",
            f"HYPTEST_SPIKE_BIN={spike}",
            "--json",
            extra_env={"HYPTEST_EVAL_HOME": str(repo)},
        )
        if ok_env_md.returncode != 0:
            failures.append("request-md fixture with env var paths should pass")
        else:
            env_payload = json.loads(ok_env_md.stdout)
            normalized = env_payload.get("normalized", {})
            if normalized.get("repo_root") != str(repo.resolve()):
                failures.append("HYPTEST_HOME variable should expand to the real repo path")
        ok_env_fallback_md = run(
            "--request-md",
            str(env_fallback_request_md),
            "--json",
            extra_env={
                "HYPTEST_HOME": str(repo),
                "HYPTEST_SPIKE_BIN": str(spike),
            },
        )
        if ok_env_fallback_md.returncode != 0:
            failures.append("request-md should use process HYPTEST_HOME and HYPTEST_SPIKE_BIN when prompt omits them")
        else:
            fallback_payload = json.loads(ok_env_fallback_md.stdout)
            normalized = fallback_payload.get("normalized", {})
            if normalized.get("repo_root") != str(repo.resolve()):
                failures.append("process HYPTEST_HOME should map to normalized repo_root")
            if normalized.get("repo_root_source") != "HYPTEST_HOME":
                failures.append("repo_root_source should record process HYPTEST_HOME fallback")
        bare_spike_env_md = run(
            "--request-md",
            str(env_fallback_request_md),
            "--json",
            extra_env={
                "HYPTEST_HOME": str(repo),
                "SPIKE_BIN": str(spike),
            },
        )
        if bare_spike_env_md.returncode == 0:
            failures.append("request-md should not accept bare SPIKE_BIN as HYPTEST_SPIKE_BIN")
        else:
            bare_spike_payload = json.loads(bare_spike_env_md.stdout)
            issues = "\n".join(bare_spike_payload.get("issues", []))
            if "requires HYPTEST_SPIKE_BIN" not in issues:
                failures.append("bare SPIKE_BIN should fail with a missing HYPTEST_SPIKE_BIN issue")
        alias_md = run("--request-md", str(alias_request_md), "--json")
        if alias_md.returncode != 0:
            failures.append("request-md fixture with HYPTEST_HOME and HYPTEST_* fields should pass")
        else:
            alias_payload = json.loads(alias_md.stdout)
            normalized = alias_payload.get("normalized", {})
            if normalized.get("repo_root") != str(repo.resolve()):
                failures.append("HYPTEST_HOME prompt field should map to repo_root")
            env_overrides = normalized.get("env_overrides", {})
            if env_overrides.get("CROSS_COMPILE") != "riscv64-unknown-elf-":
                failures.append("HYPTEST_CROSS_COMPILE prompt field should be captured as env override")
            if env_overrides.get("SPIKE_BIN") != str(spike):
                failures.append("HYPTEST_SPIKE_BIN prompt field should be captured as env override")
        natural_md = run("--request-md", str(natural_spike_only_md), "--json")
        if natural_md.returncode != 0:
            failures.append("natural-language spike-only fixture should pass")
        else:
            natural_payload = json.loads(natural_md.stdout)
            if natural_payload.get("warnings"):
                failures.append("natural-language spike-only fixture should not warn about LinkNan/difftest-ref")
        old_prompt = run("--request-md", str(old_prompt_fields_md), "--json")
        if old_prompt.returncode == 0:
            failures.append("old prompt fields repo_root/SPIKE_BIN should not be accepted")
        else:
            old_payload = json.loads(old_prompt.stdout)
            issues = "\n".join(old_payload.get("issues", []))
            warnings = "\n".join(old_payload.get("warnings", []))
            if "HYPTEST_HOME is required" not in issues:
                failures.append("old repo_root prompt field should be ignored and require HYPTEST_HOME")
            if "accepted for compatibility" in warnings:
                failures.append("old prompt fields should not produce compatibility warnings")
        old_repo_env = run(
            "--request-md",
            str(old_repo_env_request_md),
            "--json",
            extra_env={
                "HYPTEST_REPO": str(repo),
                "HYPTEST_SPIKE_BIN": str(spike),
            },
        )
        if old_repo_env.returncode == 0:
            failures.append("process HYPTEST_REPO should not satisfy missing HYPTEST_HOME")
        else:
            old_repo_payload = json.loads(old_repo_env.stdout)
            issues = "\n".join(old_repo_payload.get("issues", []))
            if "HYPTEST_HOME is required" not in issues:
                failures.append("process HYPTEST_REPO should fail with a missing HYPTEST_HOME issue")
        preflight_only = run("--request-md", str(preflight_only_md), "--json")
        if preflight_only.returncode != 0:
            failures.append("preflight-only fixture should pass without case_name or HYPTEST_SPIKE_BIN")
        else:
            preflight_payload = json.loads(preflight_only.stdout)
            if preflight_payload.get("normalized", {}).get("coverage_scope") != "repo":
                failures.append("preflight-only should infer coverage_scope=repo")
            if any("case-name" in warning.lower() or "case_name" in warning.lower() for warning in preflight_payload.get("warnings", [])):
                failures.append("preflight-only should not warn about missing case_name")
        spike_with_source = run("--request-md", str(spike_with_linknan_source_md), "--json")
        if spike_with_source.returncode != 0:
            failures.append("spike fixture with LinkNan source evidence should pass when nanhu/src/main exists")
        broken_spike_with_source = run("--request-md", str(broken_spike_with_linknan_source_md), "--json")
        if (
            broken_spike_with_source.returncode == 0
            or "HYPTEST_LINKNAN_HOME was provided for source evidence" not in broken_spike_with_source.stdout
        ):
            failures.append("spike fixture with LinkNan source evidence should fail when nanhu/src/main is missing")
        linknan_md = run("--request-md", str(linknan_request_md), "--json")
        if linknan_md.returncode != 0:
            failures.append("linknan fixture without HYPTEST_SPIKE_BIN should pass when LinkNan env is provided")
        else:
            linknan_payload = json.loads(linknan_md.stdout)
            env_overrides = linknan_payload.get("normalized", {}).get("env_overrides", {})
            if "SPIKE_BIN" in env_overrides:
                failures.append("omitted HYPTEST_SPIKE_BIN should not be emitted for linknan fixture")
            if env_overrides.get("LINKNAN_HOME") != str(linknan):
                failures.append("linknan fixture should capture LINKNAN_HOME")
            if env_overrides.get("DIFFTEST_REF_SO") != str(difftest):
                failures.append("linknan fixture should capture DIFFTEST_REF_SO")
            if any("SPIKE_BIN" in warning for warning in linknan_payload.get("warnings", [])):
                failures.append("linknan fixture should not warn about omitted HYPTEST_SPIKE_BIN")
        broken_linknan_request = tmp / "request_broken_linknan_nanhu.md"
        broken_linknan = tmp / "BrokenLinkNan"
        broken_linknan.mkdir()
        broken_linknan_request.write_text(
            f"HYPTEST_HOME: {repo}\n"
            "test_point_file: test_point/p.md\n"
            "platform: linknan\n"
            "task_mode: run-only\n"
            "case_name: ai_smoke\n"
            f"HYPTEST_LINKNAN_HOME: {broken_linknan}\n"
            f"HYPTEST_DIFFTEST_REF_SO: {difftest}\n",
            encoding="utf-8",
        )
        broken_linknan_md = run("--request-md", str(broken_linknan_request), "--json")
        if (
            broken_linknan_md.returncode == 0
            or "Nanhu source was not found under HYPTEST_LINKNAN_HOME/dependencies/nanhu/src/main"
            not in broken_linknan_md.stdout
        ):
            failures.append("linknan request should fail when LinkNan nanhu/src/main is missing")
        linknan_missing_marker = run(
            "--request-md",
            str(linknan_missing_spike_marker_md),
            "--json",
        )
        if linknan_missing_marker.returncode != 0:
            failures.append("linknan fixture without HYPTEST_SPIKE_BIN should pass")
        else:
            linknan_missing_payload = json.loads(linknan_missing_marker.stdout)
            warnings = "\n".join(linknan_missing_payload.get("warnings", []))
            if "SPIKE_BIN" in warnings:
                failures.append("linknan fixture should not suggest HYPTEST_SPIKE_BIN")
        bad_spike_placeholder = run(
            "--request-md",
            str(bad_spike_placeholder_md),
            "--json",
        )
        if (
            bad_spike_placeholder.returncode == 0
            or "requires a real HYPTEST_SPIKE_BIN path, not a placeholder" not in bad_spike_placeholder.stdout
        ):
            failures.append("platform=spike should reject placeholder HYPTEST_SPIKE_BIN")
        bad_linknan_placeholder = run(
            "--request-md",
            str(bad_linknan_placeholder_md),
            "--json",
        )
        if (
            bad_linknan_placeholder.returncode == 0
            or "requires real path(s), not placeholder values" not in bad_linknan_placeholder.stdout
        ):
            failures.append("platform=linknan should reject placeholder LinkNan fields")
        unresolved_template = run("--request-md", str(unresolved_template_md), "--json")
        if unresolved_template.returncode == 0:
            failures.append("unresolved angle-bracket template fields should fail")
        else:
            unresolved_template_payload = json.loads(unresolved_template.stdout)
            issues = "\n".join(unresolved_template_payload.get("issues", []))
            if "template placeholder" not in issues:
                failures.append("unresolved angle-bracket template fields should get a placeholder issue")
            if "spec_profile not found" in issues:
                failures.append("placeholder spec_profile should not cascade into profile-not-found noise")
        supplement = run(
            "--repo-root",
            str(repo),
            "--test-point-file",
            str(repo / "test_point/p.md"),
            "--platform",
            "spike",
            "--task-mode",
            "supplement-existing-point",
            "--env",
            f"HYPTEST_SPIKE_BIN={spike}",
            "--json",
        )
        if supplement.returncode != 0:
            failures.append("supplement-existing-point fixture should pass")
        else:
            supplement_payload = json.loads(supplement.stdout)
            if supplement_payload.get("normalized", {}).get("coverage_scope") != "file":
                failures.append("supplement-existing-point should infer coverage_scope=file")
        unresolved = tmp / "request_unresolved.md"
        unresolved.write_text(
            "HYPTEST_HOME: $MISSING_HYPTEST_HOME\n"
            "test_point_file: test_point/p.md\n"
            "platform: spike\n"
            "task_mode: run-only\n"
            "case_name: ai_smoke\n"
            "HYPTEST_SPIKE_BIN: $MISSING_HYPTEST_SPIKE_BIN\n",
            encoding="utf-8",
        )
        bad_env = run("--request-md", str(unresolved), "--json")
        if bad_env.returncode == 0:
            failures.append("unresolved prompt variables should fail")
        else:
            bad_env_payload = json.loads(bad_env.stdout)
            issues = "\n".join(bad_env_payload.get("issues", []))
            if "MISSING_HYPTEST_HOME" not in issues or "MISSING_HYPTEST_SPIKE_BIN" not in issues:
                failures.append("unresolved prompt variables should identify both missing variables")
        missing_platform = run(
            "--repo-root",
            str(repo),
            "--test-point-file",
            str(repo / "test_point/p.md"),
            "--task-mode",
            "new-case-only",
            "--new-case-count",
            "1",
            "--json",
        )
        if missing_platform.returncode == 0 or "requires platform" not in missing_platform.stdout:
            failures.append("new-case-only without platform should fail with a platform hint")
        bad_platform = run("--request-json", str(request_json), "--platform", "xiangshan", "--json")
        if bad_platform.returncode == 0 or "platform=xiangshan" not in bad_platform.stdout:
            failures.append("explicit bad platform should fail and override request-json")
        try:
            bad_payload = json.loads(bad_platform.stdout)
        except json.JSONDecodeError:
            failures.append("bad platform JSON output should be parseable")
        else:
            if bad_payload.get("normalized", {}).get("platform") == "linknan":
                failures.append("bad platform should not be normalized to a valid platform")
            if "HYPTEST_LINKNAN_HOME" in "\n".join(bad_payload.get("issues", [])):
                failures.append("bad platform should not cascade into LinkNan env requirements")
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
