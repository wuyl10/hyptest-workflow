#!/usr/bin/env python3
"""Print common hyptest-workflow maintenance and usage commands."""

from __future__ import annotations

import argparse
import json
from typing import Any


COMMAND_GROUPS: list[dict[str, Any]] = [
    {
        "group": "self-check",
        "commands": [
            {
                "name": "quick",
                "cmd": "python3 scripts/self_check.py --quick --spec-profile <spec_profile>",
                "desc": "Fast skill checks; no simulator environment required.",
            },
            {
                "name": "repo",
                "cmd": "python3 scripts/self_check.py --repo --repo-root <repo_root> --spec-profile <spec_profile>",
                "desc": "Skill checks plus repo migration, CLI contract, and lint-baseline checks.",
            },
            {
                "name": "full",
                "cmd": "python3 scripts/self_check.py --full --repo-root <repo_root> --spec-profile <spec_profile> --json --json-out .hyptest_skill_reports/self_check_full.json --md-out .hyptest_skill_reports/self_check_full.md",
                "desc": "Full checks including real-repo similar-case eval, with saved reports.",
            },
        ],
    },
    {
        "group": "doctor",
        "commands": [
            {
                "name": "repo-health",
                "cmd": "python3 scripts/doctor.py --repo-root <repo_root> --pre-submit --strict --spec-profile <spec_profile>",
                "desc": "Grouped profile, skill, repo, CLI contract, lint-baseline, env and self-check health report.",
            },
            {
                "name": "task-request",
                "cmd": "python3 scripts/validate_task_request.py --repo-root <repo_root> --test-point-file <test_point_file> --platform spike --spec-profile <spec_profile> --task-mode new-case-only --new-case-count 1-3",
                "desc": "Validate task inputs before editing or running cases.",
            },
            {
                "name": "platform-env",
                "cmd": "python3 scripts/check_env.py --repo-root <repo_root> --platform all --explain --print-exports",
                "desc": "Check Spike and LinkNan environment variables and explain what each one is used for.",
            },
            {
                "name": "doctor-all",
                "cmd": "python3 scripts/doctor.py --repo-root <repo_root> --platform all --pre-submit --spec-profile <spec_profile>",
                "desc": "Run grouped doctor checks including both Spike and LinkNan env checks.",
            },
        ],
    },
    {
        "group": "case-workflow",
        "commands": [
            {
                "name": "similar-cases",
                "cmd": "python3 scripts/find_similar_cases.py --repo-root <repo_root> --query '<scenario terms>' --limit 5 --explain-score",
                "desc": "Search existing ai/manual case sources before writing a new case.",
            },
            {
                "name": "case-lint",
                "cmd": "python3 scripts/check_case_lint.py --repo-root <repo_root> --changed-only --strict-case-end --warnings-as-errors",
                "desc": "Lint changed case sources for harness-shape mistakes.",
            },
            {
                "name": "case-lint-baseline",
                "cmd": "python3 scripts/check_case_lint.py --repo-root <repo_root> --baseline assets/baselines/case_lint_baseline.json --warnings-as-errors",
                "desc": "Fail only on active lint issues not covered by the known baseline.",
            },
            {
                "name": "cli-contract",
                "cmd": "python3 scripts/check_hyptest_cli_contract.py --repo-root <repo_root>",
                "desc": "Check compile/run script platform names, case_elf_asm, required env vars and personal-path regressions.",
            },
            {
                "name": "repo-snapshot",
                "cmd": "python3 scripts/repo_snapshot.py --repo-root <repo_root>",
                "desc": "Print a read-only snapshot of case sources, register state, test_point coverage, artifacts and latest logs.",
            },
            {
                "name": "baseline-diff",
                "cmd": "python3 scripts/case_lint_baseline_diff.py --old <old_baseline.json> --new <new_baseline.json>",
                "desc": "Review added/removed lint baseline issues before accepting a new baseline.",
            },
            {
                "name": "writeback-check",
                "cmd": "python3 scripts/check_writeback_format.py --repo-root <repo_root> --file <test_point_file> --check-register --spec-profile <spec_profile>",
                "desc": "Validate lightweight test_point writeback and registration consistency.",
            },
        ],
    },
    {
        "group": "profile-and-tiering",
        "commands": [
            {
                "name": "profile-query",
                "cmd": "python3 scripts/query_spec_profile.py --spec-profile <spec_profile> --address <pa> --summary",
                "desc": "Summarize PMA/PBMT/MMIO profile rules for an address.",
            },
            {
                "name": "profile-registry",
                "cmd": "python3 scripts/check_spec_profile_registry.py",
                "desc": "Check the profile registry and default profile mapping.",
            },
            {
                "name": "new-profile",
                "cmd": "python3 scripts/new_spec_profile.py --name <profile_name> --title '<project/core title>' --update-registry",
                "desc": "Create a new spec profile skeleton from the template and register it.",
            },
            {
                "name": "profile-decision",
                "cmd": "python3 scripts/query_spec_profile.py --spec-profile <spec_profile> --address <pa> --decision-only",
                "desc": "Print only matching profile default_decision values.",
            },
            {
                "name": "reason-code",
                "cmd": "python3 scripts/suggest_reason_code.py --symptom '<failure symptom>'",
                "desc": "Suggest candidate reason_code values from a failure symptom.",
            },
            {
                "name": "reason-code-eval",
                "cmd": "python3 scripts/eval_reason_code_suggestions.py",
                "desc": "Check symptom-to-reason_code suggestion fixtures.",
            },
            {
                "name": "failure-log",
                "cmd": "python3 scripts/classify_failure_log.py --log-file <log> --json",
                "desc": "Extract scenario, error points, reason_code candidates and next actions from a failure log.",
            },
            {
                "name": "triage-handoff",
                "cmd": "python3 scripts/make_triage_handoff.py --log-file <log> --platform linknan --spec-profile <spec_profile> --json",
                "desc": "Create a workflow-to-triage handoff card for deeper failure analysis.",
            },
        ],
    },
    {
        "group": "maintenance",
        "commands": [
            {
                "name": "readme-check",
                "cmd": "python3 scripts/check_readme_commands.py",
                "desc": "Check README generated command block is in sync.",
            },
            {
                "name": "readme-update",
                "cmd": "python3 scripts/update_readme_commands.py",
                "desc": "Refresh README generated command block.",
            },
            {
                "name": "resource-index-check",
                "cmd": "python3 scripts/check_resource_index.py",
                "desc": "Check resource_index.md mentions public scripts and key assets.",
            },
            {
                "name": "manifest-check",
                "cmd": "python3 scripts/update_script_manifest.py --check",
                "desc": "Check assets/script_manifest.json is in sync with scripts/*.py.",
            },
            {
                "name": "manifest-update",
                "cmd": "python3 scripts/update_script_manifest.py --write",
                "desc": "Refresh assets/script_manifest.json after adding or removing scripts.",
            },
            {
                "name": "resource-index-update",
                "cmd": "python3 scripts/update_resource_index.py --write",
                "desc": "Refresh the generated resource coverage block in resource_index.md.",
            },
            {
                "name": "profile-portability",
                "cmd": "python3 scripts/eval_profile_portability.py",
                "desc": "Check generic skill surfaces do not hardcode the concrete default profile.",
            },
            {
                "name": "listed-command-help",
                "cmd": "python3 scripts/eval_listed_commands_help.py",
                "desc": "Check README/listed script commands still expose --help.",
            },
        ],
    },
    {
        "group": "cleanup",
        "commands": [
            {
                "name": "clean-generated",
                "cmd": "python3 scripts/clean_generated.py --repo-root <repo_root>",
                "desc": "Remove skill-local temporary/cache files.",
            },
        ],
    },
    {
        "group": "summary",
        "commands": [
            {
                "name": "skill-summary",
                "cmd": "python3 scripts/skill_summary.py",
                "desc": "Summarize profiles, references, scripts, eval assets, and recommended checks.",
            },
        ],
    },
]

