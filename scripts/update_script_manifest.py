#!/usr/bin/env python3
"""Refresh or check assets/script_manifest.json against scripts/*.py."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from skill_config import SCRIPT_MANIFEST, SKILL_ROOT, load_script_manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Update hyptest-workflow script manifest.")
    parser.add_argument("--check", action="store_true", help="Fail if the manifest is not in sync.")
    parser.add_argument("--write", action="store_true", help="Write the refreshed manifest.")
    parser.add_argument("--json", action="store_true", help="Emit JSON report.")
    return parser.parse_args()


def infer_group(path: str) -> str:
    name = Path(path).name
    if name.startswith("eval_"):
        return "eval"
    if name.startswith("check_"):
        return "check"
    if name in {
        "case_extractor.py",
        "find_similar_cases.py",
        "markdown_sections.py",
        "similar_case_cache.py",
        "similar_case_ranker.py",
        "similar_case_render.py",
        "similar_case_terms.py",
        "term_aliases.py",
    }:
        return "similar-search"
    if "profile" in name:
        return "profile"
    if "lint" in name or "writeback" in name:
        return "case-workflow"
    if name in {
        "clean_generated.py",
        "doctor.py",
        "list_skill_commands.py",
        "self_check.py",
        "skill_summary.py",
        "update_readme_commands.py",
        "update_resource_index.py",
        "update_script_manifest.py",
    }:
        return "maintenance"
    return "workflow"


def scan_scripts() -> list[str]:
    return sorted(
        f"scripts/{path.name}"
        for path in (SKILL_ROOT / "scripts").glob("*.py")
        if path.is_file()
    )


def build_manifest() -> dict[str, object]:
    old = load_script_manifest()
    old_rows = old.get("scripts", [])
    by_path = {
        str(row.get("path", "")).strip(): row
        for row in old_rows
        if isinstance(row, dict) and str(row.get("path", "")).strip()
    }
    rows: list[dict[str, object]] = []
    for rel in scan_scripts():
        old_row = by_path.get(rel, {})
        default_self_check = Path(rel).name.startswith("eval_")
        rows.append(
            {
                "path": rel,
                "group": str(old_row.get("group") or infer_group(rel)),
                "public": bool(old_row.get("public", True)),
                "self_check": bool(old_row.get("self_check", default_self_check)),
            }
        )
    return {
        "version": int(old.get("version", 1)) if isinstance(old, dict) else 1,
        "description": str(
            old.get(
                "description",
                "Machine-readable script inventory for hyptest-workflow consistency checks.",
            )
        ),
        "scripts": rows,
    }


def diff_paths(current: dict[str, object], expected: dict[str, object]) -> dict[str, list[str]]:
    current_rows = current.get("scripts", []) if isinstance(current, dict) else []
    expected_rows = expected.get("scripts", [])
    current_by_path = {
        str(row.get("path", "")).strip(): row
        for row in current_rows
        if isinstance(row, dict) and str(row.get("path", "")).strip()
    }
    expected_by_path = {
        str(row.get("path", "")).strip(): row
        for row in expected_rows
        if isinstance(row, dict) and str(row.get("path", "")).strip()
    }
    missing = sorted(set(expected_by_path) - set(current_by_path))
    extra = sorted(set(current_by_path) - set(expected_by_path))
    changed: list[str] = []
    for rel in sorted(set(current_by_path) & set(expected_by_path)):
        if current_by_path[rel] != expected_by_path[rel]:
            changed.append(rel)
    return {"missing": missing, "extra": extra, "changed": changed}


def write_manifest(payload: dict[str, object]) -> None:
    SCRIPT_MANIFEST.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    args = parse_args()
    current = load_script_manifest()
    expected = build_manifest()
    diff = diff_paths(current, expected)
    ok = not any(diff.values())

    if args.write and not ok:
        write_manifest(expected)
        current = expected
        diff = {"missing": [], "extra": [], "changed": []}
        ok = True

    payload = {
        "ok": ok,
        "manifest": str(SCRIPT_MANIFEST),
        "script_count": len(expected["scripts"]),
        "diff": diff,
        "wrote": bool(args.write),
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(("PASS" if ok else "FAIL") + " script manifest")
        for kind, values in diff.items():
            for value in values:
                print(f"  {kind}: {value}")
        if not ok and not args.write:
            print("  next: python3 $HYPTEST_WORKFLOW_SKILL_HOME/scripts/update_script_manifest.py --write")
    return 0 if ok or not args.check else 1


if __name__ == "__main__":
    raise SystemExit(main())
