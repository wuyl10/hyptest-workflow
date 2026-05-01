#!/usr/bin/env python3
"""Create a hyptest case skeleton from preflight evidence without deciding semantics."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


CASE_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a conservative C skeleton for a new hyptest case."
    )
    parser.add_argument("--case", required=True, help="New case function name.")
    parser.add_argument(
        "--preflight-json",
        help="Optional case_preflight_pack.py JSON report to cite references and profile.",
    )
    parser.add_argument("--test-point-id", help="Optional test point id/heading, e.g. P11H.")
    parser.add_argument(
        "--needs-exception",
        action="store_true",
        help="Include TEST_SETUP_EXCEPT() when the intended assertions inspect excpt.*.",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON payload.")
    parser.add_argument("--out", help="Write skeleton C snippet to this file.")
    return parser.parse_args()


def load_json(path_arg: str | None) -> dict[str, Any]:
    if not path_arg:
        return {}
    path = Path(path_arg).expanduser()
    if not path.is_file():
        raise FileNotFoundError(str(path))
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root is not an object: {path}")
    payload["_source_path"] = str(path)
    return payload


def collect_references(preflight: dict[str, Any]) -> list[dict[str, Any]]:
    similar = preflight.get("commands", {}).get("similar_cases", {}).get("payload", {})
    results = similar.get("top_results") or similar.get("results") or []
    refs: list[dict[str, Any]] = []
    for item in results[:5]:
        refs.append(
            {
                "case_name": item.get("case_name"),
                "file": item.get("file"),
                "line": item.get("line"),
                "register_status": item.get("register_status"),
                "reference_role": item.get("reference_role"),
            }
        )
    return refs


def infer_needs_exception(args: argparse.Namespace, preflight: dict[str, Any]) -> bool:
    if args.needs_exception:
        return True
    text = "\n".join(
        [
            str(preflight.get("target_test_point_excerpt", "")),
            " ".join(preflight.get("commands", {}).get("similar_cases", {}).get("payload", {}).get("focus_terms", [])),
        ]
    ).lower()
    return any(term in text for term in ("exception", "page fault", "access fault", "excpt", "tval", "cause"))


def render_skeleton(case_name: str, preflight: dict[str, Any], args: argparse.Namespace) -> str:
    spec_profile = preflight.get("spec_profile") or "<spec_profile>"
    test_point = args.test_point_id or "<test_point_id>"
    refs = collect_references(preflight)
    lines = [
        "#include <rvh_test.h>",
        "#include <stdbool.h>",
        "",
        "/*",
        f" * test_point: {test_point}",
        f" * spec_profile: {spec_profile}",
        " * This is a skeleton only. Fill scenario setup and assertions from the",
        " * target test_point, profile, and similar cases before compiling.",
    ]
    if refs:
        lines.append(" * reference cases:")
        for ref in refs[:3]:
            lines.append(
                f" * - {ref.get('case_name')} ({ref.get('file')}:{ref.get('line')}, {ref.get('register_status')})"
            )
    lines.extend([" */", "", f"bool {case_name}()", "{", "    TEST_START();", "", "    goto_priv(PRIV_M);", ""])
    lines.extend(
        [
            "    /* TODO: prepare data, page tables, PMP/PBMT/PMA state, or other environment. */",
        ]
    )
    if infer_needs_exception(args, preflight):
        lines.extend(["", "    TEST_SETUP_EXCEPT();"])
    else:
        lines.extend(["", "    /* Call TEST_SETUP_EXCEPT() before checking excpt.* fields. */"])
    lines.extend(
        [
            "",
            "    /* TODO: execute the target instruction/path. */",
            "",
            "    TEST_ASSERT(\"TODO: observable behavior\", false);",
            "",
            f"    TEST_END(\"{case_name}\");",
            "}",
            "",
        ]
    )
    return "\n".join(lines)


def build_payload(args: argparse.Namespace) -> dict[str, Any]:
    if not CASE_NAME_RE.match(args.case):
        raise ValueError(f"invalid C identifier for --case: {args.case}")
    preflight = load_json(args.preflight_json)
    skeleton = render_skeleton(args.case, preflight, args)
    return {
        "case": args.case,
        "preflight_json": preflight.get("_source_path"),
        "spec_profile": preflight.get("spec_profile"),
        "test_point_file": preflight.get("test_point_file"),
        "references": collect_references(preflight),
        "needs_exception": infer_needs_exception(args, preflight),
        "decision_note": (
            "This is a skeleton only. It does not prove uniqueness, correctness, "
            "compile success, run success, or tiering."
        ),
        "skeleton": skeleton,
    }


def main() -> int:
    args = parse_args()
    try:
        payload = build_payload(args)
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if args.out:
        path = Path(args.out).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(payload["skeleton"], encoding="utf-8")
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(payload["skeleton"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
