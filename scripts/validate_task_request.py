#!/usr/bin/env python3
"""Validate a hyptest-workflow task request before editing or running cases."""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

from skill_config import (
    canonical_env_name,
    default_spec_profile,
    env_export_hint,
    env_override_args,
    expand_path,
    hyptest_env_name,
    is_placeholder_value,
    parse_env_overrides,
    prompt_env_overrides,
    prompt_field_hint,
    resolve_path,
    unresolved_env_vars,
    visible_env_value,
)


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parent
VALID_PLATFORMS = {"spike", "linknan"}
SPIKE_RUN_TASK_MODES = {
    "new-case-only",
    "supplement-existing-point",
    "fix-case",
    "run-only",
}
TASK_MODES = {
    "new-case-only",
    "preflight-only",
    "supplement-existing-point",
    "fix-case",
    "run-only",
    "triage-only",
    "writeback-only",
}
WAVEFORM_HANDOFF_FIELDS = (
    "waveform_path",
    "rtl_root",
    "top_module",
    "debug_target",
    "time_window",
    "expected_behavior",
    "observed_behavior",
    "waveform_report",
)
WAVEFORM_HANDOFF_PATH_FIELDS = {
    "waveform_path",
    "rtl_root",
    "waveform_report",
}
WAVEFORM_HANDOFF_CLI_FLAGS = {
    "waveform_path": "--waveform-path",
    "rtl_root": "--rtl-root",
    "top_module": "--top-module",
    "debug_target": "--debug-target",
    "time_window": "--time-window",
    "expected_behavior": "--expected-behavior",
    "observed_behavior": "--observed-behavior",
    "suggested_waveform_report": "--waveform-report",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate hyptest-workflow task inputs.")
    parser.add_argument("--request-json", help="Path to a JSON request object.")
    parser.add_argument("--request-md", help="Path to a Markdown/text request with key: value lines.")
    parser.add_argument(
        "--repo-root",
        help="Path to hyptest repo root. In prompts this is written as HYPTEST_HOME.",
    )
    parser.add_argument("--test-point-file", help="Path to test_point markdown file.")
    parser.add_argument("--platform", help="Target hyptest platform.")
    default_profile = default_spec_profile()
    parser.add_argument(
        "--spec-profile",
        help=f"Spec profile name/path. Defaults to {default_profile} from the profile registry.",
    )
    parser.add_argument("--task-mode", choices=sorted(TASK_MODES), help="Requested task mode.")
    parser.add_argument("--case-name", help="Case name for fix/run/triage tasks.")
    parser.add_argument("--new-case-count", help="New case count or range, e.g. 1 or 1-3.")
    parser.add_argument("--coverage-scope", choices=["file", "repo"], help="Coverage scope.")
    parser.add_argument(
        "--failure-log",
        help="Path to failure log for triage-only or failure-driven tasks.",
    )
    parser.add_argument("--waveform-path", help="Optional FSDB/VCD/FST path to pass through triage handoff.")
    parser.add_argument("--rtl-root", help="Optional RTL/source root to pass through triage handoff.")
    parser.add_argument("--top-module", help="Optional waveform top module for downstream triage.")
    parser.add_argument("--debug-target", help="Optional first-bad-cycle/protocol/signal question.")
    parser.add_argument("--time-window", help="Optional known failing time window or cycle range.")
    parser.add_argument("--expected-behavior", help="Optional expected behavior for waveform-aware triage.")
    parser.add_argument("--observed-behavior", help="Optional observed behavior for waveform-aware triage.")
    parser.add_argument("--waveform-report", help="Optional existing or suggested waveform-debug report.md path.")
    parser.add_argument(
        "--env",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help=(
            "Environment override for this request validation, e.g. "
            "--env HYPTEST_SPIKE_BIN=/path/to/spike. Can be repeated."
        ),
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON report.")
    return parser.parse_args()


def parse_request_md(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    full_text = path.read_text(encoding="utf-8", errors="ignore")
    key_map = {
        "hyptest_home": "HYPTEST_HOME",
        "hyptest-home": "HYPTEST_HOME",
        "HYPTEST_HOME".lower(): "HYPTEST_HOME",
        "test_point_file": "test_point_file",
        "test-point-file": "test_point_file",
        "platform": "platform",
        "spec_profile": "spec_profile",
        "spec-profile": "spec_profile",
        "task_mode": "task_mode",
        "task-mode": "task_mode",
        "case_name": "case_name",
        "case-name": "case_name",
        "new_case_count": "new_case_count",
        "new-case-count": "new_case_count",
        "coverage_scope": "coverage_scope",
        "coverage-scope": "coverage_scope",
        "failure_log": "failure_log",
        "failure-log": "failure_log",
        "waveform_path": "waveform_path",
        "waveform-path": "waveform_path",
        "rtl_root": "rtl_root",
        "rtl-root": "rtl_root",
        "top_module": "top_module",
        "top-module": "top_module",
        "debug_target": "debug_target",
        "debug-target": "debug_target",
        "time_window": "time_window",
        "time-window": "time_window",
        "expected_behavior": "expected_behavior",
        "expected-behavior": "expected_behavior",
        "observed_behavior": "observed_behavior",
        "observed-behavior": "observed_behavior",
        "waveform_report": "waveform_report",
        "waveform-report": "waveform_report",
        "hyptest_spike_bin": "HYPTEST_SPIKE_BIN",
        "hyptest-spike-bin": "HYPTEST_SPIKE_BIN",
        "hyptest_linknan_home": "HYPTEST_LINKNAN_HOME",
        "hyptest-linknan-home": "HYPTEST_LINKNAN_HOME",
        "hyptest_difftest_ref_so": "HYPTEST_DIFFTEST_REF_SO",
        "hyptest-difftest-ref-so": "HYPTEST_DIFFTEST_REF_SO",
        "hyptest_difftest_ref": "HYPTEST_DIFFTEST_REF_SO",
        "hyptest-difftest-ref": "HYPTEST_DIFFTEST_REF_SO",
        "hyptest_difftest_so": "HYPTEST_DIFFTEST_REF_SO",
        "hyptest-difftest-so": "HYPTEST_DIFFTEST_REF_SO",
        "hyptest_tmpdir": "HYPTEST_TMPDIR",
        "hyptest_tmp_dir": "HYPTEST_TMPDIR",
        "hyptest-tmp-dir": "HYPTEST_TMPDIR",
        "hyptest_cross_compile": "HYPTEST_CROSS_COMPILE",
        "hyptest-cross-compile": "HYPTEST_CROSS_COMPILE",
    }
    for raw_line in full_text.splitlines():
        line = re.sub(r"^\s*[-*]\s+", "", raw_line.strip())
        match = re.match(r"([A-Za-z_][A-Za-z0-9_-]*)\s*[:=]\s*(.+)$", line)
        if not match:
            continue
        key = key_map.get(match.group(1).strip().lower())
        if key:
            values[key] = match.group(2).strip().strip("`")
    return values


def load_request_overrides(args: argparse.Namespace) -> dict[str, object]:
    if args.request_json and args.request_md:
        raise ValueError("use only one of --request-json or --request-md")
    if args.request_json:
        path = expand_path(args.request_json)
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("--request-json must contain a JSON object")
        return payload
    if args.request_md:
        return parse_request_md(expand_path(args.request_md))
    return {}


def apply_cli_env_overrides(overrides: dict[str, object], items: list[str] | None) -> None:
    parsed = parse_env_overrides(items)
    overrides.update(parsed)
    for name, value in parsed.items():
        overrides[hyptest_env_name(name)] = value


def pick(args: argparse.Namespace, overrides: dict[str, object], name: str, default: str | None = None) -> str | None:
    value = getattr(args, name)
    if value is not None:
        return value
    if name == "repo_root":
        for alias in (
            "HYPTEST_HOME",
            "hyptest_home",
        ):
            override = overrides.get(alias)
            if override is not None:
                return str(override)
        return default
    override = overrides.get(name)
    if override is None:
        return default
    return str(override)


def add_unresolved_path_issue(
    issues: list[dict[str, str]],
    *,
    field: str,
    value: str | None,
    fallback_env: str | None = None,
    prompt_field: str | None = None,
) -> None:
    if not value:
        return
    missing = unresolved_env_vars(value)
    if not missing:
        return
    missing_text = ", ".join(missing)
    prompt_name = prompt_field or field
    prompt_hint = prompt_field_hint(prompt_name)
    if fallback_env and fallback_env in missing:
        export_hint = env_export_hint(fallback_env)
        fix = f"make the variable visible to this process (`{export_hint}`) or write `{prompt_hint}` in the prompt"
    else:
        fix = f"set the missing variable(s) before invoking the skill or write `{prompt_hint}` in the prompt"
    add_issue(
        issues,
        f"{field} contains unset variable(s): {missing_text}",
        fix,
    )


def has_unresolved_prompt_value(prompt_env: dict[str, str], name: str) -> bool:
    value = prompt_env.get(canonical_env_name(name))
    return bool(value and unresolved_env_vars(value))


def prompt_raw_env_value(overrides: dict[str, object], name: str) -> str | None:
    canonical = canonical_env_name(name)
    value = overrides.get(hyptest_env_name(canonical))
    if value is not None and bool(str(value).strip()):
        return str(value)
    return None


def has_env_field(overrides: dict[str, object], name: str) -> bool:
    return prompt_raw_env_value(overrides, name) is not None


def marked_placeholder(overrides: dict[str, object], name: str) -> bool:
    value = prompt_raw_env_value(overrides, name)
    return value is not None and is_placeholder_value(value)


def add_placeholder_issue(
    issues: list[dict[str, str]],
    *,
    field: str,
    value: str | None,
    hint_field: str | None = None,
) -> bool:
    if value is None or not is_placeholder_value(value):
        return False
    hint = prompt_field_hint(hint_field or field)
    add_issue(
        issues,
        f"{field} still contains a template placeholder: {value}",
        f"replace it with a real value such as `{hint}`, or omit the field if the current environment already provides it",
    )
    return True


def add_template_placeholder_issue(
    issues: list[dict[str, str]],
    *,
    field: str,
    value: str | None,
    hint_field: str | None = None,
) -> bool:
    if value is None or not re.search(r"<[^<>\n]+>", value.strip()):
        return False
    hint = prompt_field_hint(hint_field or field)
    add_issue(
        issues,
        f"{field} still contains a template placeholder: {value}",
        f"replace it with a real value such as `{hint}`, or omit the optional field",
    )
    return True


def placeholder(raw: str | None) -> bool:
    return bool(raw is not None and is_placeholder_value(raw))


def derived_nanhu_source(prompt_env: dict[str, str]) -> str:
    linknan = visible_env_value("LINKNAN_HOME", prompt_env)
    if not linknan:
        return ""
    linknan_home = expand_path(linknan)
    candidate = linknan_home / "dependencies" / "nanhu" / "src" / "main"
    return str(candidate) if candidate.is_dir() else ""


def resolve_profile(spec_profile: str) -> tuple[bool, str]:
    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_DIR / "resolve_spec_profile.py"),
            "--spec-profile",
            spec_profile,
        ],
        cwd=str(SKILL_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    text = (completed.stdout or completed.stderr).strip()
    return completed.returncode == 0, text


def parse_count(value: str | None) -> bool:
    if not value:
        return False
    return bool(re.fullmatch(r"\d+(?:-\d+)?", value.strip()))


def add_issue(issues: list[dict[str, str]], message: str, suggested_fix: str = "") -> None:
    item = {"message": message}
    if suggested_fix:
        item["suggested_fix"] = suggested_fix
    issues.append(item)


def add_warning(warnings: list[dict[str, str]], message: str, suggested_fix: str = "") -> None:
    item = {"message": message}
    if suggested_fix:
        item["suggested_fix"] = suggested_fix
    warnings.append(item)


def messages(items: list[dict[str, str]]) -> list[str]:
    return [item["message"] for item in items]


def normalize_platform(platform_raw: str | None) -> str | None:
    if not platform_raw:
        return None
    platform = platform_raw.strip().lower()
    return platform


def resolve_request_path(
    value: str | None,
    *,
    repo_root: Path | None = None,
) -> Path | None:
    if not value:
        return None
    if unresolved_env_vars(value):
        return None
    expanded = expand_path(value)
    if expanded.is_absolute():
        return expanded.resolve()
    if repo_root:
        return (repo_root / expanded).resolve()
    return None


def resolve_context_path(
    value: str | None,
    *,
    repo_root: Path | None = None,
) -> Path | None:
    if not value or unresolved_env_vars(value):
        return None
    expanded = expand_path(value)
    if expanded.is_absolute():
        return expanded.resolve()
    if repo_root:
        return (repo_root / expanded).resolve()
    return expanded.resolve()


def infer_coverage_scope(task_mode: str | None, explicit_scope: str | None) -> str | None:
    if explicit_scope:
        return explicit_scope
    if task_mode in {"new-case-only", "preflight-only"}:
        return "repo"
    if task_mode == "supplement-existing-point":
        return "file"
    return None


def build_next_commands(normalized: dict[str, object]) -> list[str]:
    script_home = "$HYPTEST_WORKFLOW_SKILL_HOME/scripts"
    profile = str(normalized.get("spec_profile") or default_spec_profile())
    repo_root = normalized.get("repo_root")
    test_point_file = normalized.get("test_point_file")
    platform = normalized.get("platform")
    task_mode = normalized.get("task_mode")
    case_name = normalized.get("case_name")
    failure_log = normalized.get("failure_log")
    env_overrides = normalized.get("env_overrides")
    waveform_context = normalized.get("waveform_context")
    env_args = ""
    if isinstance(env_overrides, dict):
        rendered = env_override_args(
            {
                str(key): str(value)
                for key, value in env_overrides.items()
                if value and not unresolved_env_vars(str(value))
            }
        )
        env_args = "".join(
            f" {rendered[index]} {rendered[index + 1]}"
            for index in range(0, len(rendered), 2)
        )
    commands = [
        f"python3 {script_home}/resolve_spec_profile.py --spec-profile {profile}",
    ]
    if repo_root:
        commands.append(f"python3 {script_home}/check_hyptest_cli_contract.py --repo-root {repo_root}")
    if repo_root and platform:
        task_mode_arg = f" --task-mode {task_mode}" if task_mode else ""
        commands.append(
            f"python3 {script_home}/check_env.py --repo-root {repo_root} --platform {platform}{task_mode_arg}{env_args} --explain"
        )
    if repo_root and task_mode == "new-case-only":
        commands.append(
            f"python3 {script_home}/find_similar_cases.py --repo-root {repo_root} --query '<scenario terms>' --limit 5 --explain-score"
        )
    if repo_root and test_point_file and task_mode in {
        "new-case-only",
        "supplement-existing-point",
        "writeback-only",
    }:
        commands.append(
            f"python3 {script_home}/check_writeback_format.py --repo-root {repo_root} --file {test_point_file} --check-register --spec-profile {profile}"
        )
    if failure_log and platform:
        waveform_args = ""
        if isinstance(waveform_context, dict):
            for field, flag in WAVEFORM_HANDOFF_CLI_FLAGS.items():
                value = waveform_context.get(field)
                if value:
                    waveform_args += f" {flag} {shlex.quote(str(value))}"
        commands.append(
            f"python3 {script_home}/make_triage_handoff.py --log-file {failure_log} --platform {platform} --spec-profile {profile}{waveform_args} --json"
        )
    elif task_mode == "triage-only" and case_name:
        commands.append(
            f"python3 {script_home}/classify_failure_log.py --log-file <log-for-{case_name}> --json"
        )
    return commands


def main() -> int:
    args = parse_args()
    try:
        overrides = load_request_overrides(args)
        apply_cli_env_overrides(overrides, args.env)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    issues: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []

    repo_root_raw = pick(args, overrides, "repo_root")
    test_point_file_raw = pick(args, overrides, "test_point_file")
    failure_log_raw = pick(args, overrides, "failure_log")
    platform_raw = pick(args, overrides, "platform")
    default_profile = default_spec_profile()
    spec_profile = pick(args, overrides, "spec_profile", default_profile) or default_profile
    spec_profile_placeholder = placeholder(spec_profile)
    task_mode = pick(args, overrides, "task_mode")
    case_name = pick(args, overrides, "case_name")
    new_case_count = pick(args, overrides, "new_case_count")
    coverage_scope = pick(args, overrides, "coverage_scope")
    waveform_raw = {
        field: pick(args, overrides, field)
        for field in WAVEFORM_HANDOFF_FIELDS
    }
    normalized_platform = normalize_platform(platform_raw)
    env_overrides = prompt_env_overrides(overrides)
    for raw_field, hint_field in (
        ("HYPTEST_HOME", "HYPTEST_HOME"),
        ("test_point_file", "test_point_file"),
        ("failure_log", "failure_log"),
        ("spec_profile", "spec_profile"),
    ):
        raw_value = pick(args, overrides, raw_field) if raw_field != "HYPTEST_HOME" else repo_root_raw
        add_placeholder_issue(
            issues,
            field=raw_field,
            value=raw_value,
            hint_field=hint_field,
        )
    for field, raw_value in waveform_raw.items():
        add_template_placeholder_issue(
            issues,
            field=field,
            value=raw_value,
            hint_field=field,
        )
        if field in WAVEFORM_HANDOFF_PATH_FIELDS:
            add_unresolved_path_issue(
                issues,
                field=field,
                value=raw_value,
                prompt_field=field,
            )
    for field_name, raw_key in (
        ("HYPTEST_SPIKE_BIN", "HYPTEST_SPIKE_BIN"),
        ("HYPTEST_LINKNAN_HOME", "HYPTEST_LINKNAN_HOME"),
        ("HYPTEST_DIFFTEST_REF_SO", "HYPTEST_DIFFTEST_REF_SO"),
        ("HYPTEST_CROSS_COMPILE", "HYPTEST_CROSS_COMPILE"),
        ("HYPTEST_TMPDIR", "HYPTEST_TMPDIR"),
    ):
        add_placeholder_issue(
            issues,
            field=field_name,
            value=prompt_raw_env_value(overrides, raw_key),
            hint_field=field_name,
        )
    for field_name, value in env_overrides.items():
        add_unresolved_path_issue(
            issues,
            field=hyptest_env_name(field_name),
            value=value,
            fallback_env=hyptest_env_name(field_name),
            prompt_field=hyptest_env_name(field_name),
        )
    repo_root_source = "prompt"
    if not repo_root_raw:
        env_repo_root = os.environ.get("HYPTEST_HOME", "").strip()
        env_repo_source = "HYPTEST_HOME"
        if env_repo_root:
            repo_root_raw = env_repo_root
            repo_root_source = env_repo_source
            add_unresolved_path_issue(
                issues,
                field=env_repo_source,
                value=env_repo_root,
                fallback_env=env_repo_source,
                prompt_field="HYPTEST_HOME",
            )
        else:
            repo_root_source = "missing"
    else:
        add_unresolved_path_issue(
            issues,
            field="HYPTEST_HOME",
            value=repo_root_raw,
            fallback_env="HYPTEST_HOME",
            prompt_field="HYPTEST_HOME",
        )

    repo_root_unresolved = bool(repo_root_raw and unresolved_env_vars(repo_root_raw))
    repo_root = (
        resolve_path(repo_root_raw)
        if repo_root_raw and not repo_root_unresolved and not placeholder(repo_root_raw)
        else None
    )
    test_point_file = (
        None if placeholder(test_point_file_raw)
        else resolve_request_path(test_point_file_raw, repo_root=repo_root)
    )
    failure_log = (
        None if placeholder(failure_log_raw)
        else resolve_request_path(failure_log_raw, repo_root=repo_root)
    )
    any_waveform_context = any(
        value and not placeholder(value)
        for value in waveform_raw.values()
    )
    if any_waveform_context and not waveform_raw.get("rtl_root"):
        derived_source = derived_nanhu_source(env_overrides)
        if derived_source:
            waveform_raw["rtl_root"] = derived_source
    waveform_paths = {
        field: (
            None
            if placeholder(waveform_raw.get(field))
            else resolve_context_path(waveform_raw.get(field), repo_root=repo_root)
        )
        for field in WAVEFORM_HANDOFF_PATH_FIELDS
    }
    waveform_context = {
        "waveform_path": str(waveform_paths["waveform_path"]) if waveform_paths["waveform_path"] else None,
        "rtl_root": str(waveform_paths["rtl_root"]) if waveform_paths["rtl_root"] else None,
        "top_module": None if placeholder(waveform_raw.get("top_module")) else waveform_raw.get("top_module"),
        "debug_target": None if placeholder(waveform_raw.get("debug_target")) else waveform_raw.get("debug_target"),
        "time_window": None if placeholder(waveform_raw.get("time_window")) else waveform_raw.get("time_window"),
        "expected_behavior": None if placeholder(waveform_raw.get("expected_behavior")) else waveform_raw.get("expected_behavior"),
        "observed_behavior": None if placeholder(waveform_raw.get("observed_behavior")) else waveform_raw.get("observed_behavior"),
        "suggested_waveform_report": str(waveform_paths["waveform_report"]) if waveform_paths["waveform_report"] else None,
    }

    if spec_profile_placeholder:
        profile_ok, profile_detail = False, ""
    else:
        profile_ok, profile_detail = resolve_profile(spec_profile)
    if not profile_ok and not spec_profile_placeholder:
        add_issue(
            issues,
            f"spec_profile not found or invalid: {spec_profile}: {profile_detail}",
            "use scripts/resolve_spec_profile.py --spec-profile <name> to list/verify the profile path",
        )

    if platform_raw:
        platform = platform_raw.strip().lower()
        if platform == "xiangshan":
            add_issue(
                issues,
                "platform=xiangshan is not a hyptest platform; use platform=linknan",
                "replace platform=xiangshan with platform=linknan",
            )
        elif platform not in VALID_PLATFORMS:
            add_issue(
                issues,
                f"unsupported platform `{platform_raw}`; expected spike or linknan",
                "set --platform spike or --platform linknan",
            )
    elif task_mode in SPIKE_RUN_TASK_MODES:
        add_issue(
            issues,
            f"task_mode={task_mode} requires platform when the task may compile or run a case",
            "write `platform: spike` or `platform: linknan` in the prompt",
        )

    if (
        normalized_platform == "spike"
        and task_mode in SPIKE_RUN_TASK_MODES
        and marked_placeholder(overrides, "SPIKE_BIN")
    ):
        add_issue(
            issues,
            "platform=spike run/gate requires a real HYPTEST_SPIKE_BIN path, not a placeholder",
            "write `HYPTEST_SPIKE_BIN: <community/upstream Spike executable>` or make HYPTEST_SPIKE_BIN visible to this process",
        )

    if (
        normalized_platform == "spike"
        and task_mode in SPIKE_RUN_TASK_MODES
        and not marked_placeholder(overrides, "SPIKE_BIN")
        and not visible_env_value("SPIKE_BIN", env_overrides)
        and not has_unresolved_prompt_value(env_overrides, "SPIKE_BIN")
    ):
        add_issue(
            issues,
            "platform=spike run/gate requires HYPTEST_SPIKE_BIN, but neither the prompt nor current environment provides it",
            "write `HYPTEST_SPIKE_BIN: <community/upstream Spike executable>` in the prompt or make it visible to this process with `export HYPTEST_SPIKE_BIN=<community/upstream Spike executable>`",
        )

    if (
        normalized_platform == "linknan"
        and task_mode in SPIKE_RUN_TASK_MODES
    ):
        placeholder_required = [
            name
            for name in ("LINKNAN_HOME", "DIFFTEST_REF_SO")
            if marked_placeholder(overrides, name)
        ]
        if placeholder_required:
            add_issue(
                issues,
                "platform=linknan run/gate requires real path(s), not placeholder values: "
                + ", ".join(hyptest_env_name(name) for name in placeholder_required),
                "write the required LinkNan gate fields in the prompt or export them before invoking the skill",
            )
        missing = [
            name
            for name in ("LINKNAN_HOME", "DIFFTEST_REF_SO")
            if not marked_placeholder(overrides, name)
            and not visible_env_value(name, env_overrides)
            and not has_unresolved_prompt_value(env_overrides, name)
        ]
        if missing:
            missing_prompt = ", ".join(prompt_field_hint(name) for name in missing)
            add_issue(
                issues,
                "platform=linknan run/gate requires "
                + ", ".join(hyptest_env_name(name) for name in missing),
                "write the missing fields in the prompt "
                f"({missing_prompt}) or export them before invoking the skill",
            )
        if visible_env_value("LINKNAN_HOME", env_overrides) and not derived_nanhu_source(env_overrides):
            add_issue(
                issues,
                "Nanhu source was not found under HYPTEST_LINKNAN_HOME/dependencies/nanhu/src/main",
                "initialize the LinkNan nanhu submodule or fix HYPTEST_LINKNAN_HOME",
            )

    if (
        normalized_platform == "spike"
        and task_mode in SPIKE_RUN_TASK_MODES
        and has_env_field(overrides, "LINKNAN_HOME")
        and not marked_placeholder(overrides, "LINKNAN_HOME")
        and visible_env_value("LINKNAN_HOME", env_overrides)
        and not derived_nanhu_source(env_overrides)
    ):
        add_issue(
            issues,
            "HYPTEST_LINKNAN_HOME was provided for source evidence, but Nanhu source was not found under HYPTEST_LINKNAN_HOME/dependencies/nanhu/src/main",
            "initialize the LinkNan nanhu submodule, fix HYPTEST_LINKNAN_HOME, or omit HYPTEST_LINKNAN_HOME from this Spike-only prompt when source evidence is out of scope",
        )

    if repo_root:
        required = ["compile_elf.py", "get_result.py", "test_register.c"]
        for rel in required:
            if not (repo_root / rel).exists():
                add_issue(
                    issues,
                    f"HYPTEST_HOME missing `{rel}`: {repo_root}",
                    "set prompt `HYPTEST_HOME: <riscv-hyp-tests-nhv5.1 repo root>` or pass --repo-root to that repository root",
                )
    elif task_mode not in {None, "triage-only"} and not repo_root_unresolved:
        add_issue(
            issues,
            "HYPTEST_HOME is required for this task_mode and is not visible in this process",
            "write `HYPTEST_HOME: <riscv-hyp-tests-nhv5.1 repo root>` in the prompt or make it visible with `export HYPTEST_HOME=<riscv-hyp-tests-nhv5.1 repo root>`",
        )

    if test_point_file_raw:
        add_unresolved_path_issue(
            issues,
            field="test_point_file",
            value=test_point_file_raw,
        )
    if test_point_file:
        if not test_point_file.is_file():
            add_issue(
                issues,
                f"test_point_file not found: {test_point_file}",
                "write an existing `test_point_file: test_point/<file>.md` under HYPTEST_HOME",
            )
        elif repo_root and repo_root not in test_point_file.parents and test_point_file != repo_root:
            add_warning(
                warnings,
                "test_point_file is outside HYPTEST_HOME; confirm this is intentional",
                "prefer `test_point_file: test_point/<file>.md` under HYPTEST_HOME",
            )
    elif test_point_file_raw and not repo_root and not unresolved_env_vars(test_point_file_raw):
        add_warning(
            warnings,
            "test_point_file is relative but HYPTEST_HOME is not resolved yet",
            "resolve HYPTEST_HOME first; relative test_point_file paths are checked under HYPTEST_HOME",
        )

    if task_mode in {"new-case-only", "preflight-only", "supplement-existing-point", "writeback-only"}:
        if not test_point_file_raw:
            add_issue(
                issues,
                f"task_mode={task_mode} requires --test-point-file",
                "write `test_point_file: test_point/<file>.md` in the prompt; relative paths are resolved under HYPTEST_HOME",
            )

    if task_mode == "new-case-only":
        if not parse_count(new_case_count):
            add_issue(
                issues,
                "task_mode=new-case-only requires --new-case-count like 1 or 1-3",
                "pass --new-case-count 1 or --new-case-count 1-3",
            )

    if task_mode in {"fix-case", "run-only"} and not case_name:
        add_warning(
            warnings,
            f"task_mode={task_mode} usually needs --case-name",
            "pass --case-name <case_name>",
        )

    if task_mode == "run-only" and not platform_raw:
        add_issue(issues, "task_mode=run-only requires --platform", "pass --platform spike or --platform linknan")

    if task_mode == "preflight-only" and not platform_raw:
        add_warning(
            warnings,
            "task_mode=preflight-only has no platform; profile/model notes may be less specific",
            "write `platform: spike` or `platform: linknan` when the preflight should be platform-aware",
        )

    if task_mode == "triage-only":
        if failure_log and not failure_log.is_file():
            add_issue(issues, f"failure_log not found: {failure_log}", "pass --failure-log <existing log path>")
        if not failure_log and not case_name:
            add_warning(
                warnings,
                "triage-only has no failure_log or case_name; evidence may be too thin",
                "pass --failure-log <log> or --case-name <case_name>",
            )

    waveform_path = waveform_paths["waveform_path"]
    rtl_root = waveform_paths["rtl_root"]
    waveform_report = waveform_paths["waveform_report"]
    if waveform_path and not waveform_path.is_file():
        add_warning(
            warnings,
            f"waveform_path not found: {waveform_path}",
            "confirm the FSDB/VCD/FST path before handing this to failure-triage",
        )
    if rtl_root and not rtl_root.is_dir():
        add_warning(
            warnings,
            f"rtl_root not found or not a directory: {rtl_root}",
            "pass an existing RTL/source root, commonly $HYPTEST_LINKNAN_HOME/dependencies/nanhu/src/main",
        )
    if waveform_report and waveform_report.name != "report.md":
        add_warning(
            warnings,
            "waveform_report should usually point to waveform-debug's report.md",
            "use a path ending in report.md when referencing waveform-debug output",
        )

    inferred_coverage_scope = infer_coverage_scope(task_mode, coverage_scope)
    normalized = {
        "repo_root": str(repo_root) if repo_root else None,
        "repo_root_source": repo_root_source,
        "test_point_file": str(test_point_file) if test_point_file else None,
        "failure_log": str(failure_log) if failure_log else None,
        "spec_profile": spec_profile,
        "spec_profile_path": profile_detail if profile_ok else None,
        "platform": normalized_platform,
        "task_mode": task_mode,
        "case_name": case_name,
        "new_case_count": new_case_count,
        "coverage_scope": inferred_coverage_scope,
        "env_overrides": env_overrides,
        "waveform_context": waveform_context,
    }
    payload = {
        "ok": not issues,
        "issues": messages(issues),
        "warnings": messages(warnings),
        "issue_details": issues,
        "warning_details": warnings,
        "normalized": normalized,
        "next_commands": build_next_commands(normalized),
        "resolved": {
            "repo_root": str(repo_root) if repo_root else None,
            "repo_root_source": repo_root_source,
            "test_point_file": str(test_point_file) if test_point_file else None,
            "failure_log": str(failure_log) if failure_log else None,
            "spec_profile": spec_profile,
            "spec_profile_path": profile_detail if profile_ok else None,
            "platform": platform_raw,
            "task_mode": task_mode,
            "case_name": case_name,
            "new_case_count": new_case_count,
            "coverage_scope": inferred_coverage_scope,
            "env_overrides": env_overrides,
            "waveform_context": waveform_context,
        },
    }

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(("PASS" if payload["ok"] else "FAIL") + " task request")
        for issue in issues:
            print(f"  - issue: {issue['message']}")
            if issue.get("suggested_fix"):
                print(f"    fix: {issue['suggested_fix']}")
        for warning in warnings:
            print(f"  - warning: {warning['message']}")
            if warning.get("suggested_fix"):
                print(f"    fix: {warning['suggested_fix']}")
        if payload["next_commands"]:
            print("next commands:")
            for command in payload["next_commands"]:
                print(f"  {command}")
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
