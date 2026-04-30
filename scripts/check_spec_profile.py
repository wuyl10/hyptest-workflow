#!/usr/bin/env python3
"""
Validate that a hyptest spec profile has the expected structure.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

from skill_config import default_spec_profile


REQUIRED_HEADINGS = [
    "口径优先级",
    "项目范围",
    "PMP 粒度约定",
    "PMA / PBMT / MMIO / cacheability",
    "Official Spike 模型边界",
    "非对齐与异常优先级",
    "分层默认口径",
    "Spike 不一致时",
]

RECOMMENDED_TOKENS = [
    "spike_gate_applicable",
    "default",
    "manual",
    "compile-only",
    "blocked",
]

REQUIRED_PROFILE_FIELDS = [
    "profile:",
    "pmp_granularity:",
    "official_spike_has_tlb_model:",
    "official_spike_has_cache_model:",
    "official_spike_has_pma_csr:",
    "default_spike_gate:",
]

STRICT_PLACEHOLDERS = [
    "<profile_name>",
    "<project_or_core>",
    "<填充>",
    "<写清",
    "- 写清",
]

REQUIRED_JSON_BLOCKS = {
    "hyptest-pma-pbmt-matrix": [
        "id",
        "window",
        "pma",
        "pbmt",
        "memattr_device",
        "allowed",
        "responder_required",
        "spike_gate_applicable",
        "default_decision",
    ],
    "hyptest-mmio-responder-matrix": [
        "id",
        "target",
        "responder_type",
        "memory_like_scratch",
        "default_decision",
    ],
}
PROFILE_BOOL_FIELDS = {
    "official_spike_has_tlb_model",
    "official_spike_has_cache_model",
    "official_spike_has_pma_csr",
    "linknan_mmio_requires_responder",
}
PROFILE_VALUE_ENUMS = {
    "official_spike_has_tlb_model": {"true", "false", "unknown"},
    "official_spike_has_cache_model": {"true", "false", "unknown"},
    "official_spike_has_pma_csr": {"true", "false", "unknown"},
    "linknan_mmio_requires_responder": {"true", "false", "unknown"},
}
PMA_VALUES = {"IO", "MEM", "unknown"}
PBMT_VALUES = {"None", "IO", "NC", "unknown"}
RESPONDER_STATUS_VALUES = {"confirmed", "must_confirm", "none", "unknown", "dram_memory", "memory_if_testbench_maps_it"}
RESPONDER_TYPE_VALUES = {"memory", "register-like", "testbench_dependent", "none", "unknown"}
DECISION_PREFIXES = ("default", "manual", "compile-only", "blocked")
WINDOW_RE = re.compile(r"^0x[0-9a-fA-F]+-0x[0-9a-fA-F]+$")


def script_dir() -> Path:
    return Path(__file__).resolve().parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check required structure for a hyptest spec profile."
    )
    parser.add_argument(
        "--spec-profile",
        default=default_spec_profile(),
        help=f"Profile name or markdown path. Defaults to {default_spec_profile()} from the profile registry.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON report.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail if template placeholder text remains in a real profile.",
    )
    return parser.parse_args()


def resolve_profile(raw: str) -> Path:
    resolver = script_dir() / "resolve_spec_profile.py"
    completed = subprocess.run(
        [sys.executable, str(resolver), "--spec-profile", raw],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise FileNotFoundError(completed.stderr.strip() or completed.stdout.strip())
    return Path(completed.stdout.strip()).resolve()


def check_profile(path: Path, *, strict: bool = False) -> dict[str, object]:
    text = path.read_text(encoding="utf-8")
    missing_headings = [heading for heading in REQUIRED_HEADINGS if not has_heading(text, heading)]
    missing_tokens = [token for token in RECOMMENDED_TOKENS if token not in text]
    missing_profile_fields = [
        field for field in REQUIRED_PROFILE_FIELDS if field not in text
    ] if strict else []
    json_block_report = check_required_json_blocks(text) if strict else {
        "missing_json_blocks": [],
        "json_block_errors": [],
        "json_block_counts": {},
    }
    profile_block_errors = check_profile_metadata(text) if strict else []
    strict_placeholders = [
        placeholder for placeholder in STRICT_PLACEHOLDERS if placeholder in text
    ] if strict else []
    ok = (
        not missing_headings
        and not missing_tokens
        and not missing_profile_fields
        and not json_block_report["missing_json_blocks"]
        and not json_block_report["json_block_errors"]
        and not profile_block_errors
        and not strict_placeholders
    )
    return {
        "ok": ok,
        "path": str(path),
        "missing_headings": missing_headings,
        "missing_tokens": missing_tokens,
        "missing_profile_fields": missing_profile_fields,
        **json_block_report,
        "profile_block_errors": profile_block_errors,
        "strict_placeholders": strict_placeholders,
        "profile": path.stem,
        "headings": [
            heading for heading in REQUIRED_HEADINGS if has_heading(text, heading)
        ],
        "has_reason_code_mapping": has_heading(text, "本 profile 常见 reason_code 映射"),
        "strict": strict,
    }


def has_heading(text: str, heading: str) -> bool:
    escaped = re.escape(heading)
    pattern = rf"^##\s+(?:\d+\.\s+)?{escaped}.*$"
    return re.search(pattern, text, flags=re.MULTILINE) is not None


def extract_fenced_block(text: str, info: str) -> str | None:
    pattern = rf"```{re.escape(info)}\s*\n(.*?)\n```"
    match = re.search(pattern, text, flags=re.DOTALL)
    return match.group(1) if match else None


def parse_profile_metadata(text: str) -> dict[str, str]:
    block = extract_fenced_block(text, "hyptest-profile")
    if block is None:
        return {}
    values: dict[str, str] = {}
    for raw_line in block.splitlines():
        if ":" not in raw_line:
            continue
        key, value = raw_line.split(":", 1)
        values[key.strip()] = value.strip()
    return values


def decision_value_ok(value: object) -> bool:
    text = str(value).strip()
    return bool(text) and text.startswith(DECISION_PREFIXES)


def bool_value(value: object) -> bool:
    return isinstance(value, bool)


def check_profile_metadata(text: str) -> list[str]:
    values = parse_profile_metadata(text)
    errors: list[str] = []
    if not values:
        return ["hyptest-profile: missing fenced metadata block"]
    for field in REQUIRED_PROFILE_FIELDS:
        key = field.rstrip(":")
        if key not in values:
            errors.append(f"hyptest-profile: missing field `{key}`")
    for key, allowed in PROFILE_VALUE_ENUMS.items():
        if key in values and values[key] not in allowed:
            errors.append(f"hyptest-profile: `{key}` must be one of {sorted(allowed)}")
    for key in PROFILE_BOOL_FIELDS:
        if key in values and values[key] == "":
            errors.append(f"hyptest-profile: `{key}` must not be empty")
    return errors


def check_required_json_blocks(text: str) -> dict[str, object]:
    missing: list[str] = []
    errors: list[str] = []
    counts: dict[str, int] = {}

    for info, required_fields in REQUIRED_JSON_BLOCKS.items():
        block = extract_fenced_block(text, info)
        if block is None:
            missing.append(info)
            continue
        try:
            rows = json.loads(block)
        except json.JSONDecodeError as exc:
            errors.append(f"{info}: invalid JSON: {exc}")
            continue
        if not isinstance(rows, list) or not rows:
            errors.append(f"{info}: expected a non-empty JSON list")
            continue
        counts[info] = len(rows)
        for index, row in enumerate(rows, start=1):
            if not isinstance(row, dict):
                errors.append(f"{info}[{index}]: expected object")
                continue
            for field in required_fields:
                if field not in row:
                    errors.append(f"{info}[{index}]: missing field `{field}`")
            errors.extend(check_json_row_schema(info, index, row))

    return {
        "missing_json_blocks": missing,
        "json_block_errors": errors,
        "json_block_counts": counts,
}


def check_json_row_schema(info: str, index: int, row: dict[str, object]) -> list[str]:
    errors: list[str] = []
    prefix = f"{info}[{index}]"
    if "id" in row and not str(row["id"]).strip():
        errors.append(f"{prefix}: id must not be empty")
    if "default_decision" in row and not decision_value_ok(row["default_decision"]):
        errors.append(
            f"{prefix}: default_decision should start with one of {', '.join(DECISION_PREFIXES)}"
        )

    if info == "hyptest-pma-pbmt-matrix":
        window = str(row.get("window", "")).strip()
        if window and not WINDOW_RE.fullmatch(window):
            errors.append(f"{prefix}: window should look like 0xSTART-0xEND")
        if row.get("pma") not in PMA_VALUES:
            errors.append(f"{prefix}: pma must be one of {sorted(PMA_VALUES)}")
        if row.get("pbmt") not in PBMT_VALUES:
            errors.append(f"{prefix}: pbmt must be one of {sorted(PBMT_VALUES)}")
        for field in ["memattr_device", "allowed", "responder_required", "spike_gate_applicable"]:
            if field in row and not bool_value(row[field]):
                errors.append(f"{prefix}: {field} must be boolean")
        if "responder_status" in row and row["responder_status"] not in RESPONDER_STATUS_VALUES:
            errors.append(
                f"{prefix}: responder_status must be one of {sorted(RESPONDER_STATUS_VALUES)}"
            )
        if row.get("memattr_device") is True and row.get("responder_required") is not True:
            errors.append(f"{prefix}: Device rows should set responder_required=true")

    if info == "hyptest-mmio-responder-matrix":
        if "responder_type" in row and row["responder_type"] not in RESPONDER_TYPE_VALUES:
            errors.append(
                f"{prefix}: responder_type must be one of {sorted(RESPONDER_TYPE_VALUES)}"
            )
        if "memory_like_scratch" in row and not bool_value(row["memory_like_scratch"]):
            errors.append(f"{prefix}: memory_like_scratch must be boolean")
        notes = str(row.get("notes", "")).strip()
        if "notes" in row and not notes:
            errors.append(f"{prefix}: notes must not be empty")

    return errors


def main() -> int:
    args = parse_args()
    try:
        path = resolve_profile(str(args.spec_profile))
    except FileNotFoundError as exc:
        payload = {
            "ok": False,
            "path": None,
            "error": str(exc),
            "missing_headings": REQUIRED_HEADINGS,
            "missing_tokens": RECOMMENDED_TOKENS,
        }
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(f"FAIL spec profile: {exc}")
        return 2

    report = check_profile(path, strict=args.strict)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif report["ok"]:
        print(f"PASS spec profile: {path}")
    else:
        print(f"FAIL spec profile: {path}")
        for heading in report["missing_headings"]:
            print(f"  missing heading: {heading}")
        for token in report["missing_tokens"]:
            print(f"  missing token: {token}")
        for field in report.get("missing_profile_fields", []):
            print(f"  missing profile field: {field}")
        for block in report.get("missing_json_blocks", []):
            print(f"  missing JSON block: {block}")
        for error in report.get("json_block_errors", []):
            print(f"  JSON block error: {error}")
        for placeholder in report.get("strict_placeholders", []):
            print(f"  unresolved template placeholder: {placeholder}")

    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
