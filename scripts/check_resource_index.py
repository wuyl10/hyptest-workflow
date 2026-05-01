#!/usr/bin/env python3
"""Check that resource_index.md mentions public scripts and key assets."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from skill_config import manifest_scripts


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parent
RESOURCE_INDEX = SKILL_ROOT / "references/resource_index.md"

KEY_ASSETS = [
    "assets/joint_handoff_contract.json",
    "assets/reason_codes.json",
    "assets/script_manifest.json",
    "assets/triage_handoff_schema.json",
    "references/command_index.md",
    "references/prompt_recipes.md",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check hyptest-workflow resource index coverage.")
    parser.add_argument("--json", action="store_true", help="Emit JSON report.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    text = RESOURCE_INDEX.read_text(encoding="utf-8", errors="ignore")
    required = manifest_scripts(public_only=True) + KEY_ASSETS
    missing = [item for item in required if item not in text]
    payload = {
        "ok": not missing,
        "resource_index": str(RESOURCE_INDEX),
        "required_count": len(required),
        "missing": missing,
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(("PASS" if payload["ok"] else "FAIL") + " resource index")
        for item in missing:
            print(f"  missing: {item}")
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
