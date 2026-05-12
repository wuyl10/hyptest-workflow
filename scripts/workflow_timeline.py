#!/usr/bin/env python3
"""Record prompt-to-final phase timing for one hyptest workflow turn."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from skill_config import resolve_path
from workflow_paths import workflow_report_dir


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Record an agent-visible prompt-to-final timeline. Start this as the "
            "first workflow command, call enter at each major phase boundary, and "
            "finish immediately before the final answer."
        )
    )
    sub = parser.add_subparsers(dest="command", required=True)

    start = sub.add_parser("start", help="Create a new timeline and enter the first phase.")
    add_common(start)
    start.add_argument("--timeline-id", help="Stable id for this workflow timeline.")
    start.add_argument("--label", help="Human-readable task label used when generating an id.")
    start.add_argument("--phase", default="prompt_intake", help="Initial phase name.")
    start.add_argument(
        "--prompt-received-at",
        help=(
            "Optional timestamp for when the user prompt was received. If omitted, "
            "pre-start model thinking time is not observable by this script."
        ),
    )
    add_metadata_args(start)
    start.add_argument("--force", action="store_true", help="Overwrite an existing event log.")

    enter = sub.add_parser("enter", help="Close the current phase and enter a new phase.")
    add_common(enter)
    enter.add_argument("--timeline", required=True, help="Timeline id or event-log path.")
    enter.add_argument("--phase", required=True, help="New active phase name.")

    cmd_start = sub.add_parser("cmd-start", help="Start timing one concrete command within the active phase.")
    add_common(cmd_start)
    cmd_start.add_argument("--timeline", required=True, help="Timeline id or event-log path.")
    cmd_start.add_argument("--name", required=True, help="Short command/span name.")
    cmd_start.add_argument("--phase", help="Phase name if this command should be attributed explicitly.")
    cmd_start.add_argument("--cmd", help="Command line or short command template.")
    cmd_start.add_argument("--span-id", help="Stable id used to match cmd-start/cmd-end.")

    cmd_end = sub.add_parser("cmd-end", help="Finish timing one concrete command within the active phase.")
    add_common(cmd_end)
    cmd_end.add_argument("--timeline", required=True, help="Timeline id or event-log path.")
    cmd_end.add_argument("--span-id", required=True, help="Span id emitted by cmd-start.")
    cmd_end.add_argument("--status", default="done", help="Command status, e.g. pass/fail/timeout.")
    cmd_end.add_argument("--return-code", type=int, help="Command process return code.")

    finish = sub.add_parser("finish", help="Close the current phase and write timeline reports.")
    add_common(finish)
    finish.add_argument("--timeline", required=True, help="Timeline id or event-log path.")
    finish.add_argument("--json-out", help="Write JSON report to this path.")
    finish.add_argument("--md-out", help="Write Markdown report to this path.")

    show = sub.add_parser("show", help="Render a report from an existing timeline without adding events.")
    add_common(show, include_note=False, include_at=False)
    show.add_argument("--timeline", required=True, help="Timeline id or event-log path.")
    show.add_argument("--json-out", help="Write JSON report to this path.")
    show.add_argument("--md-out", help="Write Markdown report to this path.")

    return parser.parse_args()


def add_common(parser: argparse.ArgumentParser, *, include_note: bool = True, include_at: bool = True) -> None:
    parser.add_argument("--repo-root", required=True, help="Path to hyptest repo root.")
    if include_note:
        parser.add_argument("--note", default="", help="Short note for this timeline event.")
    if include_at:
        parser.add_argument(
            "--at",
            help="Override event timestamp for tests, e.g. 2026-01-01T00:00:00Z.",
        )
    parser.add_argument("--json", action="store_true", help="Emit JSON.")


def add_metadata_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--case", help="Case name, if known.")
    parser.add_argument("--test-point-file", help="test_point file for this workflow.")
    parser.add_argument("--platform", help="Target platform.")
    parser.add_argument("--spec-profile", help="Spec profile.")
    parser.add_argument("--task-mode", help="Task mode.")
    parser.add_argument("--target-module", help="Target module.")
    parser.add_argument("--new-case-count", help="Requested new case count.")


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def parse_time(value: str | None) -> datetime:
    if not value:
        return now_utc()
    raw = value.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    dt = datetime.fromisoformat(raw)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def format_time(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def seconds_between(start: str, end: str) -> float:
    start_dt = parse_time(start)
    end_dt = parse_time(end)
    return round((end_dt - start_dt).total_seconds(), 3)


def slugify(value: str) -> str:
    text = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
    text = re.sub(r"_+", "_", text).strip("._-")
    return text[:96] or "workflow"


def report_dir(repo_root: Path) -> Path:
    path = workflow_report_dir(repo_root)
    path.mkdir(parents=True, exist_ok=True)
    return path


def default_timeline_id(args: argparse.Namespace, dt: datetime) -> str:
    base = args.label or args.case or args.test_point_file or "hyptest_workflow"
    stamp = dt.strftime("%Y%m%d_%H%M%S")
    return f"{slugify(base)}_{stamp}"


def event_log_for(repo_root: Path, timeline: str) -> Path:
    raw = Path(timeline).expanduser()
    if raw.suffix == ".jsonl" or raw.is_absolute() or "/" in timeline:
        return resolve_path(str(raw))
    return report_dir(repo_root) / f"{slugify(timeline)}_workflow_timeline_events.jsonl"


def default_report_path(event_log: Path, suffix: str) -> Path:
    name = event_log.name
    if name.endswith("_events.jsonl"):
        stem = name[: -len("_events.jsonl")]
    else:
        stem = event_log.stem
    return event_log.with_name(f"{stem}.{suffix}")


def append_event(path: Path, event: dict[str, Any], *, force: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if force and path.exists():
        path.unlink()
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")


def load_events(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise FileNotFoundError(str(path))
    events: list[dict[str, Any]] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        payload = json.loads(line)
        if not isinstance(payload, dict):
            raise ValueError(f"event line {line_no} is not an object: {path}")
        events.append(payload)
    return events


def metadata_from_args(args: argparse.Namespace) -> dict[str, Any]:
    keys = [
        "case",
        "test_point_file",
        "platform",
        "spec_profile",
        "task_mode",
        "target_module",
        "new_case_count",
    ]
    return {key: getattr(args, key) for key in keys if getattr(args, key, None)}


def prompt_received_at_from_args(args: argparse.Namespace, start_dt: datetime) -> str | None:
    value = getattr(args, "prompt_received_at", None)
    if not value:
        return None
    prompt_dt = parse_time(value)
    if prompt_dt > start_dt:
        raise ValueError("--prompt-received-at must be earlier than or equal to the start time")
    return format_time(prompt_dt)


def common_event(args: argparse.Namespace, event_type: str, dt: datetime) -> dict[str, Any]:
    return {
        "event": event_type,
        "phase": getattr(args, "phase", None),
        "at": format_time(dt),
        "note": getattr(args, "note", "") or "",
    }


def active_phase_at(events: list[dict[str, Any]], at: str) -> str | None:
    active: str | None = None
    at_dt = parse_time(at)
    for event in events:
        event_at = str(event.get("at") or "")
        if not event_at or parse_time(event_at) > at_dt:
            continue
        event_type = event.get("event")
        if event_type in {"start", "enter"}:
            active = str(event.get("phase") or "unnamed")
        elif event_type == "finish":
            active = None
    return active


def build_report(repo_root: Path, event_log: Path, events: list[dict[str, Any]]) -> dict[str, Any]:
    timeline_id = event_log.name.removesuffix("_workflow_timeline_events.jsonl")
    first_start = next((event for event in events if event.get("event") == "start"), {})
    metadata = first_start.get("metadata") if isinstance(first_start.get("metadata"), dict) else {}

    phases: list[dict[str, Any]] = []
    current_phase: str | None = None
    current_start: str | None = None
    current_note = ""
    started_at: str | None = None
    finished_at: str | None = None

    for event in events:
        event_type = event.get("event")
        event_at = str(event.get("at") or "")
        if not event_at:
            continue
        if event_type == "start":
            if started_at is None:
                started_at = event_at
            current_phase = str(event.get("phase") or "prompt_intake")
            current_start = event_at
            current_note = str(event.get("note") or "")
        elif event_type == "enter":
            if current_phase and current_start:
                phases.append(
                    phase_record(
                        current_phase,
                        current_start,
                        event_at,
                        current_note,
                        "enter",
                    )
                )
            if started_at is None:
                started_at = event_at
            current_phase = str(event.get("phase") or "unnamed")
            current_start = event_at
            current_note = str(event.get("note") or "")
        elif event_type == "finish":
            if current_phase and current_start:
                phases.append(
                    phase_record(
                        current_phase,
                        current_start,
                        event_at,
                        current_note,
                        "finish",
                    )
                )
            if started_at is None:
                started_at = event_at
            finished_at = event_at
            current_phase = None
            current_start = None
            current_note = ""

    if finished_at is None and current_phase and current_start:
        last_at = str(events[-1].get("at") or current_start)
        phases.append(
            phase_record(current_phase, current_start, last_at, current_note, "open")
        )

    command_spans = command_span_records(events)
    assign_commands_to_phases(phases, command_spans)

    aggregate: dict[str, float] = {}
    for item in phases:
        aggregate[item["name"]] = round(
            aggregate.get(item["name"], 0.0) + float(item.get("seconds") or 0.0),
            3,
        )
    slowest = sorted(phases, key=lambda item: float(item.get("seconds") or 0.0), reverse=True)[:8]
    command_aggregate: dict[str, float] = {}
    for item in command_spans:
        command_aggregate[item["name"]] = round(
            command_aggregate.get(item["name"], 0.0) + float(item.get("seconds") or 0.0),
            3,
        )
    slowest_commands = sorted(
        command_spans,
        key=lambda item: float(item.get("seconds") or 0.0),
        reverse=True,
    )[:12]
    prompt_received_at = first_start.get("prompt_received_at")
    if prompt_received_at is not None:
        prompt_received_at = str(prompt_received_at)
    pre_start_model_seconds = (
        seconds_between(prompt_received_at, started_at)
        if prompt_received_at and started_at
        else None
    )
    prompt_to_finish_seconds = (
        seconds_between(prompt_received_at, finished_at)
        if prompt_received_at and finished_at
        else None
    )
    total_seconds = seconds_between(started_at, finished_at) if started_at and finished_at else None
    total_command_seconds = round(
        sum(float(item.get("command_seconds") or 0.0) for item in phases),
        3,
    )
    total_command_span_seconds = round(
        sum(float(item.get("seconds") or 0.0) for item in command_spans),
        3,
    )
    total_unattributed_seconds = (
        round(float(total_seconds) - total_command_seconds, 3)
        if total_seconds is not None
        else None
    )
    optimization_hints = build_optimization_hints(
        phases,
        command_spans,
        total_seconds=total_seconds,
        total_unattributed_seconds=total_unattributed_seconds,
    )

    return {
        "timeline_id": timeline_id,
        "repo_root": str(repo_root),
        "event_log": str(event_log),
        "case": metadata.get("case"),
        "test_point_file": metadata.get("test_point_file"),
        "platform": metadata.get("platform"),
        "spec_profile": metadata.get("spec_profile"),
        "task_mode": metadata.get("task_mode"),
        "target_module": metadata.get("target_module"),
        "new_case_count": metadata.get("new_case_count"),
        "started_at": started_at,
        "finished_at": finished_at,
        "status": "finished" if finished_at else "open",
        "timing": {
            "total_seconds": total_seconds,
            "prompt_received_at": prompt_received_at,
            "pre_start_model_seconds": pre_start_model_seconds,
            "prompt_to_finish_seconds": prompt_to_finish_seconds,
            "total_command_seconds": total_command_seconds,
            "total_command_span_seconds": total_command_span_seconds,
            "total_unattributed_seconds": total_unattributed_seconds,
            "phases": phases,
            "by_phase": aggregate,
            "slowest_phases": slowest,
            "commands": command_spans,
            "by_command": command_aggregate,
            "slowest_commands": slowest_commands,
            "optimization_hints": optimization_hints,
        },
        "event_count": len(events),
        "events": events,
        "measurement_boundary": (
            "By default, total_seconds starts when workflow_timeline.py start is first invoked, "
            "so pure model thinking before the first tool call is not observable. If start was "
            "called with --prompt-received-at, pre_start_model_seconds and prompt_to_finish_seconds "
            "include that external prompt boundary. Run finish immediately before the final answer; "
            "tokens generated after finish are not included."
        ),
        "quality_boundary": (
            "This timeline records prompt-to-final workflow phase time plus optional command spans. "
            "Command spans are measured only when cmd-start/cmd-end or workflow_timed_cmd.py is used; "
            "command_seconds is the merged wall-clock union of command spans inside each phase, while "
            "command_span_seconds is the raw sum of spans and can exceed wall time if commands overlap. "
            "phase unattributed time is model thinking after timeline start, tool scheduling, evidence review, "
            "manual edits, or uninstrumented work. "
            "It does not replace compile/run evidence, postcheck evidence, or default/manual/compile-only decisions."
        ),
    }


def build_optimization_hints(
    phases: list[dict[str, Any]],
    commands: list[dict[str, Any]],
    *,
    total_seconds: float | None,
    total_unattributed_seconds: float | None,
) -> dict[str, Any]:
    """Summarize where timeline time can be optimized or better attributed."""
    late_phase_candidates = [
        {
            "phase": item.get("name"),
            "after_last_command_seconds": item.get("after_last_command_seconds"),
            "seconds": item.get("seconds"),
            "command_seconds": item.get("command_seconds"),
        }
        for item in phases
        if "late_phase_exit" in (item.get("diagnostic_flags") or [])
    ]
    no_command_candidates = [
        {
            "phase": item.get("name"),
            "seconds": item.get("seconds"),
        }
        for item in phases
        if "no_command_spans" in (item.get("diagnostic_flags") or [])
        and float(item.get("seconds") or 0.0) >= 5.0
    ]
    low_attr_candidates = [
        {
            "phase": item.get("name"),
            "seconds": item.get("seconds"),
            "command_seconds": item.get("command_seconds"),
            "unattributed_seconds": item.get("unattributed_seconds"),
            "attribution_ratio": item.get("attribution_ratio"),
            "flags": item.get("diagnostic_flags") or [],
        }
        for item in phases
        if "low_command_attribution" in (item.get("diagnostic_flags") or [])
    ]
    slow_commands = [
        {
            "name": item.get("name"),
            "phase": item.get("phase"),
            "seconds": item.get("seconds"),
            "status": item.get("status"),
            "return_code": item.get("return_code"),
        }
        for item in sorted(
            commands,
            key=lambda command: float(command.get("seconds") or 0.0),
            reverse=True,
        )
        if float(item.get("seconds") or 0.0) >= 1.0
    ][:5]

    late_phase_exit_seconds = round(
        sum(float(item.get("after_last_command_seconds") or 0.0) for item in late_phase_candidates),
        3,
    )
    no_command_phase_seconds = round(
        sum(
            float(item.get("seconds") or 0.0)
            for item in phases
            if "no_command_spans" in (item.get("diagnostic_flags") or [])
        ),
        3,
    )
    other_unattributed_seconds = (
        round(
            max(
                0.0,
                float(total_unattributed_seconds)
                - late_phase_exit_seconds
                - no_command_phase_seconds,
            ),
            3,
        )
        if total_unattributed_seconds is not None
        else None
    )
    command_seconds = round(
        sum(float(item.get("command_seconds") or 0.0) for item in phases),
        3,
    )
    command_ratio = (
        round(command_seconds / float(total_seconds), 3)
        if total_seconds and float(total_seconds) > 0.0
        else None
    )

    recommended_actions: list[str] = []
    if late_phase_candidates:
        recommended_actions.append(
            "Tighten phase exits: after a wrapped command finishes and its output is read, enter a review or next command phase immediately."
        )
    if no_command_candidates:
        recommended_actions.append(
            "Split long no-command phases into explicit design/edit/review phases, or add command spans around generated helper scripts when work is tool-driven."
        )
    if slow_commands:
        recommended_actions.append(
            "Optimize the slowest real commands separately; they are the only part counted as command_seconds."
        )
    if command_ratio is not None and command_ratio < 0.25:
        recommended_actions.append(
            "Treat this run as model/review/edit dominated; pack scripts and templates will help more than compile/run tuning."
        )

    return {
        "interpretation": (
            "total_unattributed_seconds is not one script. It is model thinking, output review, edits, "
            "tool scheduling, uninstrumented work, and phase-boundary lag after timeline start."
        ),
        "total_seconds": total_seconds,
        "command_seconds": command_seconds,
        "command_ratio": command_ratio,
        "total_unattributed_seconds": total_unattributed_seconds,
        "late_phase_exit_seconds": late_phase_exit_seconds,
        "no_command_phase_seconds": no_command_phase_seconds,
        "other_unattributed_seconds": other_unattributed_seconds,
        "boundary_tightening_candidates": late_phase_candidates,
        "no_command_phase_candidates": no_command_candidates,
        "low_attribution_candidates": low_attr_candidates,
        "slow_command_candidates": slow_commands,
        "recommended_actions": recommended_actions,
    }


def phase_record(name: str, start: str, end: str, note: str, end_reason: str) -> dict[str, Any]:
    return {
        "name": name,
        "started_at": start,
        "ended_at": end,
        "seconds": seconds_between(start, end),
        "note": note,
        "end_reason": end_reason,
    }


def command_span_records(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    starts: dict[str, dict[str, Any]] = {}
    spans: list[dict[str, Any]] = []
    for event in events:
        event_type = event.get("event")
        span_id = str(event.get("span_id") or "")
        if not span_id:
            continue
        if event_type == "cmd_start":
            starts[span_id] = event
        elif event_type == "cmd_end":
            start = starts.pop(span_id, None)
            if not start:
                spans.append(
                    {
                        "span_id": span_id,
                        "name": str(event.get("name") or span_id),
                        "phase": event.get("phase"),
                        "started_at": None,
                        "ended_at": event.get("at"),
                        "seconds": None,
                        "status": event.get("status") or "done",
                        "return_code": event.get("return_code"),
                        "cmd": event.get("cmd"),
                        "note": event.get("note") or "",
                        "complete": False,
                    }
                )
                continue
            start_at = str(start.get("at") or "")
            end_at = str(event.get("at") or "")
            spans.append(
                {
                    "span_id": span_id,
                    "name": str(start.get("name") or event.get("name") or span_id),
                    "phase": start.get("phase") or event.get("phase"),
                    "started_at": start_at,
                    "ended_at": end_at,
                    "seconds": seconds_between(start_at, end_at) if start_at and end_at else None,
                    "status": event.get("status") or "done",
                    "return_code": event.get("return_code"),
                    "cmd": start.get("cmd") or event.get("cmd"),
                    "note": event.get("note") or start.get("note") or "",
                    "complete": True,
                }
            )
    for span_id, start in starts.items():
        spans.append(
            {
                "span_id": span_id,
                "name": str(start.get("name") or span_id),
                "phase": start.get("phase"),
                "started_at": start.get("at"),
                "ended_at": None,
                "seconds": None,
                "status": "open",
                "return_code": None,
                "cmd": start.get("cmd"),
                "note": start.get("note") or "",
                "complete": False,
            }
        )
    return spans


def assign_commands_to_phases(phases: list[dict[str, Any]], commands: list[dict[str, Any]]) -> None:
    for phase in phases:
        phase_name = str(phase.get("name") or "")
        phase_start = str(phase.get("started_at") or "")
        phase_end = str(phase.get("ended_at") or "")
        phase_commands = [
            command
            for command in commands
            if command.get("complete") is True
            and command.get("started_at")
            and command_in_phase(command, phase_name, phase_start, phase_end)
        ]
        command_span_seconds = round(
            sum(float(command.get("seconds") or 0.0) for command in phase_commands),
            3,
        )
        command_seconds = phase_command_wall_seconds(phase, phase_commands)
        phase["command_seconds"] = command_seconds
        phase["command_span_seconds"] = command_span_seconds
        phase["unattributed_seconds"] = round(
            max(0.0, float(phase.get("seconds") or 0.0) - command_seconds),
            3,
        )
        phase["attribution_ratio"] = round(
            command_seconds / float(phase.get("seconds") or 1.0),
            3,
        )
        add_phase_gap_diagnostics(phase, phase_commands)
        phase["command_count"] = len(phase_commands)
        phase["commands"] = [
            {
                "span_id": command.get("span_id"),
                "name": command.get("name"),
                "seconds": command.get("seconds"),
                "status": command.get("status"),
                "return_code": command.get("return_code"),
            }
            for command in phase_commands
        ]
        for command in phase_commands:
            command["phase"] = phase_name


def phase_command_wall_seconds(phase: dict[str, Any], commands: list[dict[str, Any]]) -> float:
    phase_start = str(phase.get("started_at") or "")
    phase_end = str(phase.get("ended_at") or "")
    if not phase_start or not phase_end:
        return 0.0
    phase_start_dt = parse_time(phase_start)
    phase_end_dt = parse_time(phase_end)
    intervals: list[tuple[datetime, datetime]] = []
    for command in commands:
        start_at = str(command.get("started_at") or "")
        end_at = str(command.get("ended_at") or "")
        if not start_at or not end_at:
            continue
        start_dt = max(parse_time(start_at), phase_start_dt)
        end_dt = min(parse_time(end_at), phase_end_dt)
        if end_dt > start_dt:
            intervals.append((start_dt, end_dt))
    if not intervals:
        return 0.0
    intervals.sort(key=lambda item: item[0])
    merged: list[tuple[datetime, datetime]] = []
    for start_dt, end_dt in intervals:
        if not merged or start_dt > merged[-1][1]:
            merged.append((start_dt, end_dt))
        else:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end_dt))
    return round(sum((end_dt - start_dt).total_seconds() for start_dt, end_dt in merged), 3)


def add_phase_gap_diagnostics(phase: dict[str, Any], commands: list[dict[str, Any]]) -> None:
    phase_start = str(phase.get("started_at") or "")
    phase_end = str(phase.get("ended_at") or "")
    if not phase_start or not phase_end or not commands:
        phase["before_first_command_seconds"] = None
        phase["after_last_command_seconds"] = None
        phase["command_window_seconds"] = None
        phase["diagnostic_flags"] = ["no_command_spans"] if not commands else []
        return

    phase_start_dt = parse_time(phase_start)
    phase_end_dt = parse_time(phase_end)
    intervals: list[tuple[datetime, datetime]] = []
    for command in commands:
        start_at = str(command.get("started_at") or "")
        end_at = str(command.get("ended_at") or "")
        if not start_at or not end_at:
            continue
        start_dt = max(parse_time(start_at), phase_start_dt)
        end_dt = min(parse_time(end_at), phase_end_dt)
        if end_dt > start_dt:
            intervals.append((start_dt, end_dt))
    if not intervals:
        phase["before_first_command_seconds"] = None
        phase["after_last_command_seconds"] = None
        phase["command_window_seconds"] = None
        phase["diagnostic_flags"] = ["command_outside_phase_window"]
        return

    first_start = min(start_dt for start_dt, _ in intervals)
    last_end = max(end_dt for _, end_dt in intervals)
    before_first = round((first_start - phase_start_dt).total_seconds(), 3)
    after_last = round((phase_end_dt - last_end).total_seconds(), 3)
    command_window = round((last_end - first_start).total_seconds(), 3)
    phase["before_first_command_seconds"] = before_first
    phase["after_last_command_seconds"] = after_last
    phase["command_window_seconds"] = command_window

    flags: list[str] = []
    phase_seconds = float(phase.get("seconds") or 0.0)
    if phase_seconds >= 30.0 and float(phase.get("attribution_ratio") or 0.0) < 0.25:
        flags.append("low_command_attribution")
    if before_first >= 30.0:
        flags.append("late_first_command")
    if after_last >= 30.0:
        flags.append("late_phase_exit")
    phase["diagnostic_flags"] = flags


def command_in_phase(command: dict[str, Any], phase_name: str, phase_start: str, phase_end: str) -> bool:
    if command.get("phase"):
        return command.get("phase") == phase_name
    command_start = str(command.get("started_at") or "")
    if not command_start or not phase_start or not phase_end:
        return False
    dt = parse_time(command_start)
    return parse_time(phase_start) <= dt < parse_time(phase_end)


def render_markdown(report: dict[str, Any]) -> str:
    timing = report.get("timing") or {}
    lines = [
        "# hyptest workflow timeline",
        "",
        f"- timeline_id: `{report.get('timeline_id')}`",
        f"- HYPTEST_HOME: `{report.get('repo_root')}`",
        f"- case: `{report.get('case') or ''}`",
        f"- test_point_file: `{report.get('test_point_file') or ''}`",
        f"- platform: `{report.get('platform') or ''}`",
        f"- spec_profile: `{report.get('spec_profile') or ''}`",
        f"- status: `{report.get('status')}`",
        f"- started_at: `{report.get('started_at')}`",
        f"- finished_at: `{report.get('finished_at')}`",
        f"- total_seconds: `{timing.get('total_seconds')}`",
        f"- prompt_received_at: `{timing.get('prompt_received_at') or ''}`",
        f"- pre_start_model_seconds: `{timing.get('pre_start_model_seconds') if timing.get('pre_start_model_seconds') is not None else 'unobserved'}`",
        f"- prompt_to_finish_seconds: `{timing.get('prompt_to_finish_seconds') if timing.get('prompt_to_finish_seconds') is not None else 'unobserved'}`",
        f"- command_seconds: `{timing.get('total_command_seconds')}`",
        f"- command_span_seconds: `{timing.get('total_command_span_seconds')}`",
        f"- unattributed_seconds: `{timing.get('total_unattributed_seconds')}`",
        f"- event_log: `{report.get('event_log')}`",
        "",
        "## Phase Timing",
        "",
    ]
    phases = timing.get("phases") or []
    if not phases:
        lines.append("- none")
    for item in phases:
        note = f" note=`{item.get('note')}`" if item.get("note") else ""
        flags = item.get("diagnostic_flags") or []
        flag_text = f" flags=`{','.join(flags)}`" if flags else ""
        pre_cmd = item.get("before_first_command_seconds")
        post_cmd = item.get("after_last_command_seconds")
        lines.append(
            f"- `{item.get('name')}` {item.get('seconds')}s "
            f"cmd={item.get('command_seconds', 0)}s "
            f"unattributed={item.get('unattributed_seconds', item.get('seconds'))}s "
            f"attr={item.get('attribution_ratio', 0)} "
            f"pre_cmd={pre_cmd if pre_cmd is not None else 'n/a'} "
            f"post_cmd={post_cmd if post_cmd is not None else 'n/a'} "
            f"start=`{item.get('started_at')}` end=`{item.get('ended_at')}`{note}"
            f"{flag_text}"
        )
    lines.extend(["", "## Slowest Phases", ""])
    slowest = timing.get("slowest_phases") or []
    if not slowest:
        lines.append("- none")
    for item in slowest:
        lines.append(
            f"- `{item.get('name')}` {item.get('seconds')}s "
            f"(cmd={item.get('command_seconds', 0)}s, "
            f"unattributed={item.get('unattributed_seconds', item.get('seconds'))}s)"
        )
    lines.extend(["", "## Command Timing", ""])
    commands = timing.get("commands") or []
    if not commands:
        lines.append("- none recorded; use `cmd-start`/`cmd-end` or `workflow_timed_cmd.py` for command-level timing")
    for item in timing.get("slowest_commands") or []:
        cmd = f" cmd=`{item.get('cmd')}`" if item.get("cmd") else ""
        lines.append(
            f"- `{item.get('name')}` phase=`{item.get('phase') or ''}` "
            f"{item.get('seconds')}s status=`{item.get('status')}` rc=`{item.get('return_code')}`{cmd}"
        )
    hints = timing.get("optimization_hints") or {}
    if hints:
        lines.extend(["", "## Optimization Hints", ""])
        lines.append(f"- interpretation: {hints.get('interpretation')}")
        lines.append(
            f"- breakdown: command={hints.get('command_seconds')}s "
            f"ratio={hints.get('command_ratio')} "
            f"unattributed={hints.get('total_unattributed_seconds')}s "
            f"late_phase_exit={hints.get('late_phase_exit_seconds')}s "
            f"no_command={hints.get('no_command_phase_seconds')}s "
            f"other_unattributed={hints.get('other_unattributed_seconds')}s"
        )
        boundary = hints.get("boundary_tightening_candidates") or []
        if boundary:
            lines.append("- boundary_tightening_candidates:")
            for item in boundary[:8]:
                lines.append(
                    f"  - `{item.get('phase')}` post_cmd={item.get('after_last_command_seconds')}s "
                    f"phase={item.get('seconds')}s cmd={item.get('command_seconds')}s"
                )
        no_command = hints.get("no_command_phase_candidates") or []
        if no_command:
            lines.append("- no_command_phase_candidates:")
            for item in no_command[:8]:
                lines.append(f"  - `{item.get('phase')}` {item.get('seconds')}s")
        slow_commands = hints.get("slow_command_candidates") or []
        if slow_commands:
            lines.append("- slow_command_candidates:")
            for item in slow_commands[:5]:
                lines.append(
                    f"  - `{item.get('name')}` phase=`{item.get('phase') or ''}` "
                    f"{item.get('seconds')}s status=`{item.get('status')}`"
                )
        actions = hints.get("recommended_actions") or []
        if actions:
            lines.append("- recommended_actions:")
            for action in actions:
                lines.append(f"  - {action}")
    lines.extend(
        [
            "",
            "## Boundaries",
            "",
            f"- measurement: {report.get('measurement_boundary')}",
            f"- quality: {report.get('quality_boundary')}",
            "",
        ]
    )
    return "\n".join(lines)


def write_outputs(report: dict[str, Any], json_out: str | None, md_out: str | None, event_log: Path) -> None:
    json_path = resolve_path(json_out) if json_out else default_report_path(event_log, "json")
    md_path = resolve_path(md_out) if md_out else default_report_path(event_log, "md")
    json_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(report) + "\n", encoding="utf-8")


def print_result(payload: dict[str, Any], *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        for key, value in payload.items():
            print(f"{key}: {value}")


def main() -> int:
    args = parse_args()
    repo_root = resolve_path(args.repo_root)

    try:
        if args.command == "start":
            dt = parse_time(args.at)
            timeline_id = slugify(args.timeline_id or default_timeline_id(args, dt))
            event_log = event_log_for(repo_root, timeline_id)
            if event_log.exists() and not args.force:
                print(
                    f"error: timeline event log already exists: {event_log}; use --force or a new --timeline-id",
                    file=sys.stderr,
                )
                return 2
            event = common_event(args, "start", dt)
            event["metadata"] = metadata_from_args(args)
            prompt_received_at = prompt_received_at_from_args(args, dt)
            if prompt_received_at:
                event["prompt_received_at"] = prompt_received_at
            append_event(event_log, event, force=args.force)
            print_result(
                {
                    "timeline_id": timeline_id,
                    "event_log": str(event_log),
                    "active_phase": args.phase,
                    "started_at": event["at"],
                },
                as_json=args.json,
            )
            return 0

        if args.command == "enter":
            dt = parse_time(args.at)
            event_log = event_log_for(repo_root, args.timeline)
            append_event(event_log, common_event(args, "enter", dt))
            print_result(
                {
                    "timeline_id": event_log.name.removesuffix("_workflow_timeline_events.jsonl"),
                    "event_log": str(event_log),
                    "active_phase": args.phase,
                    "entered_at": format_time(dt),
                },
                as_json=args.json,
            )
            return 0

        if args.command == "cmd-start":
            dt = parse_time(args.at)
            event_log = event_log_for(repo_root, args.timeline)
            events = load_events(event_log) if event_log.exists() else []
            span_id = slugify(args.span_id or f"{args.name}_{dt.strftime('%Y%m%d_%H%M%S_%f')}")
            event = common_event(args, "cmd_start", dt)
            event["span_id"] = span_id
            event["name"] = args.name
            event["phase"] = args.phase or active_phase_at(events, event["at"])
            if args.cmd:
                event["cmd"] = args.cmd
            append_event(event_log, event)
            print_result(
                {
                    "timeline_id": event_log.name.removesuffix("_workflow_timeline_events.jsonl"),
                    "event_log": str(event_log),
                    "span_id": span_id,
                    "name": args.name,
                    "phase": event.get("phase"),
                    "started_at": event["at"],
                },
                as_json=args.json,
            )
            return 0

        if args.command == "cmd-end":
            dt = parse_time(args.at)
            event_log = event_log_for(repo_root, args.timeline)
            events = load_events(event_log) if event_log.exists() else []
            start = next(
                (
                    event
                    for event in reversed(events)
                    if event.get("event") == "cmd_start"
                    and event.get("span_id") == args.span_id
                ),
                {},
            )
            event = common_event(args, "cmd_end", dt)
            event["span_id"] = args.span_id
            event["name"] = start.get("name")
            event["phase"] = start.get("phase") or active_phase_at(events, event["at"])
            event["status"] = args.status
            event["return_code"] = args.return_code
            if start.get("cmd"):
                event["cmd"] = start.get("cmd")
            append_event(event_log, event)
            seconds = (
                seconds_between(str(start.get("at")), event["at"])
                if start.get("at")
                else None
            )
            print_result(
                {
                    "timeline_id": event_log.name.removesuffix("_workflow_timeline_events.jsonl"),
                    "event_log": str(event_log),
                    "span_id": args.span_id,
                    "name": start.get("name"),
                    "phase": event.get("phase"),
                    "status": args.status,
                    "return_code": args.return_code,
                    "seconds": seconds,
                    "ended_at": event["at"],
                },
                as_json=args.json,
            )
            return 0

        if args.command in {"finish", "show"}:
            event_log = event_log_for(repo_root, args.timeline)
            if args.command == "finish":
                dt = parse_time(args.at)
                append_event(event_log, common_event(args, "finish", dt))
            events = load_events(event_log)
            report = build_report(repo_root, event_log, events)
            write_outputs(
                report,
                getattr(args, "json_out", None),
                getattr(args, "md_out", None),
                event_log,
            )
            if args.json:
                print(json.dumps(report, ensure_ascii=False, indent=2))
            else:
                print(render_markdown(report))
            return 0
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
