#!/usr/bin/env python3
"""Run one command and record it as a workflow_timeline command span."""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
TIMELINE_SCRIPT = SCRIPT_DIR / "workflow_timeline.py"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Wrap a concrete shell command with workflow_timeline.py cmd-start/cmd-end "
            "so phase reports can separate command wall time from agent/overhead time."
        )
    )
    parser.add_argument("--repo-root", required=True, help="Path to hyptest repo root.")
    parser.add_argument("--timeline", required=True, help="Timeline id or event-log path.")
    parser.add_argument("--name", required=True, help="Short command/span name.")
    parser.add_argument("--phase", help="Explicit phase name. Defaults to active phase.")
    parser.add_argument("--span-id", help="Stable span id. Defaults to a generated id.")
    parser.add_argument("--note", default="", help="Short note stored on the command span.")
    parser.add_argument(
        "--shell",
        action="store_true",
        help="Run the command through the shell. Without this, command argv is executed directly.",
    )
    parser.add_argument("--json", action="store_true", help="Emit wrapper metadata as JSON.")
    parser.add_argument("cmd", nargs=argparse.REMAINDER, help="Command to run after `--`.")
    return parser.parse_args()


def clean_cmd(argv: list[str]) -> list[str]:
    if argv and argv[0] == "--":
        return argv[1:]
    return argv


def run_timeline(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(TIMELINE_SCRIPT), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def fail(message: str, *, as_json: bool, rc: int = 2) -> int:
    if as_json:
        print(json.dumps({"ok": False, "error": message}, ensure_ascii=False, indent=2))
    else:
        print(f"error: {message}", file=sys.stderr)
    return rc


def main() -> int:
    args = parse_args()
    cmd = clean_cmd(args.cmd)
    if not cmd:
        return fail("missing command after `--`", as_json=args.json)

    cmd_text = " ".join(cmd) if args.shell else shlex.join(cmd)
    start_args = [
        "cmd-start",
        "--repo-root",
        args.repo_root,
        "--timeline",
        args.timeline,
        "--name",
        args.name,
        "--cmd",
        cmd_text,
        "--json",
    ]
    if args.phase:
        start_args.extend(["--phase", args.phase])
    if args.span_id:
        start_args.extend(["--span-id", args.span_id])
    if args.note:
        start_args.extend(["--note", args.note])

    start = run_timeline(start_args)
    if start.returncode != 0:
        return fail(
            f"cmd-start failed rc={start.returncode}: {start.stderr or start.stdout}",
            as_json=args.json,
            rc=start.returncode,
        )
    try:
        start_payload = json.loads(start.stdout)
    except json.JSONDecodeError as exc:
        return fail(f"cmd-start did not emit JSON: {exc}", as_json=args.json)
    span_id = str(start_payload.get("span_id") or "")
    if not span_id:
        return fail("cmd-start did not return span_id", as_json=args.json)

    return_code: int
    try:
        completed = subprocess.run(
            " ".join(cmd) if args.shell else cmd,
            shell=args.shell,
            check=False,
        )
        return_code = completed.returncode
        status = "pass" if return_code == 0 else "fail"
    except KeyboardInterrupt:
        return_code = 130
        status = "interrupted"
        raise
    finally:
        end_args = [
            "cmd-end",
            "--repo-root",
            args.repo_root,
            "--timeline",
            args.timeline,
            "--span-id",
            span_id,
            "--status",
            locals().get("status", "interrupted"),
            "--return-code",
            str(locals().get("return_code", 130)),
            "--json",
        ]
        if args.note:
            end_args.extend(["--note", args.note])
        end = run_timeline(end_args)
        if end.returncode != 0:
            print(
                f"warning: cmd-end failed rc={end.returncode}: {end.stderr or end.stdout}",
                file=sys.stderr,
            )

    payload = {
        "ok": return_code == 0,
        "span_id": span_id,
        "name": args.name,
        "command": cmd_text,
        "return_code": return_code,
        "status": status,
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