README_DESC_ZH: dict[str, str] = {
    "quick": "快速检查 skill 本身；不需要模拟器环境。",
    "repo": "在 quick 基础上检查仓库迁移、CLI 约定和 lint baseline。",
    "full": "完整检查，包含真实仓库相似 case eval，并保存报告。",
    "repo-health": "按 profile、skill、repo、CLI、lint baseline、环境和 self-check 分组输出健康报告。",
    "task-request": "修改或运行 case 前校验任务输入参数。",
    "platform-env": "检查 Spike 和 LinkNan 环境变量，并说明各变量用途。",
    "doctor-all": "运行 doctor 分组检查，包含 Spike 和 LinkNan 环境检查。",
    "similar-cases": "写新 case 前搜索已有 ai/manual case 源文件。",
    "case-lint": "检查已改 case 源文件的测试框架结构问题。",
    "case-lint-baseline": "只对不在已知 baseline 内的活跃 lint 问题报错。",
    "cli-contract": "检查编译/运行脚本的平台名、case_elf_asm、必需环境变量和个人路径回归。",
    "repo-snapshot": "只读汇总 case 源、注册状态、test_point 覆盖、产物和最新日志。",
    "baseline-diff": "接受新 baseline 前查看新增/删除的 lint baseline 问题。",
    "writeback-check": "检查 test_point 轻量回填格式和注册一致性。",
    "profile-query": "按地址汇总 PMA/PBMT/MMIO profile 规则。",
    "profile-registry": "检查 profile 注册表和默认 profile 映射。",
    "new-profile": "基于模板创建新的 spec profile 骨架并写入注册表。",
    "profile-decision": "只输出匹配地址的 profile default_decision。",
    "reason-code": "根据失败现象给出候选 reason_code。",
    "reason-code-eval": "检查失败现象到 reason_code 建议的 eval 样例。",
    "failure-log": "从失败日志提取场景、错误点、候选 reason_code 和下一步动作。",
    "triage-handoff": "生成 workflow 交给 failure-triage 深入分析的交接卡片。",
    "readme-check": "检查 README 生成命令块是否同步。",
    "readme-update": "刷新 README 生成命令块。",
    "resource-index-check": "检查 resource_index.md 是否覆盖 public scripts 和关键资产。",
    "manifest-check": "检查 assets/script_manifest.json 是否与 scripts/*.py 同步。",
    "manifest-update": "新增或删除脚本后刷新 assets/script_manifest.json。",
    "resource-index-update": "刷新 resource_index.md 中的资源覆盖生成块。",
    "profile-portability": "检查通用 skill 入口没有写死具体默认 profile。",
    "listed-command-help": "检查 README/命令清单里的脚本仍然支持 --help。",
    "clean-generated": "删除 skill 本地临时文件和缓存文件。",
    "skill-summary": "汇总 profiles、references、scripts、eval assets 和推荐检查命令。",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="List common hyptest-workflow commands.")
    parser.add_argument("--json", action="store_true", help="Emit JSON report.")
    parser.add_argument("--markdown", action="store_true", help="Emit Markdown command section.")
    return parser.parse_args()


def render_markdown() -> str:
    lines: list[str] = []
    for group in COMMAND_GROUPS:
        lines.append(f"### {group['group']}")
        lines.append("")
        for item in group["commands"]:
            desc = README_DESC_ZH.get(str(item["name"]), item["desc"])
            lines.append(f"- `{item['name']}`: {desc}")
            lines.append("")
            lines.append("  ```bash")
            lines.append(f"  {item['cmd']}")
            lines.append("  ```")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    args = parse_args()
    if args.json:
        print(json.dumps({"groups": COMMAND_GROUPS}, ensure_ascii=False, indent=2))
        return 0
    if args.markdown:
        print(render_markdown(), end="")
        return 0

    for group in COMMAND_GROUPS:
        print(f"[{group['group']}]")
        for item in group["commands"]:
            print(f"  {item['name']}: {item['cmd']}")
            print(f"    {item['desc']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
