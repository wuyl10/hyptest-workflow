#!/usr/bin/env python3
"""Parse test_register.c registration status for writeback checks."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple


REGISTER_RE = re.compile(r"TEST_REGISTER\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*\)")


@dataclass
class ConditionalFrame:
    deterministic: bool
    active: bool
    branch_taken: bool


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
