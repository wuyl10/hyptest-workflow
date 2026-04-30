#!/usr/bin/env python3
"""
Validate lightweight hyptest test_point writeback format.

This checker focuses on the conventions enforced by hyptest-workflow:
- no audit-style workflow tail blocks inside test_point files
- each test-point entry uses the lightweight section shape
- reuse evidence, when present, must keep the fixed two-line fields
- optional registration/status checks can be performed against test_register.c
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Tuple

from writeback_register import load_registration_status


ENTRY_HEADER_RE = re.compile(r"^###\s+P[0-9A-Za-z]")
CASE_NAME_RE = re.compile(r"`([A-Za-z_][A-Za-z0-9_]*)`")
DEPENDENCY_STATUS_RE = re.compile(r"^（依赖[^）]+，未跑Spike）$")
PROFILE_NONGATE_RE = re.compile(
    r"PMA|PBMT|MMIO|Device|cache|TLB|refill|replay|CBO|sbuffer|MSHR|PMAADDR|PMACFG",
    re.IGNORECASE,
)

SECTION_TEST_POINT = "测试点："
SECTION_SCENARIO = "构建场景："
SECTION_SUSPECT = "怀疑点："
SECTION_MATCHED = "对应场景："
SECTION_IMPLEMENTED = "已实现 case："
SECTION_REUSE = "复用依据"
SECTION_ORDER = "顺序一致性："
SECTION_ASSERT = "断言一致性："

DISALLOWED_MARKERS = [
    "workflow 回填",
    "[新增 case]",
    "[唯一性检索证据]",
    "[质量门禁结果]",
    "[分层结论]",
    "[编译/运行统计]",
    "[关键日志路径]",
    "[修改文件清单]",
    "[回填结果与注册一致性]",
    "[exclude_check]",
]

ALLOWED_STATUS_SUFFIXES = {
    "",
    "（default，已启用）",
    "（已注释，manual）",
    "已注释（manual）",
    "（compile-only，未跑Spike）",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate lightweight writeback format in hyptest test_point markdown files."
    )
    parser.add_argument(
        "--repo-root",
        help="Optional hyptest repo root; enables test_register.c status checks",
    )
    parser.add_argument(
        "--file",
        action="append",
        default=[],
        help="Specific markdown file to validate; can be repeated",
    )
    parser.add_argument(
        "--glob",
        action="append",
        default=[],
        help="Glob pattern to validate, resolved from repo-root or current directory; can be repeated",
    )
    parser.add_argument(
        "--all-test-points",
        action="store_true",
        help="Validate all test_point markdown files under repo-root.",
    )
    parser.add_argument(
        "--check-register",
        action="store_true",
        help="Check writeback status text against test_register.c when repo-root is given",
    )
    parser.add_argument(
        "--spec-profile",
        help="Optional profile name/path; adds warnings for obvious profile-nongate default markings.",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of text")
    return parser.parse_args()


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def collect_files(args: argparse.Namespace) -> List[Path]:
    files: List[Path] = []
    seen = set()

    for raw in args.file:
        path = Path(raw).expanduser().resolve()
        if path.is_file() and path not in seen:
            seen.add(path)
            files.append(path)

    if args.glob:
        base = Path(args.repo_root).expanduser().resolve() if args.repo_root else Path.cwd()
        for pattern in args.glob:
            for path in sorted(base.glob(pattern)):
                resolved = path.resolve()
                if resolved.is_file() and resolved not in seen:
                    seen.add(resolved)
                    files.append(resolved)

    if args.all_test_points:
        if not args.repo_root:
            raise ValueError("--all-test-points requires --repo-root")
        base = Path(args.repo_root).expanduser().resolve()
        for path in sorted((base / "test_point").glob("*.md")):
            resolved = path.resolve()
            if resolved.is_file() and resolved not in seen:
                seen.add(resolved)
                files.append(resolved)

    return files


def split_entries(lines: List[str]) -> List[Tuple[int, int]]:
    entries: List[Tuple[int, int]] = []
    start = None
    for idx, line in enumerate(lines):
        if ENTRY_HEADER_RE.match(line):
            if start is not None:
                entries.append((start, idx))
            start = idx
    if start is not None:
        entries.append((start, len(lines)))
    return entries


def find_section_index(block: List[str], prefix: str) -> int | None:
    for idx, line in enumerate(block):
        if line.strip().startswith(prefix):
            return idx
    return None


def collect_implemented_case_lines(block: List[str], start_index: int) -> List[str]:
    case_lines: List[str] = []
    for line in block[start_index + 1 :]:
        stripped = line.strip()
        if ENTRY_HEADER_RE.match(line):
            break
        if stripped in {
            SECTION_TEST_POINT,
            SECTION_SCENARIO,
            SECTION_SUSPECT,
            SECTION_MATCHED,
            SECTION_IMPLEMENTED,
        }:
            break
        if stripped.startswith(SECTION_REUSE):
            break
        if stripped.startswith("[") and stripped.endswith("]"):
            break
        if not stripped:
            continue
        case_lines.append(stripped)
    return case_lines


def is_allowed_status_suffix(suffix: str) -> bool:
    if suffix in ALLOWED_STATUS_SUFFIXES:
        return True
    return bool(DEPENDENCY_STATUS_RE.fullmatch(suffix))


def validate_case_lines(
    case_lines: List[str],
    register_status: Dict[str, str],
    check_register: bool,
) -> Tuple[List[str], List[dict[str, str]]]:
    issues: List[str] = []
    warnings: List[dict[str, str]] = []
    if not case_lines:
        return ["`已实现 case` 段为空"], warnings

    found_case_name = False
    for line in case_lines:
        if line.startswith("-"):
            content = line[1:].strip()
        else:
            content = line

        if content.startswith("暂无（原因：") or content == "暂无":
            continue

        match = CASE_NAME_RE.search(content)
        if not match:
            issues.append(f"`已实现 case` 行未包含反引号 case 名: {line}")
            continue

        found_case_name = True
        case_name = match.group(1)
        suffix = content[match.end() :].strip()
        if not is_allowed_status_suffix(suffix):
            issues.append(f"`已实现 case` 行状态说明不符合约定: {line}")
            continue

        if check_register and register_status:
            status = register_status.get(case_name)
            if suffix == "（default，已启用）" and status != "enabled":
                issues.append(
                    f"{case_name} 标注为 default 已启用，但 test_register.c 中不是 enabled"
                )
            if suffix in {
                "（已注释，manual）",
                "已注释（manual）",
                "（compile-only，未跑Spike）",
            } and status != "commented":
                issues.append(
                    f"{case_name} 标注为非 default 未跑 gate，但 test_register.c 中不是 commented"
                )
            if DEPENDENCY_STATUS_RE.fullmatch(suffix) and status != "commented":
                issues.append(
                    f"{case_name} 标注为依赖约束未跑 Spike，但 test_register.c 中不是 commented"
                )

        if suffix == "（default，已启用）" and PROFILE_NONGATE_RE.search(content):
            warnings.append(
                {
                    "warning_code": "PROFILE_NONGATE_DEFAULT",
                    "case": case_name,
                    "message": f"{case_name} default 标注旁出现 PMA/PBMT/MMIO/cache/TLB 等 profile-nongate 关键词，请确认 spike_gate_applicable=true",
                    "suggestion": "若 profile 查询显示 spike_gate_applicable=false，应改为 manual/compile-only/blocked 或补证据。",
                }
            )

    if not found_case_name and not any("暂无" in line for line in case_lines):
        issues.append("`已实现 case` 段未找到有效 case 名")

    return issues, warnings


def validate_entry(
    entry_index: int,
    block: List[str],
    register_status: Dict[str, str],
    check_register: bool,
) -> Tuple[List[str], List[dict[str, str]]]:
    issues: List[str] = []
    warnings: List[dict[str, str]] = []
    title = block[0].strip()
    block_text = "\n".join(block)

    has_test_point = find_section_index(block, SECTION_TEST_POINT) is not None
    has_scenario = find_section_index(block, SECTION_SCENARIO) is not None
    has_suspect = find_section_index(block, SECTION_SUSPECT) is not None
    has_matched = find_section_index(block, SECTION_MATCHED) is not None
    implemented_index = find_section_index(block, SECTION_IMPLEMENTED)
    reuse_index = find_section_index(block, SECTION_REUSE)

    if not has_test_point:
        issues.append(f"{title}: 缺少 `{SECTION_TEST_POINT}`")
    if not (has_scenario or has_matched):
        issues.append(f"{title}: 缺少 `{SECTION_SCENARIO}` 或 `{SECTION_MATCHED}`")
    if has_suspect and not has_matched:
        issues.append(f"{title}: 出现 `{SECTION_SUSPECT}` 时应同时出现 `{SECTION_MATCHED}`")
    if implemented_index is None:
        issues.append(f"{title}: 缺少 `{SECTION_IMPLEMENTED}`")
    else:
        case_issues, case_warnings = validate_case_lines(
            collect_implemented_case_lines(block, implemented_index),
            register_status,
            check_register,
        )
        issues.extend(f"{title}: {issue}" for issue in case_issues)
        for warning in case_warnings:
            warning = dict(warning)
            warning["entry"] = title
            warning["message"] = f"{title}: {warning['message']}"
            warnings.append(warning)

    if reuse_index is not None:
        if find_section_index(block[reuse_index:], SECTION_ORDER) is None:
            issues.append(f"{title}: 出现 `复用依据` 时缺少 `{SECTION_ORDER}`")
        if find_section_index(block[reuse_index:], SECTION_ASSERT) is None:
            issues.append(f"{title}: 出现 `复用依据` 时缺少 `{SECTION_ASSERT}`")

    if PROFILE_NONGATE_RE.search(block_text):
        implemented_lines = (
            collect_implemented_case_lines(block, implemented_index)
            if implemented_index is not None
            else []
        )
        if any("（default，已启用）" in line for line in implemented_lines):
            warnings.append(
                {
                    "warning_code": "PROFILE_NONGATE_ENTRY_DEFAULT",
                    "entry": title,
                    "case": "",
                    "message": f"{title}: 条目包含 PMA/PBMT/MMIO/cache/TLB 等关键词且 case 标为 default，请按 profile 复核 Spike gate",
                    "suggestion": "用 scripts/query_spec_profile.py 查询对应 PMA/PBMT/window 的 default_decision。",
                }
            )

    return issues, warnings


def validate_file(
    path: Path,
    register_status: Dict[str, str],
    check_register: bool,
    profile_text: str = "",
) -> Dict[str, object]:
    text = read_text(path)
    lines = text.splitlines()
    issues: List[str] = []
    warnings: List[dict[str, str]] = []

    for marker in DISALLOWED_MARKERS:
        if marker in text:
            issues.append(f"命中禁止回填块/字段: {marker}")

    entries = split_entries(lines)
    if not entries:
        issues.append("未找到任何 `###` 测试点条目")
    else:
        for idx, (start, end) in enumerate(entries, start=1):
            block = lines[start:end]
            entry_issues, entry_warnings = validate_entry(idx, block, register_status, check_register)
            issues.extend(entry_issues)
            if profile_text:
                warnings.extend(entry_warnings)

    return {
        "file": str(path),
        "entry_count": len(entries),
        "ok": not issues,
        "issues": issues,
        "warnings": warnings,
    }


def resolve_profile_text(raw_profile: str | None) -> str:
    if not raw_profile:
        return ""
    resolver = Path(__file__).resolve().parent / "resolve_spec_profile.py"
    completed = subprocess.run(
        [sys.executable, str(resolver), "--spec-profile", raw_profile],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise ValueError(completed.stderr.strip() or completed.stdout.strip())
    return Path(completed.stdout.strip()).read_text(encoding="utf-8", errors="ignore")


def main() -> int:
    args = parse_args()
    try:
        files = collect_files(args)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if not files:
        print("No files found. Use --file and/or --glob.", file=sys.stderr)
        return 2
    try:
        profile_text = resolve_profile_text(args.spec_profile)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    register_status: Dict[str, str] = {}
    if args.check_register:
        if not args.repo_root:
            print("--check-register requires --repo-root.", file=sys.stderr)
            return 2
        register_status = load_registration_status(Path(args.repo_root).expanduser().resolve())

    results = [
        validate_file(path, register_status, args.check_register, profile_text)
        for path in files
    ]
    warning_count = sum(len(item["warnings"]) for item in results)
    payload = {
        "checked_file_count": len(results),
        "ok_file_count": sum(1 for item in results if item["ok"]),
        "warning_count": warning_count,
        "results": results,
    }

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"checked_files: {payload['checked_file_count']}")
        print(f"ok_files: {payload['ok_file_count']}")
        for item in results:
            status = "OK" if item["ok"] else "FAIL"
            print(f"{status} {item['file']} entries={item['entry_count']}")
            for issue in item["issues"]:
                print(f"  - {issue}")
            for warning in item.get("warnings", []):
                print(
                    "  warning: "
                    f"{warning.get('warning_code', 'WARNING')}: {warning.get('message', warning)}"
                )
                if warning.get("suggestion"):
                    print(f"    suggestion: {warning['suggestion']}")

    return 0 if payload["ok_file_count"] == payload["checked_file_count"] else 1


if __name__ == "__main__":
    sys.exit(main())
