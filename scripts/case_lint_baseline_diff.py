#!/usr/bin/env python3
"""Compare two check_case_lint baseline files."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Diff two case lint baselines.")
    parser.add_argument("--old", required=True, help="Old baseline JSON.")
    parser.add_argument("--new", required=True, help="New baseline JSON.")
    parser.add_argument("--json", action="store_true", help="Emit JSON report.")
    return parser.parse_args()


def load_keys(path: str) -> set[str]:
    payload = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
    return {str(item) for item in payload.get("issue_keys", [])}


def main() -> int:
    args = parse_args()
    old = load_keys(args.old)
    new = load_keys(args.new)
    added = sorted(new - old)
    removed = sorted(old - new)
    unchanged = len(old & new)
    payload = {
        "ok": not added,
        "old_count": len(old),
        "new_count": len(new),
        "unchanged_count": unchanged,
        "added_count": len(added),
        "removed_count": len(removed),
        "added": added,
        "removed": removed,
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(("PASS" if payload["ok"] else "FAIL") + " case lint baseline diff")
        print(
            f"old={len(old)} new={len(new)} unchanged={unchanged} "
            f"added={len(added)} removed={len(removed)}"
        )
        for item in added[:40]:
            print(f"  + {item}")
        for item in removed[:40]:
            print(f"  - {item}")
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
