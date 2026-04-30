#!/usr/bin/env python3
"""Markdown section selection helpers for hyptest-workflow scripts."""

from __future__ import annotations

import re
from typing import Dict, List


MARKDOWN_HEADING_RE = re.compile(r"^#{1,6}\s+")


def split_markdown_sections(text: str) -> List[Dict[str, str]]:
    sections: List[Dict[str, str]] = []
    current_lines: List[str] = []
    current_heading = ""

    def flush_current() -> None:
        if not current_lines:
            return
        sections.append(
            {
                "heading": current_heading,
                "text": "\n".join(current_lines),
            }
        )

    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if MARKDOWN_HEADING_RE.match(stripped):
            flush_current()
            current_heading = MARKDOWN_HEADING_RE.sub("", stripped).strip()
            current_lines = [raw_line]
            continue
        current_lines.append(raw_line)

    flush_current()
    return sections


def filter_markdown_sections_by_heading(
    sections: List[Dict[str, str]],
    heading_pattern: str,
) -> List[Dict[str, str]]:
    matcher = re.compile(heading_pattern, re.IGNORECASE)
    return [section for section in sections if matcher.search(section["heading"])]


def pick_markdown_section_by_index(
    sections: List[Dict[str, str]],
    section_index: int,
) -> Dict[str, str]:
    if section_index == 0:
        raise ValueError("--section-index must not be 0")

    index = section_index - 1 if section_index > 0 else len(sections) + section_index
    if index < 0 or index >= len(sections):
        raise IndexError(
            f"--section-index {section_index} is out of range for {len(sections)} matching sections"
        )
    return sections[index]
