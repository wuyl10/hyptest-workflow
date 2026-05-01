#!/usr/bin/env python3
"""Smoke-test case_gate_pack.py compile/run/postcheck contract."""

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


def chmod_exec(path: Path) -> None:
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True, check=False)


def load_json_output(
    completed: subprocess.CompletedProcess[str],
    failures: list[str],
    name: str,
    *,
    expect_rc: int = 0,
) -> dict[str, object]:
    if completed.returncode != expect_rc:
        failures.append(
            f"{name} returned {completed.returncode}, expected {expect_rc}: "
            f"{completed.stderr.strip() or completed.stdout.strip()}"
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
    with tempfile.TemporaryDirectory(prefix="hyptest_case_gate_", dir=temp_parent()) as tmpdir:
        tmp = Path(tmpdir)
        repo = tmp / "repo"
        case_name = "ai_arch_gate_smoke_case"

        write(
            repo / "compile_elf.py",
            "#!/usr/bin/env python3\n"
            "import argparse\n"
            "from pathlib import Path\n"
            "p=argparse.ArgumentParser(); p.add_argument('--plat', default='spike'); p.add_argument('--name', required=True); a=p.parse_args()\n"
            "out=Path('case_elf_asm')/a.plat; out.mkdir(parents=True, exist_ok=True)\n"
            "(out/(a.name+'.ELF')).write_text('elf\\n')\n"
            "(out/(a.name+'.asm')).write_text('asm\\n')\n"
            "print('compiled', a.name)\n",
        )
        chmod_exec(repo / "compile_elf.py")
        write(
            repo / "get_result.py",
            "#!/usr/bin/env python3\n"
            "import argparse\n"
            "from pathlib import Path\n"
            "p=argparse.ArgumentParser(); p.add_argument('--platform', default='spike'); p.add_argument('--case', required=True); a=p.parse_args()\n"
            "out=Path('result_log')/a.platform; out.mkdir(parents=True, exist_ok=True)\n"
            "(out/(a.case+'_smoke.log')).write_text('PASSED\\nHIT GOOD TRAP\\n')\n"
            "print('PASSED', a.case)\n",
        )
        chmod_exec(repo / "get_result.py")
        write(repo / "test_register.c", f"TEST_REGISTER({case_name})\n")
        write(
            repo / "ai_test_cases/gate_smoke.c",
            f"bool {case_name}() {{\n"
            "    TEST_START();\n"
            "    TEST_SETUP_EXCEPT();\n"
            "    TEST_ASSERT(\"gate smoke\", true);\n"
            f"    TEST_END(\"{case_name}\");\n"
            "}\n",
        )
        (repo / "manual_test_cases").mkdir(parents=True)
        test_point = repo / "test_point/gate_smoke.md"
        write(
            test_point,
            "### P1A. gate smoke\n\n"
            "测试点：\n\n"
            "- gate smoke path\n\n"
            "构建场景：\n\n"
            "- gate smoke assertion\n\n"
            "已实现 case：\n\n"
            f"- `{case_name}`（default，已启用）\n",
        )

        completed = run(
            [
                sys.executable,
                str(SCRIPT_DIR / "case_gate_pack.py"),
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
            ]
        )
        payload = load_json_output(completed, failures, "case_gate_pack")
        if payload:
            if not payload.get("ok"):
                failures.append("case_gate_pack ok=false for smoke repo")
            for step in ("compile", "run", "postcheck"):
                if not payload.get("commands", {}).get(step, {}).get("ok"):
                    failures.append(f"case_gate_pack step not ok: {step}")
            evidence = payload.get("evidence_requirements", {})
            if not evidence.get("ok"):
                failures.append("case_gate_pack evidence requirements failed for smoke repo")
            timing = payload.get("timing", {})
            if "total_seconds" not in timing or not timing.get("by_step"):
                failures.append("case_gate_pack missing timing data")
            post_cases = payload.get("commands", {}).get("postcheck", {}).get("payload", {}).get("cases", [])
            if not post_cases or not post_cases[0].get("latest_logs"):
                failures.append("case_gate_pack postcheck missing latest log evidence")
            run_logs = payload.get("run_log_evidence", [])
            if not run_logs or not run_logs[0].get("new_or_updated"):
                failures.append("case_gate_pack should capture the run-created log as direct evidence")

        no_log_repo = tmp / "no_log_repo"
        no_log_case = "ai_arch_gate_no_log_case"
        write(
            no_log_repo / "compile_elf.py",
            "#!/usr/bin/env python3\n"
            "import argparse\n"
            "from pathlib import Path\n"
            "p=argparse.ArgumentParser(); p.add_argument('--plat', default='spike'); p.add_argument('--name', required=True); a=p.parse_args()\n"
            "out=Path('case_elf_asm')/a.plat; out.mkdir(parents=True, exist_ok=True)\n"
            "(out/(a.name+'.ELF')).write_text('elf\\n')\n"
            "(out/(a.name+'.asm')).write_text('asm\\n')\n"
            "print('compiled', a.name)\n",
        )
        chmod_exec(no_log_repo / "compile_elf.py")
        write(
            no_log_repo / "get_result.py",
            "#!/usr/bin/env python3\n"
            "import argparse\n"
            "p=argparse.ArgumentParser(); p.add_argument('--platform', default='spike'); p.add_argument('--case', required=True); a=p.parse_args()\n"
            "print('PASSED without log', a.case)\n",
        )
        chmod_exec(no_log_repo / "get_result.py")
        write(no_log_repo / "test_register.c", f"TEST_REGISTER({no_log_case})\n")
        write(
            no_log_repo / "ai_test_cases/no_log.c",
            f"bool {no_log_case}() {{\n"
            "    TEST_START();\n"
            "    TEST_SETUP_EXCEPT();\n"
            "    TEST_ASSERT(\"gate no log\", true);\n"
            f"    TEST_END(\"{no_log_case}\");\n"
            "}\n",
        )
        (no_log_repo / "manual_test_cases").mkdir(parents=True)
        no_log_test_point = no_log_repo / "test_point/no_log.md"
        write(
            no_log_test_point,
            "### P1A. gate no log\n\n"
            "测试点：\n\n"
            "- gate no log path\n\n"
            "构建场景：\n\n"
            "- gate no log assertion\n\n"
            "已实现 case：\n\n"
            f"- `{no_log_case}`（default，已启用）\n",
        )

        no_log_completed = run(
            [
                sys.executable,
                str(SCRIPT_DIR / "case_gate_pack.py"),
                "--repo-root",
                str(no_log_repo),
                "--test-point-file",
                str(no_log_test_point),
                "--case",
                no_log_case,
                "--platform",
                "spike",
                "--spec-profile",
                profile,
                "--json",
            ]
        )
        no_log_payload = load_json_output(
            no_log_completed,
            failures,
            "case_gate_pack_missing_log",
            expect_rc=1,
        )
        if no_log_payload:
            evidence = no_log_payload.get("evidence_requirements", {})
            requirements = evidence.get("requirements", {})
            if no_log_payload.get("ok"):
                failures.append("case_gate_pack should fail when run log evidence is missing")
            if evidence.get("ok"):
                failures.append("case_gate_pack evidence should fail when run log is missing")
            if requirements.get("artifact_elf") is not True or requirements.get("latest_log") is not False:
                failures.append("case_gate_pack missing-log requirements are not precise")

        compile_only_completed = run(
            [
                sys.executable,
                str(SCRIPT_DIR / "case_gate_pack.py"),
                "--repo-root",
                str(no_log_repo),
                "--test-point-file",
                str(no_log_test_point),
                "--case",
                no_log_case,
                "--platform",
                "spike",
                "--spec-profile",
                profile,
                "--compile-only",
                "--json",
            ]
        )
        compile_only_payload = load_json_output(
            compile_only_completed,
            failures,
            "case_gate_pack_compile_only",
        )
        if compile_only_payload:
            evidence = compile_only_payload.get("evidence_requirements", {})
            requirements = evidence.get("requirements", {})
            if not compile_only_payload.get("ok"):
                failures.append("case_gate_pack compile-only should pass without run log")
            if not evidence.get("ok"):
                failures.append("case_gate_pack compile-only evidence should pass without run log")
            if requirements.get("artifact_elf") is not True or requirements.get("latest_log") is not True:
                failures.append("case_gate_pack compile-only requirements are not precise")

        compile_fail_repo = tmp / "compile_fail_repo"
        compile_fail_case = "ai_arch_gate_compile_fail_case"
        write(
            compile_fail_repo / "compile_elf.py",
            "#!/usr/bin/env python3\n"
            "import sys\n"
            "print('compile failed')\n"
            "sys.exit(1)\n",
        )
        chmod_exec(compile_fail_repo / "compile_elf.py")
        write(
            compile_fail_repo / "get_result.py",
            "#!/usr/bin/env python3\n"
            "from pathlib import Path\n"
            "Path('run_was_called').write_text('bad')\n"
            "print('should not run')\n",
        )
        chmod_exec(compile_fail_repo / "get_result.py")
        write(compile_fail_repo / "test_register.c", f"TEST_REGISTER({compile_fail_case})\n")
        write(
            compile_fail_repo / "ai_test_cases/compile_fail.c",
            f"bool {compile_fail_case}() {{\n"
            "    TEST_START();\n"
            "    TEST_SETUP_EXCEPT();\n"
            "    TEST_ASSERT(\"gate compile fail\", true);\n"
            f"    TEST_END(\"{compile_fail_case}\");\n"
            "}\n",
        )
        (compile_fail_repo / "manual_test_cases").mkdir(parents=True)
        compile_fail_test_point = compile_fail_repo / "test_point/compile_fail.md"
        write(
            compile_fail_test_point,
            "### P1A. gate compile fail\n\n"
            "测试点：\n\n"
            "- gate compile fail path\n\n"
            "构建场景：\n\n"
            "- gate compile fail assertion\n\n"
            "已实现 case：\n\n"
            f"- `{compile_fail_case}`（default，已启用）\n",
        )
        compile_fail_completed = run(
            [
                sys.executable,
                str(SCRIPT_DIR / "case_gate_pack.py"),
                "--repo-root",
                str(compile_fail_repo),
                "--test-point-file",
                str(compile_fail_test_point),
                "--case",
                compile_fail_case,
                "--platform",
                "spike",
                "--spec-profile",
                profile,
                "--json",
            ]
        )
        compile_fail_payload = load_json_output(
            compile_fail_completed,
            failures,
            "case_gate_pack_compile_fail",
            expect_rc=1,
        )
        if compile_fail_payload:
            if "run" in compile_fail_payload.get("commands", {}):
                failures.append("case_gate_pack must not run get_result.py after compile failure")
            if (compile_fail_repo / "run_was_called").exists():
                failures.append("compile failure early-stop did not prevent get_result.py execution")
            if compile_fail_payload.get("skipped", {}).get("run") != "compile failed; run skipped":
                failures.append("case_gate_pack should explain compile-failure run skip")
            requirements = compile_fail_payload.get("evidence_requirements", {}).get("requirements", {})
            if requirements.get("latest_log") is not True:
                failures.append("latest_log should not be required when run was skipped after compile failure")

        run_fail_repo = tmp / "run_fail_repo"
        run_fail_case = "ai_arch_gate_run_fail_case"
        write(
            run_fail_repo / "compile_elf.py",
            "#!/usr/bin/env python3\n"
            "import argparse\n"
            "from pathlib import Path\n"
            "p=argparse.ArgumentParser(); p.add_argument('--plat', default='spike'); p.add_argument('--name', required=True); a=p.parse_args()\n"
            "out=Path('case_elf_asm')/a.plat; out.mkdir(parents=True, exist_ok=True)\n"
            "(out/(a.name+'.ELF')).write_text('elf\\n')\n"
            "(out/(a.name+'.asm')).write_text('asm\\n')\n",
        )
        chmod_exec(run_fail_repo / "compile_elf.py")
        write(
            run_fail_repo / "get_result.py",
            "#!/usr/bin/env python3\n"
            "import argparse, sys\n"
            "from pathlib import Path\n"
            "p=argparse.ArgumentParser(); p.add_argument('--platform', default='spike'); p.add_argument('--case', required=True); a=p.parse_args()\n"
            "out=Path('result_log')/a.platform; out.mkdir(parents=True, exist_ok=True)\n"
            "(out/(a.case+'_failed.log')).write_text('FAILED\\nassert_site=smoke assert_expr=0\\n')\n"
            "print('FAILED', a.case)\n"
            "sys.exit(1)\n",
        )
        chmod_exec(run_fail_repo / "get_result.py")
        write(run_fail_repo / "test_register.c", f"TEST_REGISTER({run_fail_case})\n")
        write(
            run_fail_repo / "ai_test_cases/run_fail.c",
            f"bool {run_fail_case}() {{\n"
            "    TEST_START();\n"
            "    TEST_SETUP_EXCEPT();\n"
            "    TEST_ASSERT(\"gate run fail\", true);\n"
            f"    TEST_END(\"{run_fail_case}\");\n"
            "}\n",
        )
        (run_fail_repo / "manual_test_cases").mkdir(parents=True)
        run_fail_test_point = run_fail_repo / "test_point/run_fail.md"
        write(
            run_fail_test_point,
            "### P1A. gate run fail\n\n"
            "测试点：\n\n"
            "- gate run fail path\n\n"
            "构建场景：\n\n"
            "- gate run fail assertion\n\n"
            "已实现 case：\n\n"
            f"- `{run_fail_case}`（default，已启用）\n",
        )
        run_fail_completed = run(
            [
                sys.executable,
                str(SCRIPT_DIR / "case_gate_pack.py"),
                "--repo-root",
                str(run_fail_repo),
                "--test-point-file",
                str(run_fail_test_point),
                "--case",
                run_fail_case,
                "--platform",
                "spike",
                "--spec-profile",
                profile,
                "--json",
            ]
        )
        run_fail_payload = load_json_output(
            run_fail_completed,
            failures,
            "case_gate_pack_run_fail",
            expect_rc=1,
        )
        if run_fail_payload:
            classification = run_fail_payload.get("failure_classification") or {}
            if not classification.get("attempted"):
                failures.append("case_gate_pack should classify latest failure log after run failure")
            if not str(classification.get("log_file", "")).endswith("_failed.log"):
                failures.append("case_gate_pack should classify the direct run-created failure log")
            if not classification.get("payload", {}).get("reason_code_candidates"):
                failures.append("case_gate_pack failure classification should include reason code candidates")
            timing = run_fail_payload.get("timing", {}).get("by_step", {})
            if "failure_classification" not in timing:
                failures.append("case_gate_pack timing should include failure_classification")

    if failures:
        print("FAIL case gate pack eval")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("PASS case gate pack eval")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
