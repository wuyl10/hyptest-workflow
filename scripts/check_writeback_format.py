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
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple


ENTRY_HEADER_RE = re.compile(r"^###\s+P[0-9A-Za-z]")
CASE_NAME_RE = re.compile(r"`(ai_[A-Za-z0-9_]+)`")
REGISTER_RE = re.compile(r"TEST_REGISTER\s*\(\s*(ai_[A-Za-z0-9_]+)\s*\)")
DEPENDENCY_STATUS_RE = re.compile(r"^（依赖[^）]+，未跑Spike）$")

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


@dataclass
class ConditionalFrame:
    deterministic: bool
    active: bool
    branch_taken: bool


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
        "--check-register",
        action="store_true",
        help="Check writeback status text against test_register.c when repo-root is given",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of text")
    return parser.parse_args()


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def strip_inline_comment_markers(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", " ", text)
    return text.split("//", 1)[0].strip()


def parse_pp_boolean(expr: str) -> bool | None:
    normalized = strip_inline_comment_markers(expr)
    if normalized == "0":
        return False
    if normalized == "1":
        return True
    return None


def update_conditional_stack(stripped_code: str, stack: List[ConditionalFrame]) -> None:
    if not stripped_code.startswith("#"):
        return

    directive_line = stripped_code[1:].strip()
    if not directive_line:
        return

    parts = directive_line.split(None, 1)
    directive = parts[0]
    expr = parts[1] if len(parts) > 1 else ""

    if directive == "if":
        parsed = parse_pp_boolean(expr)
        if parsed is None:
            stack.append(ConditionalFrame(deterministic=False, active=True, branch_taken=True))
        else:
            stack.append(
                ConditionalFrame(
                    deterministic=True,
                    active=parsed,
                    branch_taken=parsed,
                )
            )
        return

    if directive in {"ifdef", "ifndef"}:
        stack.append(ConditionalFrame(deterministic=False, active=True, branch_taken=True))
        return

    if directive == "elif":
        if not stack:
            return
        frame = stack[-1]
        if not frame.deterministic:
            return
        parsed = parse_pp_boolean(expr)
        if frame.branch_taken:
            frame.active = False
            return
        if parsed is None:
            frame.active = True
            frame.branch_taken = True
            return
        frame.active = parsed
        frame.branch_taken = parsed
        return

    if directive == "else":
        if not stack:
            return
        frame = stack[-1]
        if not frame.deterministic:
            return
        frame.active = not frame.branch_taken
        frame.branch_taken = True
        return

    if directive == "endif" and stack:
        stack.pop()


def split_code_and_comment_text(line: str, in_block_comment: bool) -> Tuple[str, str, bool]:
    code_parts: List[str] = []
    comment_parts: List[str] = []
    index = 0

    while index < len(line):
        if in_block_comment:
            end = line.find("*/", index)
            if end == -1:
                comment_parts.append(line[index:])
                return "".join(code_parts), "".join(comment_parts), True
            comment_parts.append(line[index : end + 2])
            index = end + 2
            in_block_comment = False
            continue

        if line.startswith("//", index):
            comment_parts.append(line[index:])
            break

        if line.startswith("/*", index):
            end = line.find("*/", index + 2)
            if end == -1:
                comment_parts.append(line[index:])
                return "".join(code_parts), "".join(comment_parts), True
            comment_parts.append(line[index : end + 2])
            index = end + 2
            continue

        code_parts.append(line[index])
        index += 1

    return "".join(code_parts), "".join(comment_parts), in_block_comment


def is_code_active(stack: List[ConditionalFrame]) -> bool:
    return all(frame.active for frame in stack)


def record_status(status: Dict[str, str], case_name: str, value: str) -> None:
    existing = status.get(case_name)
    if existing == "enabled":
        return
    if value == "enabled" or existing is None:
        status[case_name] = value


def load_registration_status(repo_root: Path) -> Dict[str, str]:
    register_path = repo_root / "test_register.c"
    status: Dict[str, str] = {}
    if not register_path.is_file():
        return status

    in_block_comment = False
    conditional_stack: List[ConditionalFrame] = []

    for line in read_text(register_path).splitlines():
        code_text, comment_text, in_block_comment = split_code_and_comment_text(
            line, in_block_comment
        )

        stripped_code = code_text.strip()
        if stripped_code.startswith("#"):
            update_conditional_stack(stripped_code, conditional_stack)
            continue

        for match in REGISTER_RE.finditer(comment_text):
            record_status(status, match.group(1), "commented")

        line_status = "enabled" if is_code_active(conditional_stack) else "commented"
        for match in REGISTER_RE.finditer(code_text):
            record_status(status, match.group(1), line_status)

    return status


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
) -> List[str]:
    issues: List[str] = []
    if not case_lines:
        return ["`已实现 case` 段为空"]

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

    if not found_case_name and not any("暂无" in line for line in case_lines):
        issues.append("`已实现 case` 段未找到有效 case 名")

    return issues


def validate_entry(
    entry_index: int,
    block: List[str],
    register_status: Dict[str, str],
    check_register: bool,
) -> List[str]:
    issues: List[str] = []
    title = block[0].strip()

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
        issues.extend(
            f"{title}: {issue}"
            for issue in validate_case_lines(
                collect_implemented_case_lines(block, implemented_index),
                register_status,
                check_register,
            )
        )

    if reuse_index is not None:
        if find_section_index(block[reuse_index:], SECTION_ORDER) is None:
            issues.append(f"{title}: 出现 `复用依据` 时缺少 `{SECTION_ORDER}`")
        if find_section_index(block[reuse_index:], SECTION_ASSERT) is None:
            issues.append(f"{title}: 出现 `复用依据` 时缺少 `{SECTION_ASSERT}`")

    return issues


def validate_file(
    path: Path,
    register_status: Dict[str, str],
    check_register: bool,
) -> Dict[str, object]:
    text = read_text(path)
    lines = text.splitlines()
    issues: List[str] = []

    for marker in DISALLOWED_MARKERS:
        if marker in text:
            issues.append(f"命中禁止回填块/字段: {marker}")

    entries = split_entries(lines)
    if not entries:
        issues.append("未找到任何 `###` 测试点条目")
    else:
        for idx, (start, end) in enumerate(entries, start=1):
            block = lines[start:end]
            issues.extend(validate_entry(idx, block, register_status, check_register))

    return {
        "file": str(path),
        "entry_count": len(entries),
        "ok": not issues,
        "issues": issues,
    }


def main() -> int:
    args = parse_args()
    files = collect_files(args)
    if not files:
        print("No files found. Use --file and/or --glob.", file=sys.stderr)
        return 2

    register_status: Dict[str, str] = {}
    if args.check_register:
        if not args.repo_root:
            print("--check-register requires --repo-root.", file=sys.stderr)
            return 2
        register_status = load_registration_status(Path(args.repo_root).expanduser().resolve())

    results = [
        validate_file(path, register_status, args.check_register)
        for path in files
    ]
    payload = {
        "checked_file_count": len(results),
        "ok_file_count": sum(1 for item in results if item["ok"]),
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

    return 0 if payload["ok_file_count"] == payload["checked_file_count"] else 1


if __name__ == "__main__":
    sys.exit(main())
