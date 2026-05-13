#!/usr/bin/env python3
"""
Check the hyptest repo and platform environment before compile/run commands.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import time
from pathlib import Path

from skill_config import (
    apply_env_overrides,
    env_export_hint,
    expand_path,
    hyptest_env_name,
    prompt_field_hint,
    process_env_value,
    resolve_path,
)
from workflow_paths import cache_file


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
    "preflight-only",
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
        "Community/upstream Spike executable used by get_result.py when platform=spike. "
        "Use this for architecture/default gate evidence."
    ),
    "LINKNAN_HOME": (
        "LinkNan workspace root used to locate simv, create run directories, "
        "and run platform=linknan."
    ),
    "NANHU_SOURCE": (
        "Nanhu source tree used for RTL/source evidence when hunting suspected bugs. "
        "It is derived from HYPTEST_LINKNAN_HOME/dependencies/nanhu/src/main."
    ),
    "DIFFTEST_REF_SO": (
        "Difftest reference shared object, often built from the project/custom "
        "Spike tree, passed to LinkNan simv for platform=linknan difftest runs."
    ),
}

ENV_IMPACTS = {
    "CROSS_COMPILE": [
        "compile_elf.py cannot build ELF files when the toolchain prefix is wrong or not in PATH.",
        "Makefile compile targets using <prefix>gcc/binutils will fail.",
    ],
    "SPIKE_BIN": [
        "get_result.py platform=spike cannot run community/upstream Spike.",
        "Spike-only default gate evidence cannot be collected.",
    ],
    "LINKNAN_HOME": [
        "get_result.py platform=linknan cannot locate the LinkNan simv workspace.",
        "LinkNan run directories cannot be created under the expected sim path.",
    ],
    "NANHU_SOURCE": [
        "RTL/source evidence for Nanhu cannot be located under the LinkNan checkout.",
        "Suspected bug hunting may lack source context until the LinkNan nanhu submodule is initialized.",
    ],
    "DIFFTEST_REF_SO": [
        "LinkNan difftest runs cannot pass the +diff reference shared object.",
        "platform=linknan run evidence is incomplete without the reference model.",
    ],
}

# env probe cache
CACHE_VERSION = 1
CACHE_FILENAME = "env_probe.json"
DEFAULT_CACHE_TTL_HOURS = 12


def env_probe_cache_path(repo_root: Path, cache_dir_arg: str | None = None) -> Path:
    return cache_file(repo_root, CACHE_FILENAME, cache_dir_arg)


def _cache_key(
    repo_root: Path,
    platform: str,
    task_mode: str | None,
    platform_env_optional: bool,
    env_overrides: dict[str, str],
) -> dict[str, object]:
    # Include only fields that, if they change, should invalidate the cache.
    # HYPTEST_* values are captured so that a user override change invalidates.
    return {
        "repo_root": str(repo_root),
        "platform": platform,
        "task_mode": task_mode,
        "platform_env_optional": platform_env_optional,
        "env_overrides": {k: v for k, v in sorted(env_overrides.items())},
        "env_snapshot": {
            name: os.environ.get(name, "")
            for name in (
                "HYPTEST_CROSS_COMPILE",
                "HYPTEST_SPIKE_BIN",
                "HYPTEST_LINKNAN_HOME",
                "HYPTEST_DIFFTEST_REF_SO",
                "HYPTEST_TMPDIR",
            )
        },
    }


def _restat_cached_paths(report: dict[str, object]) -> list[str]:
    """Cheap re-stat of paths already recorded in a cached report.

    Returns a list of invalidation reasons. Empty list means cache is still valid.
    """
    reasons: list[str] = []
    for check in report.get("env_checks", []):
        if not isinstance(check, dict):
            continue
        # Toolchain check records the resolved gcc path under "gcc_path".
        gcc_path = check.get("gcc_path")
        if isinstance(gcc_path, str) and gcc_path.startswith("/"):
            if not Path(gcc_path).is_file():
                reasons.append(f"toolchain gone: {gcc_path}")
        # Platform env check records the resolved value as "value" and sets is_file/exists.
        name = check.get("name")
        value = check.get("value")
        if (
            name in ("SPIKE_BIN", "DIFFTEST_REF_SO")
            and isinstance(value, str)
            and value.startswith("/")
        ):
            if not Path(value).is_file():
                reasons.append(f"{name} gone: {value}")
        if name == "LINKNAN_HOME" and isinstance(value, str) and value.startswith("/"):
            if not Path(value).is_dir():
                reasons.append(f"{name} gone: {value}")
        if (
            name == "NANHU_SOURCE"
            and isinstance(value, str)
            and value.startswith("/")
            and not Path(value).is_dir()
        ):
            reasons.append(f"{name} gone: {value}")
    for check in report.get("repo_checks", []):
        if not isinstance(check, dict):
            continue
        rel = check.get("path")
        if rel and isinstance(rel, str):
            full = Path(str(report["repo_root"])) / rel
            kind = check.get("kind")
            if kind == "file" and not full.is_file():
                reasons.append(f"repo file gone: {rel}")
            elif kind == "dir" and not full.is_dir():
                reasons.append(f"repo dir gone: {rel}")
    return reasons


def load_env_probe_cache(
    repo_root: Path,
    key: dict[str, object],
    ttl_hours: float,
    cache_dir_arg: str | None = None,
) -> tuple[dict[str, object] | None, dict[str, object]]:
    """Return (cached_report, cache_info). cached_report is None on miss."""
    path = env_probe_cache_path(repo_root, cache_dir_arg)
    info: dict[str, object] = {"path": str(path), "hit": False}
    if not path.is_file():
        info["miss_reason"] = "no cache file"
        return None, info
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        info["miss_reason"] = f"cache parse error: {exc}"
        return None, info
    if data.get("version") != CACHE_VERSION:
        info["miss_reason"] = "cache version mismatch"
        return None, info
    if data.get("key") != key:
        info["miss_reason"] = "cache key mismatch"
        return None, info
    timestamp = data.get("timestamp", 0)
    age_seconds = max(time.time() - timestamp, 0)
    info["age_seconds"] = age_seconds
    info["ttl_hours"] = ttl_hours
    if age_seconds > ttl_hours * 3600:
        info["miss_reason"] = f"cache expired ({age_seconds/3600:.1f}h > {ttl_hours}h TTL)"
        return None, info
    cached_report = data.get("report")
    if not isinstance(cached_report, dict):
        info["miss_reason"] = "cache report missing"
        return None, info
    restat_reasons = _restat_cached_paths(cached_report)
    if restat_reasons:
        info["miss_reason"] = "re-stat failed: " + "; ".join(restat_reasons[:3])
        return None, info
    info["hit"] = True
    return cached_report, info


def save_env_probe_cache(
    repo_root: Path,
    key: dict[str, object],
    report: dict[str, object],
    cache_dir_arg: str | None = None,
) -> Path:
    path = env_probe_cache_path(repo_root, cache_dir_arg)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": CACHE_VERSION,
        "timestamp": time.time(),
        "key": key,
        "report": report,
    }
    # Unique tmp suffix per process to avoid races when multiple check_env
    # invocations target the same repo in parallel (e.g. case_multi_platform_gate_pack).
    tmp_path = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    try:
        os.replace(tmp_path, path)
    except OSError:
        # Best-effort cleanup; cache save is advisory.
        if tmp_path.is_file():
            try:
                tmp_path.unlink()
            except OSError:
                pass
    return path


def invalidate_env_probe_cache(repo_root: Path, cache_dir_arg: str | None = None) -> None:
    path = env_probe_cache_path(repo_root, cache_dir_arg)
    if path.is_file():
        try:
            path.unlink()
        except OSError:
            pass



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
    parser.add_argument(
        "--platform-env-optional",
        action="store_true",
        help=(
            "Downgrade platform runner env misses such as HYPTEST_SPIKE_BIN to warnings. "
            "Use only for compile-only or postcheck-only flows that will not call get_result.py."
        ),
    )
    parser.add_argument(
        "--env",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help=(
            "Environment override for this check, e.g. --env HYPTEST_SPIKE_BIN=/path/to/spike. "
            "Can be repeated for HYPTEST_LINKNAN_HOME, "
            "HYPTEST_DIFFTEST_REF_SO, HYPTEST_CROSS_COMPILE, HYPTEST_TMPDIR."
        ),
    )
    parser.add_argument(
        "--cache-ttl-hours",
        type=float,
        default=DEFAULT_CACHE_TTL_HOURS,
        help=(
            f"Cache TTL in hours; default {DEFAULT_CACHE_TTL_HOURS}. Cached reports are reused "
            "only when key matches AND all recorded paths still re-stat successfully."
        ),
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Disable env probe cache for this call (always re-run checks and skip write).",
    )
    parser.add_argument(
        "--invalidate-cache",
        action="store_true",
        help="Remove the env probe cache file before running and exit.",
    )
    parser.add_argument(
        "--cache-dir",
        help="Override the cache directory (same flag semantics as repo_evidence_index.py).",
    )
    return parser.parse_args()


def env_value(name: str) -> str:
    return process_env_value(name)


def check_executable(path: Path) -> bool:
    return path.is_file() and os.access(path, os.X_OK)


def runner_role_warnings(name: str, value: str) -> list[str]:
    lowered = value.lower()
    if name == "SPIKE_BIN" and any(
        marker in lowered for marker in ("difftest", "linknan", "xiangshan", "xspike")
    ):
        return [
            "HYPTEST_SPIKE_BIN looks like a custom/difftest runner path. For platform=spike "
            "default gate, prefer a community/upstream riscv-isa-sim Spike binary; "
            "use HYPTEST_DIFFTEST_REF_SO for LinkNan difftest evidence."
        ]
    return []


def shell_startup_definitions(name: str) -> list[dict[str, object]]:
    """Find simple `export NAME=...` definitions in common shell startup files.

    This is diagnostic only. The checker intentionally does not source startup
    files because they can run arbitrary commands and often behave differently
    for interactive shells.
    """
    home = Path.home()
    candidates = [
        home / ".bashrc",
        home / ".bash_profile",
        home / ".profile",
    ]
    names = (hyptest_env_name(name),)
    pattern = re.compile(
        rf"^\s*(?:export\s+)?(?P<name>{'|'.join(re.escape(item) for item in names)})\s*=\s*(.+?)\s*$"
    )
    results: list[dict[str, object]] = []
    for path in candidates:
        if not path.is_file():
            continue
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        noninteractive_return_line = None
        for index, line in enumerate(lines, 1):
            if "return" in line and "$-" in "\n".join(lines[max(0, index - 6):index + 1]):
                noninteractive_return_line = index
            match = pattern.match(line)
            if not match:
                continue
            raw_value = match.group(2).strip().strip('"').strip("'")
            expanded = os.path.expandvars(raw_value.replace("$HOME", str(home)))
            results.append(
                {
                    "file": str(path),
                    "line": index,
                    "name": match.group("name"),
                    "value": raw_value,
                    "expanded_value": expanded,
                    "after_noninteractive_return_guard": bool(
                        noninteractive_return_line is not None
                        and index > noninteractive_return_line
                    ),
                }
            )
    return results


def check_toolchain() -> dict[str, object]:
    prefix = env_value("CROSS_COMPILE") or "riscv64-unknown-elf-"
    gcc_name = f"{prefix}gcc"
    gcc_path = shutil.which(gcc_name)
    return {
        "name": "CROSS_COMPILE",
        "prompt_name": hyptest_env_name("CROSS_COMPILE"),
        "value": prefix,
        "gcc": gcc_name,
        "gcc_path": gcc_path,
        "ok": gcc_path is not None,
        "required": True,
        "required_for_task": True,
        "explain": ENV_EXPLANATIONS["CROSS_COMPILE"],
        "impact": ENV_IMPACTS["CROSS_COMPILE"],
        "prompt_hint": prompt_field_hint("CROSS_COMPILE"),
        "export_hint": env_export_hint("CROSS_COMPILE"),
    }


def check_env_path(
    name: str,
    *,
    executable: bool = False,
    file_only: bool = False,
) -> dict[str, object]:
    value = env_value(name)
    startup_defs = shell_startup_definitions(name) if not value else []
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
        "prompt_name": hyptest_env_name(name),
        "value": value or None,
        "exists": exists,
        "is_file": is_file,
        "executable": check_executable(path) if path else False,
        "ok": ok,
        "required": True,
        "required_for_task": True,
        "explain": ENV_EXPLANATIONS.get(name, ""),
        "impact": ENV_IMPACTS.get(name, []),
        "prompt_hint": prompt_field_hint(name),
        "export_hint": env_export_hint(name),
        "role_warnings": runner_role_warnings(name, value) if value else [],
        "startup_definitions": startup_defs,
        "startup_hint": (
            "Variable was not present in this process environment. If it is "
            "defined in ~/.bashrc, put the export before any non-interactive "
            "`return` guard, or export it in the parent shell before running "
            "the workflow."
            if startup_defs and not value
            else ""
        ),
    }


def infer_nanhu_source_from_linknan() -> tuple[Path | None, str]:
    linknan_value = env_value("LINKNAN_HOME")
    if not linknan_value:
        return None, ""
    linknan_home = expand_path(linknan_value)
    rel = "dependencies/nanhu/src/main"
    return linknan_home / rel, f"HYPTEST_LINKNAN_HOME/{rel}"


def check_nanhu_source() -> dict[str, object]:
    path, source = infer_nanhu_source_from_linknan()
    exists = bool(path and path.exists())
    is_dir = bool(path and path.is_dir())
    ok = exists and is_dir
    return {
        "name": "NANHU_SOURCE",
        "prompt_name": "Nanhu source (from HYPTEST_LINKNAN_HOME)",
        "value": str(path) if path else None,
        "source": source or "missing",
        "exists": exists,
        "is_file": bool(path and path.is_file()),
        "is_dir": is_dir,
        "executable": False,
        "ok": ok,
        "required": True,
        "required_for_task": True,
        "explain": ENV_EXPLANATIONS.get("NANHU_SOURCE", ""),
        "impact": ENV_IMPACTS.get("NANHU_SOURCE", []),
        "prompt_hint": prompt_field_hint("NANHU_SOURCE"),
        "export_hint": env_export_hint("NANHU_SOURCE"),
        "role_warnings": [],
        "startup_definitions": [],
        "startup_hint": (
            "Nanhu source was not found under HYPTEST_LINKNAN_HOME/dependencies/nanhu/src/main. "
            "Initialize the LinkNan nanhu submodule, or fix HYPTEST_LINKNAN_HOME."
            if not ok
            else ""
        ),
    }


def is_platform_env_required_for_task(task_mode: str | None) -> bool:
    return task_mode not in {"preflight-only", "triage-only", "writeback-only"}


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


def append_platform_env_checks(
    report: dict[str, object],
    platform: str,
    task_mode: str | None,
    *,
    platform_env_optional: bool = False,
) -> None:
    env_checks = report["env_checks"]
    assert isinstance(env_checks, list)
    required_for_task = (
        is_platform_env_required_for_task(task_mode)
        and not platform_env_optional
    )

    if platform in {"spike", "all"}:
        spike = check_env_path("SPIKE_BIN", executable=True)
        env_checks.append(spike)
        for warning in spike.get("role_warnings", []):
            report["warnings"].append(str(warning))
        if not spike["ok"]:
            add_env_issue_or_warning(
                report,
                spike,
                "HYPTEST_SPIKE_BIN is required for Spike runs and must point to an executable file",
                required_for_task=required_for_task,
            )

    if platform in {"linknan", "all"}:
        linknan = check_env_path("LINKNAN_HOME")
        nanhu = check_nanhu_source()
        difftest = check_env_path("DIFFTEST_REF_SO", file_only=True)
        env_checks.extend([linknan, nanhu, difftest])
        for warning in nanhu.get("role_warnings", []):
            report["warnings"].append(str(warning))
        if not linknan["ok"]:
            add_env_issue_or_warning(
                report,
                linknan,
                "HYPTEST_LINKNAN_HOME is required for LinkNan runs and must point to an existing path",
                required_for_task=required_for_task,
            )
        if not nanhu["ok"]:
            add_env_issue_or_warning(
                report,
                nanhu,
                "Nanhu source was not found at HYPTEST_LINKNAN_HOME/dependencies/nanhu/src/main; initialize the LinkNan nanhu submodule or fix HYPTEST_LINKNAN_HOME",
                required_for_task=required_for_task,
            )
        if not difftest["ok"]:
            add_env_issue_or_warning(
                report,
                difftest,
                "HYPTEST_DIFFTEST_REF_SO is required for LinkNan runs and must point to an existing file",
                required_for_task=required_for_task,
            )


def build_report(
    repo_root: Path,
    platform: str,
    task_mode: str | None = None,
    *,
    platform_env_optional: bool = False,
    env_overrides: dict[str, str] | None = None,
) -> dict[str, object]:
    report: dict[str, object] = {
        "repo_root": str(repo_root),
        "platform": platform,
        "task_mode": task_mode,
        "platform_env_optional": platform_env_optional,
        "env_overrides": env_overrides or {},
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
            f"toolchain not found: {toolchain['gcc']} (set HYPTEST_CROSS_COMPILE or PATH)"
        )

    append_platform_env_checks(
        report,
        platform,
        task_mode,
        platform_env_optional=platform_env_optional,
    )

    report["ok"] = not report["issues"]
    return report


def print_text_report(report: dict[str, object]) -> None:
    status = "PASS" if report["ok"] else "FAIL"
    print(f"{status} hyptest environment")
    print(f"HYPTEST_HOME: {report['repo_root']}")
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
            print(f"  {marker}: {item['prompt_name']} ({item['gcc']}) -> {item['gcc_path']}")
        else:
            print(f"  {marker}: {item['prompt_name']} (runtime {item['name']}) -> {item['value']}")
        if not item.get("ok") and item.get("required_for_task"):
            if item.get("prompt_hint"):
                print(f"    prompt: {item['prompt_hint']}")
            if item.get("export_hint"):
                print(f"    export: {item['export_hint']}")
        for definition in item.get("startup_definitions", []) or []:
            guard = (
                " after non-interactive return guard"
                if definition.get("after_noninteractive_return_guard")
                else ""
            )
            print(
                "    startup definition: "
                f"{definition.get('file')}:{definition.get('line')} "
                f"{definition.get('name')}{guard}"
            )
        if item.get("startup_hint"):
            print(f"    hint: {item['startup_hint']}")


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
        "SPIKE_BIN": "export HYPTEST_SPIKE_BIN=/path/to/spike",
        "LINKNAN_HOME": "export HYPTEST_LINKNAN_HOME=/path/to/LinkNan",
        "NANHU_SOURCE": "git -C \"$HYPTEST_LINKNAN_HOME\" submodule update --init dependencies/nanhu",
        "DIFFTEST_REF_SO": "export HYPTEST_DIFFTEST_REF_SO=/path/to/riscv64-spike-so",
    }
    for name in missing:
        print(f"  {examples.get(name, env_export_hint(name))}")
    print(
        "  note: if you put these exports in ~/.bashrc, keep them before any "
        "non-interactive `return` guard."
    )


def print_explanations(report: dict[str, object]) -> None:
    print("environment variable usage:")
    for item in report["env_checks"]:
        detail = item.get("explain")
        if detail:
            print(f"  {item['prompt_name']}: {detail}")
        impact = item.get("impact")
        if impact:
            for line in impact:
                print(f"    affects: {line}")


def main() -> int:
    args = parse_args()
    try:
        env_overrides = apply_env_overrides(args.env)
    except ValueError as exc:
        print(f"invalid --env: {exc}", file=sys.stderr)
        return 2
    repo_root = resolve_path(args.repo_root)

    if args.invalidate_cache:
        invalidate_env_probe_cache(repo_root, args.cache_dir)
        print("env probe cache invalidated")
        return 0

    cache_info: dict[str, object] = {"hit": False, "enabled": not args.no_cache}
    report: dict[str, object] | None = None
    key = _cache_key(
        repo_root,
        args.platform,
        args.task_mode,
        args.platform_env_optional,
        env_overrides,
    )
    if not args.no_cache:
        report, cache_info = load_env_probe_cache(
            repo_root, key, args.cache_ttl_hours, args.cache_dir
        )
        cache_info["enabled"] = True

    if report is None:
        report = build_report(
            repo_root,
            args.platform,
            args.task_mode,
            platform_env_optional=args.platform_env_optional,
            env_overrides=env_overrides,
        )
        if not args.no_cache and report.get("ok"):
            save_env_probe_cache(repo_root, key, report, args.cache_dir)
            cache_info["saved"] = True

    report["cache"] = cache_info

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print_text_report(report)
        if args.explain:
            print_explanations(report)
        if args.print_exports:
            print_export_hints(report)
        if cache_info.get("hit"):
            age = cache_info.get("age_seconds", 0)
            print(
                f"cache: hit (age {float(age)/60:.1f} min, ttl {cache_info.get('ttl_hours')}h)"
            )
        elif cache_info.get("enabled"):
            reason = cache_info.get("miss_reason", "first run")
            print(f"cache: miss ({reason})")

    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
