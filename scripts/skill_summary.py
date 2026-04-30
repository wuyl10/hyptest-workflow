#!/usr/bin/env python3
"""Summarize the hyptest-workflow skill structure and available profiles."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from skill_config import current_profile_anchor, load_script_manifest, recommended_checks


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Summarize hyptest-workflow skill metadata.")
    parser.add_argument("--json", action="store_true", help="Emit JSON report.")
    parser.add_argument(
        "--show-resolved-profile",
        action="store_true",
        help="Expand recommended checks with the registry default --spec-profile value.",
    )
    return parser.parse_args()


def list_rel_files(root: Path, pattern: str) -> list[str]:
    return sorted(str(path.relative_to(SKILL_ROOT)) for path in root.glob(pattern) if path.is_file())


def script_group(name: str) -> str:
    if name.startswith("eval_"):
        return "eval"
    if name.startswith("check_"):
        return "check"
    if name.startswith("similar_case") or name in {"case_extractor.py", "find_similar_cases.py"}:
        return "similar-search"
    if "profile" in name:
        return "profile"
    if "lint" in name or "writeback" in name:
        return "case-workflow"
    if name in {"doctor.py", "self_check.py", "skill_summary.py", "list_skill_commands.py", "update_readme_commands.py", "clean_generated.py"}:
        return "maintenance"
    return "workflow"


def manifest_script_groups() -> dict[str, list[str]]:
    rows = load_script_manifest().get("scripts", [])
    groups: dict[str, list[str]] = {}
    if not isinstance(rows, list):
        return groups
    for row in rows:
        if not isinstance(row, dict):
            continue
        path = str(row.get("path", "")).strip()
        group = str(row.get("group", "workflow")).strip() or "workflow"
        if path:
            groups.setdefault(group, []).append(path)
    return {key: sorted(value) for key, value in sorted(groups.items())}


def count_baseline_issues(path: Path) -> int:
    if not path.is_file():
        return 0
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return 0
    return int(payload.get("issue_count", 0))


def main() -> int:
    args = parse_args()
    references = SKILL_ROOT / "references"
    scripts = SKILL_ROOT / "scripts"
    assets = SKILL_ROOT / "assets"
    profile_dir = references / "spec_profiles"
    eval_dir = assets / "evals"
    script_groups = manifest_script_groups()
    script_files = sorted({Path(path).name for files in script_groups.values() for path in files})

    payload = {
        "skill_root": str(SKILL_ROOT),
        "skill_name": "hyptest-workflow",
        "spec_profiles": list_rel_files(profile_dir, "*.md") if profile_dir.is_dir() else [],
        "reference_count": len(list(references.rglob("*.md"))) if references.is_dir() else 0,
        "public_script_count": len(script_files),
        "script_groups": script_groups,
        "eval_assets": list_rel_files(eval_dir, "*.json") if eval_dir.is_dir() else [],
        "eval_count": len(list(eval_dir.glob("*.json"))) if eval_dir.is_dir() else 0,
        "case_lint_baseline_issue_count": count_baseline_issues(
            assets / "baselines/case_lint_baseline.json"
        ),
        "recommended_checks": recommended_checks(show_resolved_profile=args.show_resolved_profile),
        "recommended_checks_use_registry_default": not args.show_resolved_profile,
        "current_layout_anchor": "references/repo_layout.md",
        "current_profile_anchor": current_profile_anchor(),
    }

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    print(f"skill: {payload['skill_name']}")
    print(f"root: {payload['skill_root']}")
    print(f"profiles: {len(payload['spec_profiles'])}")
    for profile in payload["spec_profiles"]:
        print(f"  - {profile}")
    print(f"references: {payload['reference_count']}")
    print(f"public_scripts: {payload['public_script_count']}")
    print("script_groups:")
    for group, files in sorted(payload["script_groups"].items()):
        print(f"  {group}: {len(files)}")
    print("eval_assets:")
    for fixture in payload["eval_assets"]:
        print(f"  - {fixture}")
    print("recommended_checks:")
    for command in payload["recommended_checks"]:
        print(f"  {command}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
