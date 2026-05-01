#!/usr/bin/env python3
"""Smoke-test case_batch_gate_pack.py with two independent cases."""

from __future__ import annotations

import json
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


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def chmod_exec(path: Path) -> None:
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def main() -> int:
    failures: list[str] = []
    profile = default_spec_profile()
    with tempfile.TemporaryDirectory(prefix="hyptest_batch_gate_", dir=temp_parent()) as tmpdir:
        repo = Path(tmpdir) / "repo"
        cases = ["ai_arch_batch_gate_case_a", "ai_arch_batch_gate_case_b"]
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
            "(out/(a.case+'_batch.log')).write_text('PASS\\nHIT GOOD TRAP\\n')\n"
            "print('PASS', a.case)\n",
        )
        chmod_exec(repo / "get_result.py")
        write(repo / "test_register.c", "".join(f"TEST_REGISTER({case})\n" for case in cases))
        body = ""
        for case in cases:
            body += (
                f"bool {case}() {{\n"
                "    TEST_START();\n"
                "    TEST_SETUP_EXCEPT();\n"
                "    TEST_ASSERT(\"batch gate\", true);\n"
                f"    TEST_END(\"{case}\");\n"
                "}\n\n"
            )
        write(repo / "ai_test_cases/batch_gate.c", body)
        (repo / "manual_test_cases").mkdir(parents=True)
        test_point = repo / "test_point/batch_gate.md"
        write(
            test_point,
            "### P1A. batch gate\n\n"
            "测试点：\n\n"
            "- batch gate path\n\n"
            "构建场景：\n\n"
            "- batch gate assertion\n\n"
            "已实现 case：\n\n"
            + "".join(f"- `{case}`（default，已启用）\n" for case in cases),
        )
        command = [
            sys.executable,
            str(SCRIPT_DIR / "case_batch_gate_pack.py"),
            "--repo-root",
            str(repo),
            "--test-point-file",
            str(test_point),
            "--platform",
            "spike",
            "--spec-profile",
            profile,
            "--json",
        ]
        for case in cases:
            command.extend(["--case", case])
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
        if completed.returncode != 0:
            failures.append(f"case_batch_gate_pack returned {completed.returncode}: {completed.stderr or completed.stdout}")
            payload = {}
        else:
            try:
                payload = json.loads(completed.stdout)
            except json.JSONDecodeError as exc:
                failures.append(f"case_batch_gate_pack did not emit JSON: {exc}")
                payload = {}
        if payload:
            if not payload.get("ok"):
                failures.append("case_batch_gate_pack ok=false for smoke repo")
            if payload.get("parallel"):
                failures.append("case_batch_gate_pack should default to serial execution")
            results = payload.get("case_results", {})
            if set(results) != set(cases):
                failures.append("case_batch_gate_pack missing per-case results")
            for case in cases:
                if not results.get(case, {}).get("payload", {}).get("run_log_evidence"):
                    failures.append(f"case_batch_gate_pack missing run log evidence for {case}")

    if failures:
        print("FAIL case batch gate pack eval")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("PASS case batch gate pack eval")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
