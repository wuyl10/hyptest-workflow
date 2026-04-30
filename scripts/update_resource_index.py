#!/usr/bin/env python3
"""Suggest or apply resource_index.md coverage updates."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from check_resource_index import KEY_ASSETS, RESOURCE_INDEX
from skill_config import manifest_scripts


MARKER_BEGIN = "<!-- BEGIN GENERATED RESOURCE COVERAGE -->"
MARKER_END = "<!-- END GENERATED RESOURCE COVERAGE -->"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Update resource_index.md generated coverage block.")
    parser.add_argument("--check", action="store_true", help="Fail if generated coverage block is stale.")
    parser.add_argument("--write", action="store_true", help="Write/update the generated coverage block.")
    parser.add_argument("--suggest", action="store_true", help="Print missing resource bullets.")
    parser.add_argument("--json", action="store_true", help="Emit JSON report.")
    return parser.parse_args()


def required_resources() -> list[str]:
    return sorted(dict.fromkeys(manifest_scripts(public_only=True) + KEY_ASSETS))


def missing_resources(text: str, required: list[str]) -> list[str]:
    return [item for item in required if item not in text]


def generated_block(required: list[str]) -> str:
    lines = [
        MARKER_BEGIN,
        "## Generated Resource Coverage",
        "",
        "该段由 `python3 scripts/update_resource_index.py --write` 维护，只记录必须被索引覆盖的资源路径。",
        "",
    ]
    for rel in required:
        lines.append(f"- `{rel}`")
    lines.append(MARKER_END)
    return "\n".join(lines) + "\n"


def replace_block(text: str, block: str) -> str:
    begin = text.find(MARKER_BEGIN)
    end = text.find(MARKER_END)
    if begin != -1 and end != -1 and begin < end:
        end += len(MARKER_END)
        return text[:begin].rstrip() + "\n\n" + block.rstrip() + "\n" + text[end:].lstrip()
    return text.rstrip() + "\n\n" + block


def main() -> int:
    args = parse_args()
    text = RESOURCE_INDEX.read_text(encoding="utf-8", errors="ignore")
    required = required_resources()
    expected_block = generated_block(required)
    expected_text = replace_block(text, expected_block)
    has_generated_block = MARKER_BEGIN in text or MARKER_END in text
    stale = has_generated_block and text != expected_text
    missing = missing_resources(text, required)

    if args.write and (stale or not has_generated_block):
        RESOURCE_INDEX.write_text(expected_text, encoding="utf-8")
        text = expected_text
        stale = False
        missing = missing_resources(text, required)

    payload = {
        "ok": not stale and not missing,
        "resource_index": str(RESOURCE_INDEX),
        "required_count": len(required),
        "missing": missing,
        "stale_generated_block": stale,
        "wrote": bool(args.write),
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(("PASS" if payload["ok"] else "FAIL") + " resource index generated coverage")
        if args.suggest or missing:
            for item in missing:
                print(f"- `{item}`")
        if stale and not args.write:
            print("next: python3 scripts/update_resource_index.py --write")
    return 0 if payload["ok"] or not args.check else 1


if __name__ == "__main__":
    raise SystemExit(main())
