#!/usr/bin/env python3
"""
Check the hyptest repo and platform environment before compile/run commands.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

from skill_config import expand_path, resolve_path


REQUIRED_REPO_FILES = [
    "compile_elf.py",
    "get_result.py",
    "test_register.c",
]

REQUIRED_REPO_DIRS = [
    "ai_test_cases",
    "manual_test_cases",
    "test_point",
]
TASK_MODES = {
    "new-case-only",
    "supplement-existing-point",
    "fix-case",
    "run-only",
    "triage-only",
    "writeback-only",
}

ENV_EXPLANATIONS = {
    "CROSS_COMPILE": (
        "RISC-V bare-metal toolchain prefix. compile_elf.py/Makefile use "
        "<prefix>gcc and related binutils; default is riscv64-unknown-elf-."
    ),
    "SPIKE_BIN": (
        "Official Spike executable used by get_result.py when platform=spike."
    ),
    "LINKNAN_HOME": (
        "LinkNan workspace root used to locate simv, create run directories, "
        "and run platform=linknan."
    ),
    "DIFFTEST_REF_SO": (
        "Difftest reference shared object passed to LinkNan simv for "
        "platform=linknan difftest runs."
    ),
}

ENV_IMPACTS = {
    "CROSS_COMPILE": [
        "compile_elf.py cannot build ELF files when the toolchain prefix is wrong or not in PATH.",
        "Makefile compile targets using <prefix>gcc/binutils will fail.",
    ],
    "SPIKE_BIN": [
        "get_result.py platform=spike cannot run official Spike.",
        "Spike-only default gate evidence cannot be collected.",
    ],
    "LINKNAN_HOME": [
        "get_result.py platform=linknan cannot locate the LinkNan simv workspace.",
        "LinkNan run directories cannot be created under the expected sim path.",
    ],
    "DIFFTEST_REF_SO": [
        "LinkNan difftest runs cannot pass the +diff reference shared object.",
        "platform=linknan run evidence is incomplete without the reference model.",
    ],
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check hyptest repo anchors and platform environment variables."
    )
    parser.add_argument("--repo-root", required=True, help="Path to hyptest repo root.")
    parser.add_argument(
        "--platform",
        choices=["spike", "linknan", "all"],
        required=True,
        help="Target platform to check; use all to check both Spike and LinkNan env vars.",
    )
    parser.add_argument(
        "--task-mode",
        choices=sorted(TASK_MODES),
        help="Use task context to downgrade platform env misses that are not required for this task.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON report.",
    )
    parser.add_argument(
        "--print-exports",
        action="store_true",
        help="Print example export commands when required env vars are missing.",
    )
    parser.add_argument(
        "--explain",
        action="store_true",
        help="Print what each checked environment variable is used for.",
    )
    return parser.parse_args()


def env_value(name: str) -> str:
    return os.environ.get(name, "").strip()


def check_executable(path: Path) -> bool:
    return path.is_file() and os.access(path, os.X_OK)


def check_toolchain() -> dict[str, object]:
    prefix = env_value("CROSS_COMPILE") or "riscv64-unknown-elf-"
    gcc_name = f"{prefix}gcc"
    gcc_path = shutil.which(gcc_name)
    return {
        "name": "CROSS_COMPILE",
        "value": prefix,
        "gcc": gcc_name,
        "gcc_path": gcc_path,
        "ok": gcc_path is not None,
        "required": True,
        "required_for_task": True,
        "explain": ENV_EXPLANATIONS["CROSS_COMPILE"],
        "impact": ENV_IMPACTS["CROSS_COMPILE"],
    }


def check_env_path(
    name: str,
    *,
    executable: bool = False,
    file_only: bool = False,
) -> dict[str, object]:
    value = env_value(name)
    path = expand_path(value) if value else None
    exists = bool(path and path.exists())
    is_file = bool(path and path.is_file())
    ok = bool(
        exists
        and (not file_only or is_file)
        and (not executable or check_executable(path))
    )
    return {
        "name": name,
        "value": value or None,
        "exists": exists,
        "is_file": is_file,
        "executable": check_executable(path) if path else False,
        "ok": ok,
        "required": True,
        "required_for_task": True,
        "explain": ENV_EXPLANATIONS.get(name, ""),
        "impact": ENV_IMPACTS.get(name, []),
    }


def is_platform_env_required_for_task(task_mode: str | None) -> bool:
    return task_mode not in {"triage-only", "writeback-only"}


def add_env_issue_or_warning(
    report: dict[str, object],
    item: dict[str, object],
    message: str,
    *,
    required_for_task: bool,
) -> None:
    item["required_for_task"] = required_for_task
    target = "issues" if required_for_task else "warnings"
    report[target].append(message)


def append_platform_env_checks(report: dict[str, object], platform: str, task_mode: str | None) -> None:
    env_checks = report["env_checks"]
    assert isinstance(env_checks, list)
    required_for_task = is_platform_env_required_for_task(task_mode)

    if platform in {"spike", "all"}:
        spike = check_env_path("SPIKE_BIN", executable=True)
        env_checks.append(spike)
        if not spike["ok"]:
            add_env_issue_or_warning(
                report,
                spike,
                "SPIKE_BIN is required for Spike runs and must point to an executable file",
                required_for_task=required_for_task,
            )

    if platform in {"linknan", "all"}:
        linknan = check_env_path("LINKNAN_HOME")
        difftest = check_env_path("DIFFTEST_REF_SO", file_only=True)
        env_checks.extend([linknan, difftest])
        if not linknan["ok"]:
            add_env_issue_or_warning(
                report,
                linknan,
                "LINKNAN_HOME is required for LinkNan runs and must point to an existing path",
                required_for_task=required_for_task,
            )
        if not difftest["ok"]:
            add_env_issue_or_warning(
                report,
                difftest,
                "DIFFTEST_REF_SO is required for LinkNan runs and must point to an existing file",
                required_for_task=required_for_task,
            )


def build_report(repo_root: Path, platform: str, task_mode: str | None = None) -> dict[str, object]:
    report: dict[str, object] = {
        "repo_root": str(repo_root),
        "platform": platform,
        "task_mode": task_mode,
        "ok": True,
        "issues": [],
        "warnings": [],
        "repo_checks": [],
        "env_checks": [],
    }

    repo_checks = report["repo_checks"]
    assert isinstance(repo_checks, list)
    for rel in REQUIRED_REPO_FILES:
        path = repo_root / rel
        item = {"path": rel, "kind": "file", "ok": path.is_file()}
        repo_checks.append(item)
        if not item["ok"]:
            report["issues"].append(f"missing required repo file: {rel}")

    for rel in REQUIRED_REPO_DIRS:
        path = repo_root / rel
        item = {"path": rel, "kind": "dir", "ok": path.is_dir()}
        repo_checks.append(item)
        if not item["ok"]:
            report["issues"].append(f"missing required repo dir: {rel}")

    env_checks = report["env_checks"]
    assert isinstance(env_checks, list)
    toolchain = check_toolchain()
    env_checks.append(toolchain)
    if not toolchain["ok"]:
        report["issues"].append(
            f"toolchain not found: {toolchain['gcc']} (set CROSS_COMPILE or PATH)"
        )

    append_platform_env_checks(report, platform, task_mode)

    report["ok"] = not report["issues"]
    return report


def print_text_report(report: dict[str, object]) -> None:
    status = "PASS" if report["ok"] else "FAIL"
    print(f"{status} hyptest environment")
    print(f"repo_root: {report['repo_root']}")
    print(f"platform: {report['platform']}")
    if report.get("task_mode"):
        print(f"task_mode: {report['task_mode']}")
    for issue in report["issues"]:
        print(f"  issue: {issue}")
    for warning in report.get("warnings", []):
        print(f"  warning: {warning}")

    print("repo checks:")
    for item in report["repo_checks"]:
        marker = "ok" if item["ok"] else ("missing-required" if item.get("required_for_task", True) else "missing-optional")
        print(f"  {marker}: {item['kind']} {item['path']}")

    print("environment checks:")
    for item in report["env_checks"]:
        marker = "ok" if item["ok"] else "missing"
        if item["name"] == "CROSS_COMPILE":
            print(f"  {marker}: {item['gcc']} -> {item['gcc_path']}")
        else:
            print(f"  {marker}: {item['name']} -> {item['value']}")


def print_export_hints(report: dict[str, object]) -> None:
    missing = [
        item["name"]
        for item in report["env_checks"]
        if item.get("required_for_task") and not item.get("ok") and item["name"] != "CROSS_COMPILE"
    ]
    if not missing:
        return
    print("export hints:")
    examples = {
        "SPIKE_BIN": "/path/to/spike",
        "LINKNAN_HOME": "/path/to/LinkNan",
        "DIFFTEST_REF_SO": "/path/to/riscv64-spike-so",
    }
    for name in missing:
        print(f"  export {name}={examples.get(name, '<path>')}")


def print_explanations(report: dict[str, object]) -> None:
    print("environment variable usage:")
    for item in report["env_checks"]:
        detail = item.get("explain")
        if detail:
            print(f"  {item['name']}: {detail}")
        impact = item.get("impact")
        if impact:
            for line in impact:
                print(f"    affects: {line}")


def main() -> int:
    args = parse_args()
    repo_root = resolve_path(args.repo_root)
    report = build_report(repo_root, args.platform, args.task_mode)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print_text_report(report)
        if args.explain:
            print_explanations(report)
        if args.print_exports:
            print_export_hints(report)

    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
