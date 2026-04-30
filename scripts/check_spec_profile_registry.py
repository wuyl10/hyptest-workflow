#!/usr/bin/env python3
"""Validate references/spec_profiles/index.json."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

GENERIC_DOCS = [
    "SKILL.md",
    "README.md",
    "agents/openai.yaml",
    "references/spec_and_model_limits.md",
    "references/writing_cases.md",
    "references/build_run_debug.md",
    "references/repo_layout.md",
    "references/task_input_schema.md",
    "references/resource_index.md",
    "references/maintainer_guide.md",
]


def skill_root() -> Path:
    return Path(__file__).resolve().parent.parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check spec profile registry.")
    parser.add_argument(
        "--registry",
        help="Override registry JSON path. Defaults to references/spec_profiles/index.json.",
    )
    parser.add_argument(
        "--profile-dir",
        help="Override profile directory for fixture checks. Defaults to references/spec_profiles.",
    )
    parser.add_argument(
        "--policy",
        choices=["registry", "generic-docs", "all"],
        default="registry",
        help=(
            "Validation policy. registry checks index/profile files; generic-docs also "
            "ensures generic docs do not spell out the concrete default profile name."
        ),
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON report.")
    return parser.parse_args()


def check_generic_docs(root: Path, default_profile: str) -> list[str]:
    if not default_profile:
        return []
    issues: list[str] = []
    for rel in GENERIC_DOCS:
        path = root / rel
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if default_profile in text:
            issues.append(
                f"{rel}: concrete default profile `{default_profile}` should stay in "
                "references/spec_profiles/index.json or profile files only"
            )
    return issues


def main() -> int:
    args = parse_args()
    root = skill_root()
    registry_path = Path(args.registry).expanduser().resolve() if args.registry else root / "references/spec_profiles/index.json"
    profile_dir = Path(args.profile_dir).expanduser().resolve() if args.profile_dir else root / "references/spec_profiles"
    registry_base = registry_path.parent.parent.parent if args.registry else root
    issues: list[str] = []
    warnings: list[str] = []

    if not registry_path.is_file():
        print(f"missing registry: {registry_path}", file=sys.stderr)
        return 2

    try:
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"invalid registry JSON: {exc}", file=sys.stderr)
        return 2

    default_profile = str(registry.get("default_profile", "")).strip()
    profiles = registry.get("profiles")
    if not default_profile:
        issues.append("registry missing default_profile")
    if not isinstance(profiles, list) or not profiles:
        issues.append("registry profiles must be a non-empty list")
        profiles = []

    names: set[str] = set()
    registry_md_paths: set[Path] = set()
    for index, row in enumerate(profiles, start=1):
        if not isinstance(row, dict):
            issues.append(f"profiles[{index}] must be an object")
            continue
        name = str(row.get("name", "")).strip()
        rel_path = str(row.get("path", "")).strip()
        status = str(row.get("status", "")).strip()
        if not name:
            issues.append(f"profiles[{index}] missing name")
            continue
        if name in names:
            issues.append(f"duplicate profile name: {name}")
        names.add(name)
        if not rel_path:
            issues.append(f"{name}: missing path")
            continue
        if not rel_path.startswith("references/spec_profiles/") or not rel_path.endswith(".md"):
            issues.append(f"{name}: path should be references/spec_profiles/<name>.md")
        path = (registry_base / rel_path).resolve()
        registry_md_paths.add(path.resolve())
        if not path.is_file():
            issues.append(f"{name}: profile path missing: {rel_path}")
            continue
        if path.stem != name:
            issues.append(f"{name}: profile path stem `{path.stem}` does not match name")
        if status not in {"active", "draft", "template", "deprecated"}:
            warnings.append(f"{name}: unknown status `{status}`")

    if default_profile not in names:
        issues.append(f"default_profile `{default_profile}` is not listed in profiles")

    for path in sorted(profile_dir.glob("*.md")):
        if path.resolve() not in registry_md_paths:
            try:
                rel = path.relative_to(registry_base)
            except ValueError:
                rel = path
            warnings.append(f"profile markdown not listed in registry: {rel}")

    if args.policy in {"generic-docs", "all"} and not args.registry:
        issues.extend(check_generic_docs(root, default_profile))

    payload = {
        "ok": not issues,
        "registry": str(registry_path),
        "policy": args.policy,
        "default_profile": default_profile,
        "profile_count": len(names),
        "issues": issues,
        "warnings": warnings,
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(("PASS" if payload["ok"] else "FAIL") + " spec profile registry")
        for issue in issues:
            print(f"  - {issue}")
        for warning in warnings:
            print(f"  warning: {warning}")
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
