#!/usr/bin/env python3
"""Validate a `target_module` name against the RTL source tree with fuzzy fallbacks.

Pipeline (Bug Hunt Evidence §"开工前先校验 target_module 拼写"):

  1. Exact match (case-insensitive) against Scala file/dir names.
  2. Naming-convention expansion (snake_case ↔ CamelCase, strip `_`/`-`).
  3. Fuzzy candidates via Levenshtein distance (≤ 2).
  4. Empty candidates → exit 1, instruct user to correct spelling.

Step 2 auto-rewrites (no user confirmation); step 3 lists candidates so the
user must confirm before the agent proceeds.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Iterable


def _scala_stems(source_root: Path) -> list[str]:
    if not source_root.is_dir():
        return []
    stems: set[str] = set()
    for path in source_root.rglob("*.scala"):
        stems.add(path.stem)
    for entry in source_root.iterdir():
        if entry.is_dir():
            stems.add(entry.name)
    return sorted(stems)


def _match_exact(module: str, stems: Iterable[str]) -> list[str]:
    lower = module.lower()
    return sorted({s for s in stems if s.lower() == lower})


def _snake_to_camel(name: str) -> str:
    parts = [p for p in name.replace("-", "_").split("_") if p]
    return "".join(p[:1].upper() + p[1:].lower() for p in parts)


def _camel_to_snake(name: str) -> str:
    # Insert "_" before capitals preceded by a lowercase letter or digit.
    out: list[str] = []
    for i, ch in enumerate(name):
        if i > 0 and ch.isupper() and (name[i - 1].islower() or name[i - 1].isdigit()):
            out.append("_")
        out.append(ch.lower())
    return "".join(out)


def _expansion_candidates(module: str) -> list[str]:
    """Generate naming-convention variants of `module`.

    Order matters: preferred canonical form first.
    """
    seen: set[str] = set()
    candidates: list[str] = []

    def add(value: str) -> None:
        if value and value not in seen:
            seen.add(value)
            candidates.append(value)

    add(module)
    compact = module.replace("_", "").replace("-", "")
    add(compact)
    add(_snake_to_camel(module))
    add(_snake_to_camel(compact))
    add(_camel_to_snake(module))
    add(module.lower())
    add(module.upper())
    return candidates


def _match_expansion(module: str, stems: Iterable[str]) -> list[str]:
    stems_list = list(stems)
    stems_lower = {s.lower(): s for s in stems_list}
    hits: list[str] = []
    seen: set[str] = set()
    for variant in _expansion_candidates(module):
        real = stems_lower.get(variant.lower())
        if real and real not in seen:
            seen.add(real)
            hits.append(real)
    return hits


def _levenshtein(a: str, b: str, limit: int) -> int:
    if abs(len(a) - len(b)) > limit:
        return limit + 1
    if a == b:
        return 0
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        curr = [i] + [0] * len(b)
        row_min = i
        for j, cb in enumerate(b, 1):
            cost = 0 if ca == cb else 1
            curr[j] = min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + cost)
            if curr[j] < row_min:
                row_min = curr[j]
        if row_min > limit:
            return limit + 1
        prev = curr
    return prev[-1]


def _match_fuzzy(module: str, stems: Iterable[str], max_distance: int = 2, top: int = 3) -> list[dict]:
    lower = module.lower()
    scored: list[tuple[int, str]] = []
    for stem in stems:
        dist = _levenshtein(lower, stem.lower(), max_distance)
        if dist <= max_distance:
            scored.append((dist, stem))
    scored.sort(key=lambda x: (x[0], x[1]))
    return [{"candidate": stem, "edit_distance": dist} for dist, stem in scored[:top]]


def resolve_source_root(linknan_home: str | None) -> Path | None:
    if not linknan_home:
        return None
    candidate = Path(linknan_home).expanduser() / "dependencies" / "nanhu" / "src" / "main"
    return candidate if candidate.is_dir() else None


def build_report(
    module: str,
    source_root: Path | None,
    *,
    fuzzy_distance: int = 2,
) -> dict:
    report: dict = {
        "module": module,
        "source_root": str(source_root) if source_root else None,
        "verdict": "unknown",
        "resolved_module": None,
        "via": None,
        "exact_hits": [],
        "expansion_hits": [],
        "fuzzy_candidates": [],
        "next_action": None,
    }
    if source_root is None:
        report["verdict"] = "no_source_root"
        report["next_action"] = (
            "HYPTEST_LINKNAN_HOME or its dependencies/nanhu/src/main submodule is "
            "not initialized; cannot validate target_module spelling. Skip RTL reading "
            "or initialize the submodule before continuing."
        )
        return report

    stems = _scala_stems(source_root)
    exact = _match_exact(module, stems)
    if exact:
        report["exact_hits"] = exact
        report["verdict"] = "exact"
        report["resolved_module"] = exact[0]
        report["via"] = "exact"
        report["next_action"] = f"use module name `{exact[0]}`"
        return report

    expansion = _match_expansion(module, stems)
    if expansion:
        report["expansion_hits"] = expansion
        report["verdict"] = "expansion"
        report["resolved_module"] = expansion[0]
        report["via"] = "naming_convention"
        report["next_action"] = (
            f"auto-rewrite target_module to `{expansion[0]}` (snake↔Camel / alias expansion; "
            "no user confirmation needed)"
        )
        return report

    fuzzy = _match_fuzzy(module, stems, max_distance=fuzzy_distance)
    if fuzzy:
        report["fuzzy_candidates"] = fuzzy
        report["verdict"] = "fuzzy_candidates"
        top = fuzzy[0]["candidate"]
        report["next_action"] = (
            f"target_module=`{module}` not found; closest RTL candidates (edit distance ≤ "
            f"{fuzzy_distance}): "
            + ", ".join(f"`{c['candidate']}` (distance={c['edit_distance']})" for c in fuzzy)
            + f". Ask the user to confirm `{top}` or fix the spelling; do NOT auto-rewrite."
        )
        return report

    report["verdict"] = "miss"
    report["next_action"] = (
        f"target_module=`{module}` does not match any Scala module under the Nanhu source "
        "tree, and no fuzzy candidates were found. Stop and ask the user to confirm spelling."
    )
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate a target_module name against the Nanhu RTL source tree. "
            "Exact → naming-convention expansion → Levenshtein fuzzy candidates → stop."
        )
    )
    parser.add_argument("--module", required=True, help="Candidate target_module name (as given by the user).")
    parser.add_argument(
        "--linknan-home",
        default=os.environ.get("HYPTEST_LINKNAN_HOME"),
        help="LinkNan workspace root (defaults to $HYPTEST_LINKNAN_HOME).",
    )
    parser.add_argument(
        "--source-root",
        help="Override the Nanhu src/main path directly; takes precedence over --linknan-home.",
    )
    parser.add_argument(
        "--fuzzy-distance",
        type=int,
        default=2,
        help="Maximum edit distance for fuzzy candidate matching (default 2).",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON report instead of text.")
    return parser.parse_args()


def render_text(report: dict) -> str:
    verdict = report.get("verdict")
    lines: list[str] = []
    if verdict == "exact":
        lines.append(f"PASS target_module `{report['module']}` matched `{report['resolved_module']}` (exact)")
    elif verdict == "expansion":
        lines.append(
            f"PASS target_module `{report['module']}` rewritten to "
            f"`{report['resolved_module']}` via naming-convention expansion"
        )
    elif verdict == "fuzzy_candidates":
        lines.append(f"FAIL target_module `{report['module']}` not found; fuzzy candidates follow")
        for item in report.get("fuzzy_candidates", []):
            lines.append(f"  - {item['candidate']} (edit distance={item['edit_distance']})")
    elif verdict == "miss":
        lines.append(f"FAIL target_module `{report['module']}` not found and no fuzzy candidates")
    elif verdict == "no_source_root":
        lines.append(f"SKIP target_module `{report['module']}` — Nanhu source tree not available")
    else:
        lines.append(f"UNKNOWN verdict={verdict}")
    if report.get("source_root"):
        lines.append(f"source_root: {report['source_root']}")
    if report.get("next_action"):
        lines.append(f"next_action: {report['next_action']}")
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    if args.source_root:
        source_root = Path(args.source_root).expanduser()
        if not source_root.is_dir():
            source_root = None
    else:
        source_root = resolve_source_root(args.linknan_home)
    report = build_report(args.module, source_root, fuzzy_distance=args.fuzzy_distance)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_text(report))
    verdict = report.get("verdict")
    # PASS: exact or expansion. SKIP (no_source_root) treated as non-fatal.
    if verdict in ("exact", "expansion", "no_source_root"):
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
