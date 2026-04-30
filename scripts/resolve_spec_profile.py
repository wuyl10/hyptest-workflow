#!/usr/bin/env python3
"""
Resolve a hyptest spec_profile name or path to an existing markdown file.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from skill_config import default_spec_profile, load_profile_registry


DEFAULT_PROFILE = default_spec_profile()


def skill_root() -> Path:
    return Path(__file__).resolve().parent.parent


def load_registry() -> dict[str, dict[str, object]]:
    try:
        payload = load_profile_registry()
    except json.JSONDecodeError:
        return {}
    profiles = payload.get("profiles")
    if not isinstance(profiles, list):
        return {}
    by_name: dict[str, dict[str, object]] = {}
    for row in profiles:
        if isinstance(row, dict) and row.get("name"):
            by_name[str(row["name"])] = row
    return by_name


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Resolve spec_profile=<name> to references/spec_profiles/<name>.md."
    )
    parser.add_argument(
        "--spec-profile",
        default=DEFAULT_PROFILE,
        help=f"Profile name or markdown path. Defaults to {DEFAULT_PROFILE}.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON instead of a plain path.",
    )
    return parser.parse_args()


def resolve_profile(raw: str) -> tuple[str, Path]:
    root = skill_root()
    value = raw.strip() or DEFAULT_PROFILE
    candidate = Path(value).expanduser()

    if candidate.suffix == ".md" or candidate.is_absolute() or "/" in value:
        if candidate.is_absolute():
            path = candidate.resolve()
        else:
            cwd_path = (Path.cwd() / candidate).resolve()
            skill_path = (root / candidate).resolve()
            path = cwd_path if cwd_path.exists() else skill_path
        profile_name = path.stem
    else:
        profile_name = value
        registry = load_registry()
        registry_row = registry.get(value)
        if registry_row and registry_row.get("path"):
            path = root / str(registry_row["path"])
        else:
            path = root / "references" / "spec_profiles" / f"{value}.md"

    if not path.exists():
        raise FileNotFoundError(
            f"spec_profile '{raw}' resolved to missing file: {path}"
        )
    if not path.is_file():
        raise FileNotFoundError(
            f"spec_profile '{raw}' resolved to non-file path: {path}"
        )
    return profile_name, path


def main() -> int:
    args = parse_args()
    try:
        profile_name, path = resolve_profile(str(args.spec_profile))
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(
            json.dumps(
                {
                    "spec_profile": profile_name,
                    "path": str(path),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
