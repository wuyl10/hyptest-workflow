#!/usr/bin/env python3
"""Shared helpers for reading hyptest spec profile fenced blocks."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent


def resolve_profile_path(raw_profile: str) -> Path:
    resolver = SCRIPT_DIR / "resolve_spec_profile.py"
    completed = subprocess.run(
        [sys.executable, str(resolver), "--spec-profile", raw_profile],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise FileNotFoundError(completed.stderr.strip() or completed.stdout.strip())
    return Path(completed.stdout.strip()).resolve()


def read_profile_text(raw_profile: str) -> tuple[Path, str]:
    path = resolve_profile_path(raw_profile)
    return path, path.read_text(encoding="utf-8", errors="ignore")


def extract_fenced_block(text: str, info: str) -> str | None:
    pattern = rf"```{re.escape(info)}\s*\n(.*?)\n```"
    match = re.search(pattern, text, flags=re.DOTALL)
    return match.group(1) if match else None


def load_json_block(text: str, info: str) -> list[dict[str, Any]]:
    block = extract_fenced_block(text, info)
    if block is None:
        raise ValueError(f"missing fenced block `{info}`")
    data = json.loads(block)
    if not isinstance(data, list):
        raise ValueError(f"`{info}` must be a JSON list")
    rows: list[dict[str, Any]] = []
    for index, row in enumerate(data, start=1):
        if not isinstance(row, dict):
            raise ValueError(f"`{info}` row {index} must be an object")
        rows.append(row)
    return rows


def parse_int_auto(raw: str) -> int:
    return int(raw.replace("_", ""), 0)


def parse_window(raw: str) -> tuple[int, int] | None:
    parts = raw.split("-", 1)
    if len(parts) != 2:
        return None
    try:
        return parse_int_auto(parts[0]), parse_int_auto(parts[1])
    except ValueError:
        return None


def window_contains(window: str, address: str) -> bool:
    parsed = parse_window(window)
    if parsed is None:
        return False
    start, end = parsed
    value = parse_int_auto(address)
    return start <= value < end
