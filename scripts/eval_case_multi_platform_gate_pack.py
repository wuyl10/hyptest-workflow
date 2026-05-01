#!/usr/bin/env python3
"""Smoke-test case_multi_platform_gate_pack.py contract."""

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


def write(path: Path, text: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def chmod_exec(path: Path) -> None:
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True, check=False)


def main() -> int:
    failures: list[str] = []
    profile = default_spec_profile()
    with tempfile.TemporaryDirectory(prefix="hyptest_multi_gate_", dir=temp_parent()) as tmpdir:
        tmp = Path(tmpdir)
        repo = tmp / "repo"
        case_name = "ai_arch_multi_gate_case"
        write(
            repo / "compile_elf.py",
            "#!/usr/bin/env python3\n"
            "import argparse\n"
            "from pathlib import Path\n"
            "p=argparse.ArgumentParser(); p.add_argument('--plat', default='spike'); p.add_argument('--name', required=True); a=p.parse_args()\n"
            "out=Path('case_elf_asm')/a.plat; out.mkdir(parents=True, exist_ok=True)\n"
            "(out/(a.name+'.ELF')).write_text('elf\\n')\n"
            "(out/(a.name+'.asm')).write_text('asm\\n')\n",
        )
        chmod_exec(repo / "compile_elf.py")
        write(
            repo / "get_result.py",
            "#!/usr/bin/env python3\n"
            "import argparse\n"
            "from pathlib import Path\n"
            "p=argparse.ArgumentParser(); p.add_argument('--platform', default='spike'); p.add_argument('--case', required=True); a=p.parse_args()\n"
            "out=Path('result_log')/a.platform; out.mkdir(parents=True, exist_ok=True)\n"
            "(out/(a.case+'_'+a.platform+'.log')).write_text('PASS\\nHIT GOOD TRAP\\n')\n"
            "print('PASS', a.platform, a.case)\n",
        )
        chmod_exec(repo / "get_result.py")
        write(repo / "test_register.c", f"TEST_REGISTER({case_name})\n")
        write(
            repo / "ai_test_cases/multi_gate.c",
            f"bool {case_name}() {{\n"
            "    TEST_START();\n"
            "    TEST_SETUP_EXCEPT();\n"
            "    TEST_ASSERT(\"multi gate\", true);\n"
            f"    TEST_END(\"{case_name}\");\n"
            "}\n",
        )
        (repo / "manual_test_cases").mkdir(parents=True)
        test_point = repo / "test_point/multi_gate.md"
        write(
            test_point,
            "### P1A. multi gate\n\n"
            "测试点：\n\n"
            "- multi gate path\n\n"
            "构建场景：\n\n"
            "- multi gate assertion\n\n"
            "已实现 case：\n\n"
            f"- `{case_name}`（default，已启用）\n",
        )
        report_dir = tmp / "reports"
        completed = run(
            [
                sys.executable,
                str(SCRIPT_DIR / "case_multi_platform_gate_pack.py"),
                "--repo-root",
                str(repo),
                "--test-point-file",
                str(test_point),
                "--case",
                case_name,
                "--platform",
                "spike",
                "--platform",
                "linknan",
                "--spec-profile",
                profile,
                "--report-dir",
                str(report_dir),
                "--json",
            ]
        )
        if completed.returncode != 0:
            failures.append(completed.stderr.strip() or completed.stdout.strip())
        else:
            payload = json.loads(completed.stdout)
            if not payload.get("ok"):
                failures.append("multi-platform gate should pass")
            results = payload.get("platform_results", {})
            if set(results) != {"spike", "linknan"}:
                failures.append("multi-platform gate missing platform results")
            for platform in ("spike", "linknan"):
                if not results.get(platform, {}).get("payload", {}).get("ok"):
                    failures.append(f"{platform} nested gate payload should pass")
                if not (report_dir / f"case_gate_{platform}.json").is_file():
                    failures.append(f"{platform} gate json report missing")
            if "spike" not in payload.get("timing", {}).get("by_step", {}):
                failures.append("multi-platform gate missing per-platform timing")
            if "decision" in payload and payload.get("decision"):
                failures.append("multi-platform gate must not decide final tier")

    if failures:
        print("FAIL case multi-platform gate eval")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("PASS case multi-platform gate eval")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
