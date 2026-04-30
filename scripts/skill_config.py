#!/usr/bin/env python3
"""Shared config helpers for hyptest-workflow scripts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parent
PROFILE_REGISTRY = SKILL_ROOT / "references/spec_profiles/index.json"
SCRIPT_MANIFEST = SKILL_ROOT / "assets/script_manifest.json"
TRIAGE_HANDOFF_SCHEMA = SKILL_ROOT / "assets/triage_handoff_schema.json"
JOINT_HANDOFF_CONTRACT = SKILL_ROOT / "assets/joint_handoff_contract.json"


def load_json_file(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_profile_registry() -> dict[str, Any]:
    if not PROFILE_REGISTRY.is_file():
        raise FileNotFoundError(f"profile registry not found: {PROFILE_REGISTRY}")
    payload = load_json_file(PROFILE_REGISTRY)
    if not isinstance(payload, dict):
        raise ValueError(f"profile registry must be a JSON object: {PROFILE_REGISTRY}")
    return payload


def default_spec_profile() -> str:
    raw = load_profile_registry().get("default_profile")
    value = str(raw).strip()
    if not value:
        raise ValueError(f"profile registry missing default_profile: {PROFILE_REGISTRY}")
    return value


def load_script_manifest() -> dict[str, Any]:
    if not SCRIPT_MANIFEST.is_file():
        return {"scripts": []}
    payload = load_json_file(SCRIPT_MANIFEST)
    if not isinstance(payload, dict):
        return {"scripts": []}
    return payload


def manifest_scripts(*, public_only: bool = False, self_check_only: bool = False) -> list[str]:
    payload = load_script_manifest()
    rows = payload.get("scripts", [])
    if not isinstance(rows, list):
        return []
    rels: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        rel = str(row.get("path", "")).strip()
        if not rel:
            continue
        if public_only and row.get("public") is False:
            continue
        if self_check_only and row.get("self_check") is not True:
            continue
        rels.append(rel)
    return sorted(dict.fromkeys(rels))


def recommended_checks(*, show_resolved_profile: bool = False) -> list[str]:
    profile_arg = (
        f" --spec-profile {default_spec_profile()}" if show_resolved_profile else ""
    )
    return [
        f"python3 scripts/self_check.py --quick{profile_arg}",
        f"python3 scripts/self_check.py --full --repo-root <repo_root>{profile_arg}",
        f"python3 scripts/doctor.py --repo-root <repo_root> --pre-submit --strict{profile_arg}",
    ]


def current_profile_anchor() -> str:
    return f"references/spec_profiles/{default_spec_profile()}.md"
