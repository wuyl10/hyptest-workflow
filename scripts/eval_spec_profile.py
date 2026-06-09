#!/usr/bin/env python3
"""
Run focused regression checks for spec profile resolution and validation.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from skill_config import current_profile_anchor, default_spec_profile


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parent


def run(command: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        check=False,
    )


def expect(condition: bool, failures: list[str], message: str) -> None:
    if not condition:
        failures.append(message)


def temp_parent() -> Path:
    path = SKILL_ROOT / ".hyptest_workflow_skill" / "tmp" / "eval"
    path.mkdir(parents=True, exist_ok=True)
    return path


def main() -> int:
    failures: list[str] = []
    resolver = SCRIPT_DIR / "resolve_spec_profile.py"
    checker = SCRIPT_DIR / "check_spec_profile.py"
    default_profile = default_spec_profile()
    default_profile_path = SKILL_ROOT / current_profile_anchor()

    result = run([sys.executable, str(resolver), "--spec-profile", default_profile, "--json"])
    expect(result.returncode == 0, failures, "resolve by profile name failed")
    if result.returncode == 0:
        payload = json.loads(result.stdout)
        expect(Path(payload["path"]) == default_profile_path, failures, "resolve by name returned wrong path")

    result = run(
        [
            sys.executable,
            str(resolver),
            "--spec-profile",
            current_profile_anchor(),
            "--json",
        ],
        cwd=Path.home(),
    )
    expect(result.returncode == 0, failures, "resolve skill-relative profile path from another cwd failed")

    result = run([sys.executable, str(checker), "--spec-profile", default_profile, "--json"])
    expect(result.returncode == 0, failures, f"check {default_profile} profile failed")
    if result.returncode == 0:
        payload = json.loads(result.stdout)
        expect(payload.get("ok") is True, failures, f"{default_profile} profile did not report ok=true")

    result = run([sys.executable, str(checker), "--spec-profile", default_profile, "--strict", "--json"])
    expect(result.returncode == 0, failures, f"strict check for {default_profile} profile failed")

    result = run(
        [
            sys.executable,
            str(checker),
            "--spec-profile",
            "references/spec_profiles/template.md",
            "--strict",
            "--json",
        ]
    )
    expect(result.returncode == 1, failures, "strict check for template profile should fail")

    with tempfile.TemporaryDirectory(
        prefix="hyptest_profile_eval_",
        dir=temp_parent(),
    ) as tmpdir:
        tmp = Path(tmpdir)
        missing_heading = tmp / "missing_heading.md"
        missing_heading.write_text(
            "# Bad Profile\n\n"
            "## 1. 口径优先级\n\n"
            "default manual compile-only blocked spike_gate_applicable\n",
            encoding="utf-8",
        )
        result = run([sys.executable, str(checker), "--spec-profile", str(missing_heading), "--json"])
        expect(result.returncode == 1, failures, "profile missing headings should fail")

        missing_tokens = tmp / "missing_tokens.md"
        missing_tokens.write_text(
            "# Bad Profile\n\n"
            "## 1. 口径优先级\n\n"
            "## 2. 项目范围\n\n"
            "## 3. PMP 粒度约定\n\n"
            "## 4. PMA / PBMT / MMIO / cacheability\n\n"
            "## 5. Official Spike 模型边界\n\n"
            "## 6. 非对齐与异常优先级\n\n"
            "## 7. 分层默认口径\n\n"
            "## 8. Spike 不一致时\n\n",
            encoding="utf-8",
        )
        result = run([sys.executable, str(checker), "--spec-profile", str(missing_tokens), "--json"])
        expect(result.returncode == 1, failures, "profile missing recommended tokens should fail")

        missing_json_blocks = tmp / "missing_json_blocks.md"
        missing_json_blocks.write_text(
            "# Bad Strict Profile\n\n"
            "```hyptest-profile\n"
            "profile: bad\n"
            "pmp_granularity: 4KB\n"
            "official_spike_has_tlb_model: false\n"
            "official_spike_has_cache_model: false\n"
            "official_spike_has_pma_csr: false\n"
            "linknan_difftest_ref_has_pma_csr: unknown\n"
            "default_spike_gate: ordinary\n"
            "```\n\n"
            "## 1. 口径优先级\n\n"
            "## 2. 项目范围\n\n"
            "## 3. PMP 粒度约定\n\n"
            "## 4. PMA / PBMT / MMIO / cacheability\n\n"
            "## 5. Official Spike 模型边界\n\n"
            "## 6. 非对齐与异常优先级\n\n"
            "## 7. 分层默认口径\n\n"
            "## 8. Spike 不一致时\n\n"
            "spike_gate_applicable default manual compile-only blocked\n",
            encoding="utf-8",
        )
        result = run(
            [
                sys.executable,
                str(checker),
                "--spec-profile",
                str(missing_json_blocks),
                "--strict",
                "--json",
            ]
        )
        expect(result.returncode == 1, failures, "strict profile missing JSON blocks should fail")

    if failures:
        print("FAIL spec profile eval")
        for failure in failures:
            print(f"  - {failure}")
        return 1

    print("PASS spec profile eval")
    return 0


if __name__ == "__main__":
    sys.exit(main())
