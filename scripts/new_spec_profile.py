#!/usr/bin/env python3
"""Create a new spec profile from the bundled template."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parent
PROFILE_DIR = SKILL_ROOT / "references/spec_profiles"
REGISTRY = PROFILE_DIR / "index.json"
TEMPLATE = PROFILE_DIR / "template.md"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a hyptest spec profile skeleton.")
    parser.add_argument("--name", required=True, help="Profile name, e.g. project_core_name.")
    parser.add_argument("--title", help="Human-readable title. Defaults to the profile name.")
    parser.add_argument(
        "--description",
        help="Description to add to references/spec_profiles/index.json.",
    )
    parser.add_argument(
        "--status",
        default="draft",
        choices=["active", "draft", "template", "deprecated"],
        help="Registry status for the new profile.",
    )
    parser.add_argument("--force", action="store_true", help="Overwrite an existing profile file.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Check conflicts and print the planned profile/registry changes without writing files.",
    )
    parser.add_argument(
        "--check-registry-only",
        action="store_true",
        help="Only check whether --name is consistently registered; do not create or update files.",
    )
    parser.add_argument(
        "--update-registry",
        action="store_true",
        help="Add/update this profile in references/spec_profiles/index.json.",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON report.")
    return parser.parse_args()


def valid_profile_name(name: str) -> bool:
    return bool(re.fullmatch(r"[a-z0-9][a-z0-9_]*", name))


def load_registry() -> dict[str, object]:
    return json.loads(REGISTRY.read_text(encoding="utf-8"))


def find_registry_row(registry: dict[str, object], name: str) -> dict[str, object] | None:
    profiles = registry.get("profiles", [])
    if not isinstance(profiles, list):
        return None
    for item in profiles:
        if isinstance(item, dict) and item.get("name") == name:
            return item
    return None


def check_registry_row(args: argparse.Namespace) -> tuple[bool, list[str], dict[str, object]]:
    registry = load_registry()
    row = find_registry_row(registry, args.name)
    issues: list[str] = []
    details: dict[str, object] = {
        "registry": str(REGISTRY),
        "profile": args.name,
        "registered": row is not None,
    }
    if row is None:
        issues.append(f"profile `{args.name}` is not listed in {REGISTRY}")
        return False, issues, details

    rel_path = str(row.get("path", "")).strip()
    details["path"] = rel_path or None
    if not rel_path:
        issues.append(f"profile `{args.name}` registry row is missing path")
        return False, issues, details
    if not rel_path.startswith("references/spec_profiles/") or not rel_path.endswith(".md"):
        issues.append(f"profile `{args.name}` path should be references/spec_profiles/<name>.md")
    profile_path = (SKILL_ROOT / rel_path).resolve()
    details["path_exists"] = profile_path.is_file()
    if profile_path.stem != args.name:
        issues.append(
            f"profile `{args.name}` registry path stem `{profile_path.stem}` does not match name"
        )
    if not profile_path.is_file():
        issues.append(f"profile `{args.name}` path is missing: {rel_path}")
    return not issues, issues, details


def write_registry(registry: dict[str, object], args: argparse.Namespace, path: str) -> None:
    profiles = registry.setdefault("profiles", [])
    if not isinstance(profiles, list):
        raise ValueError("registry profiles must be a list")
    description = args.description or f"{args.title or args.name} hyptest profile."
    row = {
        "name": args.name,
        "path": path,
        "description": description,
        "status": args.status,
    }
    for index, item in enumerate(profiles):
        if isinstance(item, dict) and item.get("name") == args.name:
            profiles[index] = row
            break
    else:
        profiles.append(row)
    REGISTRY.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def render_template(args: argparse.Namespace) -> str:
    text = TEMPLATE.read_text(encoding="utf-8")
    title = args.title or args.name
    replacements = {
        "<profile_name>": args.name,
        "<project_or_core>": title,
        "<写清 ISA/privilege/extension 默认范围>": "TODO: fill ISA/privilege/extension scope",
        "<写清 PMP 构造粒度>": "TODO: fill PMP granularity",
        "<true|false|unknown>": "unknown",
        "<写清哪些场景可作为 default Spike gate>": "TODO: fill Spike gate scope",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


def main() -> int:
    args = parse_args()
    if not valid_profile_name(args.name):
        print("profile name must match [a-z0-9][a-z0-9_]*", file=sys.stderr)
        return 2
    if args.check_registry_only:
        ok, issues, details = check_registry_row(args)
        payload = {
            "ok": ok,
            "mode": "check-registry-only",
            "issues": issues,
            **details,
        }
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(("PASS" if ok else "FAIL") + f" registry row for {args.name}")
            for issue in issues:
                print(f"  - {issue}")
        return 0 if ok else 1

    if not TEMPLATE.is_file():
        print(f"template not found: {TEMPLATE}", file=sys.stderr)
        return 2

    target = PROFILE_DIR / f"{args.name}.md"
    registry = load_registry()
    row = find_registry_row(registry, args.name)
    rel_target = str(target.relative_to(SKILL_ROOT))
    issues: list[str] = []
    if target.exists() and not args.force:
        issues.append(f"profile already exists: {target}")
    if args.update_registry and row is not None and not args.force:
        issues.append(f"profile already listed in registry: {args.name}; use --force to update it")
    if row is not None:
        row_path = str(row.get("path", "")).strip()
        if row_path and row_path != rel_target:
            issues.append(f"profile registry path `{row_path}` does not match target `{rel_target}`")

    dry_payload = {
        "ok": not issues,
        "profile": args.name,
        "path": str(target),
        "path_exists": target.exists(),
        "registry": str(REGISTRY),
        "registry_row_exists": row is not None,
        "would_write_profile": not args.dry_run and not issues,
        "would_update_registry": bool(args.update_registry and not args.dry_run and not issues),
        "issues": issues,
        "next_checks": [
            f"python3 scripts/check_spec_profile.py --spec-profile {args.name} --strict",
            "python3 scripts/check_spec_profile_registry.py --policy all",
        ],
    }
    if args.dry_run or issues:
        if args.json:
            print(json.dumps(dry_payload, ensure_ascii=False, indent=2))
        else:
            print(("PASS" if dry_payload["ok"] else "FAIL") + f" dry-run profile {args.name}")
            print(f"target: {target}")
            if args.update_registry:
                print(f"registry: {REGISTRY}")
            for issue in issues:
                print(f"  - {issue}")
            if not issues:
                print("no files written")
        return 0 if dry_payload["ok"] else 1

    target.write_text(render_template(args), encoding="utf-8")
    registry_updated = False
    if args.update_registry:
        write_registry(registry, args, str(target.relative_to(SKILL_ROOT)))
        registry_updated = True

    payload = {
        "ok": True,
        "profile": args.name,
        "path": str(target),
        "registry_updated": registry_updated,
        "next_checks": [
            f"python3 scripts/check_spec_profile.py --spec-profile {args.name} --strict",
            "python3 scripts/check_spec_profile_registry.py --policy all",
        ],
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"created: {target}")
        if registry_updated:
            print(f"updated: {REGISTRY}")
        for command in payload["next_checks"]:
            print(f"next: {command}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
