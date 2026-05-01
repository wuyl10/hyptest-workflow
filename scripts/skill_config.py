#!/usr/bin/env python3
"""Shared config helpers for hyptest-workflow scripts."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parent
PROFILE_REGISTRY = SKILL_ROOT / "references/spec_profiles/index.json"
SCRIPT_MANIFEST = SKILL_ROOT / "assets/script_manifest.json"
TRIAGE_HANDOFF_SCHEMA = SKILL_ROOT / "assets/triage_handoff_schema.json"
JOINT_HANDOFF_CONTRACT = SKILL_ROOT / "assets/joint_handoff_contract.json"
CANONICAL_ENV_NAMES = (
    "SPIKE_BIN",
    "LINKNAN_HOME",
    "DIFFTEST_REF_SO",
    "CROSS_COMPILE",
    "TMPDIR",
)
HYPTEST_ENV_ALIASES = {
    "HYPTEST_SPIKE_BIN": "SPIKE_BIN",
    "HYPTEST_LINKNAN_HOME": "LINKNAN_HOME",
    "HYPTEST_DIFFTEST_REF_SO": "DIFFTEST_REF_SO",
    "HYPTEST_CROSS_COMPILE": "CROSS_COMPILE",
    "HYPTEST_TMPDIR": "TMPDIR",
}
CANONICAL_TO_HYPTEST_ENV = {target: alias for alias, target in HYPTEST_ENV_ALIASES.items()}
ALLOWED_ENV_OVERRIDE_NAMES = set(HYPTEST_ENV_ALIASES)
# Public prompt/request fields use HYPTEST_* names. Canonical names are only
# emitted to child hyptest repo commands by runtime_env_overrides().
PROMPT_ENV_FIELD_NAMES = tuple(HYPTEST_ENV_ALIASES)
PROMPT_FIELD_HINTS = {
    "HYPTEST_HOME": "HYPTEST_HOME: <riscv-hyp-tests-nhv5.1 repo root>",
    "CROSS_COMPILE": "HYPTEST_CROSS_COMPILE: <RISC-V toolchain prefix>",
    "HYPTEST_CROSS_COMPILE": "HYPTEST_CROSS_COMPILE: <RISC-V toolchain prefix>",
    "SPIKE_BIN": "HYPTEST_SPIKE_BIN: <community/upstream Spike executable>",
    "HYPTEST_SPIKE_BIN": "HYPTEST_SPIKE_BIN: <community/upstream Spike executable>",
    "LINKNAN_HOME": "HYPTEST_LINKNAN_HOME: <LinkNan repo root>",
    "HYPTEST_LINKNAN_HOME": "HYPTEST_LINKNAN_HOME: <LinkNan repo root>",
    "NANHU_SOURCE": "initialize HYPTEST_LINKNAN_HOME/dependencies/nanhu/src/main",
    "DIFFTEST_REF_SO": "HYPTEST_DIFFTEST_REF_SO: <riscv64-spike-so path>",
    "HYPTEST_DIFFTEST_REF_SO": "HYPTEST_DIFFTEST_REF_SO: <riscv64-spike-so path>",
    "TMPDIR": "HYPTEST_TMPDIR: <temporary directory>",
    "HYPTEST_TMPDIR": "HYPTEST_TMPDIR: <temporary directory>",
}
ENV_EXPORT_HINTS = {
    "HYPTEST_HOME": "export HYPTEST_HOME=<riscv-hyp-tests-nhv5.1 repo root>",
    "CROSS_COMPILE": "export HYPTEST_CROSS_COMPILE=<RISC-V toolchain prefix>",
    "HYPTEST_CROSS_COMPILE": "export HYPTEST_CROSS_COMPILE=<RISC-V toolchain prefix>",
    "SPIKE_BIN": "export HYPTEST_SPIKE_BIN=<community/upstream Spike executable>",
    "HYPTEST_SPIKE_BIN": "export HYPTEST_SPIKE_BIN=<community/upstream Spike executable>",
    "LINKNAN_HOME": "export HYPTEST_LINKNAN_HOME=<LinkNan repo root>",
    "HYPTEST_LINKNAN_HOME": "export HYPTEST_LINKNAN_HOME=<LinkNan repo root>",
    "NANHU_SOURCE": "git -C \"$HYPTEST_LINKNAN_HOME\" submodule update --init dependencies/nanhu",
    "DIFFTEST_REF_SO": "export HYPTEST_DIFFTEST_REF_SO=<riscv64-spike-so path>",
    "HYPTEST_DIFFTEST_REF_SO": "export HYPTEST_DIFFTEST_REF_SO=<riscv64-spike-so path>",
    "TMPDIR": "export HYPTEST_TMPDIR=<temporary directory>",
    "HYPTEST_TMPDIR": "export HYPTEST_TMPDIR=<temporary directory>",
}
PLACEHOLDER_VALUES = {
    "not needed",
    "not-needed",
    "not_needed",
    "unused",
    "none",
    "n/a",
    "na",
    "不需要",
    "不用",
    "无需",
}
ANGLE_PLACEHOLDER_PATTERN = re.compile(r"<[^<>\n]+>")
INFER_VALUES = {
    "infer",
    "inferred",
    "infer from linknan",
    "infer from linknan submodule",
    "auto",
    "auto infer",
    "auto-infer",
    "自动推导",
    "从linknan推导",
    "从 linknan 推导",
}
ENV_OVERRIDE_PATTERN = re.compile(r"^[A-Z_][A-Z0-9_]*$")
UNRESOLVED_ENV_VAR_PATTERN = re.compile(
    r"(?<!\\)(?:\$(?P<braced>\{[A-Za-z_][A-Za-z0-9_]*\})|\$(?P<plain>[A-Za-z_][A-Za-z0-9_]*))"
)


def load_json_file(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def expand_path(value: str | Path) -> Path:
    """Expand shell-style environment variables and ~ in user-supplied paths."""
    return Path(os.path.expandvars(str(value))).expanduser()


def unresolved_env_vars(value: str | Path) -> list[str]:
    """Return shell-style environment variables that remain after expansion."""
    raw = str(value)
    expanded = os.path.expandvars(raw)
    names: list[str] = []
    for match in UNRESOLVED_ENV_VAR_PATTERN.finditer(expanded):
        token = match.group("braced") or match.group("plain") or ""
        name = token.strip("{}")
        if name:
            names.append(name)
    return sorted(dict.fromkeys(names))


def resolve_path(value: str | Path) -> Path:
    """Expand a user-supplied path and resolve it to an absolute path."""
    return expand_path(value).resolve()


def is_placeholder_value(value: str) -> bool:
    stripped = value.strip()
    return stripped.lower() in PLACEHOLDER_VALUES or bool(ANGLE_PLACEHOLDER_PATTERN.search(stripped))


def is_infer_value(value: str) -> bool:
    return value.strip().lower() in INFER_VALUES


def prompt_field_hint(name: str) -> str:
    return PROMPT_FIELD_HINTS.get(name, f"{name}: <path>")


def env_export_hint(name: str) -> str:
    return ENV_EXPORT_HINTS.get(name, f"export {name}=<path>")


def canonical_env_name(name: str) -> str:
    return HYPTEST_ENV_ALIASES.get(name, name)


def hyptest_env_name(name: str) -> str:
    return CANONICAL_TO_HYPTEST_ENV.get(name, name)


def process_env_value(name: str) -> str:
    canonical = canonical_env_name(name)
    alias = hyptest_env_name(canonical)
    value = os.environ.get(alias, "").strip()
    if unresolved_env_vars(value):
        return ""
    return value


def prompt_env_overrides(overrides: dict[str, object]) -> dict[str, str]:
    """Extract environment override fields from a prompt/request object.

    Placeholder values are omitted. Values are expanded with the current
    process environment, but unresolved variables are left visible so callers
    can report them clearly.
    """
    env: dict[str, str] = {}
    for raw_key in PROMPT_ENV_FIELD_NAMES:
        value = overrides.get(raw_key)
        if value is None or not str(value).strip():
            continue
        stripped = str(value).strip()
        if is_placeholder_value(stripped) or is_infer_value(stripped):
            continue
        key = canonical_env_name(raw_key)
        env[key] = os.path.expandvars(stripped)
    return env


def visible_env_value(name: str, prompt_env: dict[str, str] | None = None) -> str:
    """Return a prompt override or process env value only when fully expanded."""
    prompt_env = prompt_env or {}
    canonical = canonical_env_name(name)
    value = prompt_env.get(canonical)
    if value is not None:
        stripped = value.strip()
        if unresolved_env_vars(stripped):
            return ""
        return stripped
    return process_env_value(canonical)


def parse_env_overrides(items: list[str] | None) -> dict[str, str]:
    """Parse repeated KEY=VALUE environment override CLI arguments."""
    overrides: dict[str, str] = {}
    for item in items or []:
        if "=" not in item:
            raise ValueError(f"env override must be KEY=VALUE: {item}")
        raw_name, value = item.split("=", 1)
        raw_name = raw_name.strip()
        if not ENV_OVERRIDE_PATTERN.match(raw_name):
            raise ValueError(f"invalid env override name: {raw_name}")
        if raw_name not in ALLOWED_ENV_OVERRIDE_NAMES:
            allowed = ", ".join(sorted(ALLOWED_ENV_OVERRIDE_NAMES))
            raise ValueError(f"unsupported env override {raw_name}; allowed: {allowed}")
        name = canonical_env_name(raw_name)
        expanded = os.path.expandvars(value.strip())
        unresolved = unresolved_env_vars(expanded)
        if unresolved:
            missing = ", ".join(unresolved)
            raise ValueError(
                f"env override {hyptest_env_name(name)} contains unset variable(s): {missing}"
            )
        overrides[name] = expanded
    return overrides


def apply_env_overrides(items: list[str] | None) -> dict[str, str]:
    """Apply CLI environment overrides to this process and return them."""
    overrides = parse_env_overrides(items)
    for name, value in overrides.items():
        os.environ[name] = value
        alias = hyptest_env_name(name)
        if alias != name:
            os.environ[alias] = value
    return overrides


def env_override_args(overrides: dict[str, str]) -> list[str]:
    """Render overrides as repeated --env KEY=VALUE CLI args."""
    args: list[str] = []
    for name, value in sorted(overrides.items()):
        args.extend(["--env", f"{hyptest_env_name(name)}={value}"])
    return args


def runtime_env_overrides(overrides: dict[str, str] | None) -> dict[str, str]:
    """Return env vars suitable for child hyptest commands.

    Public prompt fields use HYPTEST_* names to avoid colliding with other
    projects. The hyptest repo scripts still expect canonical names such as
    SPIKE_BIN, so child processes receive both names.
    """
    env: dict[str, str] = {}
    for raw_name, value in (overrides or {}).items():
        canonical = canonical_env_name(raw_name)
        alias = hyptest_env_name(canonical)
        env[canonical] = value
        if alias != canonical:
            env[alias] = value
    for canonical in CANONICAL_ENV_NAMES:
        alias = hyptest_env_name(canonical)
        if canonical in env or alias in env:
            value = env.get(canonical) or env.get(alias) or ""
        elif alias in os.environ:
            value = os.environ[alias]
        else:
            continue
        env[canonical] = value
        if alias != canonical:
            env[alias] = value
    return env


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
        f"python3 scripts/self_check.py --full --repo-root \"$HYPTEST_HOME\"{profile_arg}",
        f"python3 scripts/doctor.py --repo-root \"$HYPTEST_HOME\" --pre-submit --strict{profile_arg}",
    ]


def current_profile_anchor() -> str:
    return f"references/spec_profiles/{default_spec_profile()}.md"
