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
                "cmd": "python3 scripts/self_check.py --repo --repo-root $HYPTEST_HOME --spec-profile <spec_profile>",
                "desc": "Skill checks plus repo CLI contract, log contract, snapshot, and lint-baseline checks.",
            },
            {
                "name": "full",
                "cmd": "python3 scripts/self_check.py --full --repo-root $HYPTEST_HOME --spec-profile <spec_profile> --json --json-out $HYPTEST_HOME/.hyptest_workflow_skill/reports/self_check_full.json --md-out $HYPTEST_HOME/.hyptest_workflow_skill/reports/self_check_full.md",
                "desc": "Full checks including real-repo similar-case eval, with saved reports.",
            },
        ],
    },
    {
        "group": "doctor",
        "commands": [
            {
                "name": "repo-health",
                "cmd": "python3 scripts/doctor.py --repo-root $HYPTEST_HOME --pre-submit --strict --spec-profile <spec_profile>",
                "desc": "Grouped profile, skill, repo, CLI contract, lint-baseline, env and self-check health report.",
            },
            {
                "name": "task-request",
                "cmd": "python3 scripts/validate_task_request.py --repo-root $HYPTEST_HOME --test-point-file <test_point_file> --platform spike --spec-profile <spec_profile> --task-mode new-case-only --new-case-count 1-3",
                "desc": "Validate task inputs before editing or running cases; add --env HYPTEST_SPIKE_BIN=<path> only when the prompt explicitly overrides the runner path.",
            },
            {
                "name": "platform-env",
                "cmd": "python3 scripts/check_env.py --repo-root $HYPTEST_HOME --platform all --explain --print-exports",
                "desc": "Check hyptest, Spike, LinkNan and difftest-ref environment variables, plus the Nanhu source path derived from the LinkNan submodule.",
            },
            {
                "name": "doctor-all",
                "cmd": "python3 scripts/doctor.py --repo-root $HYPTEST_HOME --platform all --pre-submit --spec-profile <spec_profile>",
                "desc": "Run grouped doctor checks including both Spike and LinkNan env checks.",
            },
        ],
    },
    {
        "group": "case-workflow",
        "commands": [
            {
                "name": "similar-cases",
                "cmd": "python3 scripts/find_similar_cases.py --repo-root $HYPTEST_HOME --query '<scenario terms>' --limit 5 --explain-score",
                "desc": "Search existing ai/manual case sources before writing a new case.",
            },
            {
                "name": "repo-evidence-index",
                "cmd": "python3 scripts/repo_evidence_index.py --repo-root $HYPTEST_HOME --query '<scenario terms>' --json",
                "desc": "Build or reuse a repo-wide cached evidence index for cases, test_points and register status.",
            },
            {
                "name": "workflow-paths",
                "cmd": "python3 scripts/workflow_paths.py --repo-root $HYPTEST_HOME",
                "desc": "Print unified .hyptest_workflow_skill cache/report/memory/tmp paths.",
            },
            {
                "name": "case-preflight-pack",
                "cmd": "python3 scripts/case_preflight_pack.py --repo-root $HYPTEST_HOME --test-point-file <test_point_file> --platform spike --spec-profile <spec_profile> --task-mode new-case-only --new-case-count 1 --query '<scenario terms>' --md-out $HYPTEST_HOME/.hyptest_workflow_skill/reports/case_preflight.md --json-out $HYPTEST_HOME/.hyptest_workflow_skill/reports/case_preflight.json",
                "desc": "Collect task/profile/env/repo/similar-case context before writing a case, with conservative pack caching; add --env only for prompt-provided runner overrides.",
            },
            {
                "name": "case-skeleton",
                "cmd": "python3 scripts/make_case_skeleton.py --case <case_name> --preflight-json $HYPTEST_HOME/.hyptest_workflow_skill/reports/case_preflight.json --test-point-id <PnX>",
                "desc": "Generate a conservative C skeleton from preflight evidence without deciding case semantics.",
            },
            {
                "name": "case-name-suggest",
                "cmd": "python3 scripts/suggest_case_name.py --repo-root $HYPTEST_HOME --preflight-json $HYPTEST_HOME/.hyptest_workflow_skill/reports/case_preflight.json --prefix ai_micro --json",
                "desc": "Suggest case names from preflight/test_point terms and check repo-wide exact/similar name conflicts.",
            },
            {
                "name": "case-uniqueness",
                "cmd": "python3 scripts/check_case_uniqueness.py --repo-root $HYPTEST_HOME --case <case_name> --expect absent --json",
                "desc": "Check exact case-name uniqueness before editing by reusing the repo evidence cache instead of cold-scanning with rg.",
            },
            {
                "name": "case-lint",
                "cmd": "python3 scripts/check_case_lint.py --repo-root $HYPTEST_HOME --changed-only --strict-case-end --warnings-as-errors",
                "desc": "Lint changed case sources for harness-shape mistakes.",
            },
            {
                "name": "case-lint-baseline",
                "cmd": "python3 scripts/check_case_lint.py --repo-root $HYPTEST_HOME --baseline assets/baselines/case_lint_baseline.json --warnings-as-errors",
                "desc": "Fail only on active lint issues not covered by the known baseline.",
            },
            {
                "name": "cli-contract",
                "cmd": "python3 scripts/check_hyptest_cli_contract.py --repo-root $HYPTEST_HOME",
                "desc": "Check compile/run script platform names, case_elf_asm, required env vars and personal-path regressions.",
            },
            {
                "name": "repo-snapshot",
                "cmd": "python3 scripts/repo_snapshot.py --repo-root $HYPTEST_HOME",
                "desc": "Print a read-only snapshot of case sources, register state, test_point coverage, artifacts and latest logs.",
            },
            {
                "name": "baseline-diff",
                "cmd": "python3 scripts/case_lint_baseline_diff.py --old <old_baseline.json> --new <new_baseline.json>",
                "desc": "Review added/removed lint baseline issues before accepting a new baseline.",
            },
            {
                "name": "writeback-check",
                "cmd": "python3 scripts/check_writeback_format.py --repo-root $HYPTEST_HOME --file <test_point_file> --check-register --spec-profile <spec_profile>",
                "desc": "Validate lightweight test_point writeback and registration consistency.",
            },
            {
                "name": "case-postcheck-pack",
                "cmd": "python3 scripts/case_postcheck_pack.py --repo-root $HYPTEST_HOME --test-point-file <test_point_file> --case <case_name> --platform spike --spec-profile <spec_profile> --md-out $HYPTEST_HOME/.hyptest_workflow_skill/reports/case_postcheck.md --json-out $HYPTEST_HOME/.hyptest_workflow_skill/reports/case_postcheck.json",
                "desc": "Collect lint/writeback/register/artifact/log evidence after editing a case.",
            },
            {
                "name": "case-gate-pack",
                "cmd": "python3 scripts/case_gate_pack.py --repo-root $HYPTEST_HOME --test-point-file <test_point_file> --case <case_name> --platform spike --spec-profile <spec_profile> --md-out $HYPTEST_HOME/.hyptest_workflow_skill/reports/case_gate.md --json-out $HYPTEST_HOME/.hyptest_workflow_skill/reports/case_gate.json --postcheck-md-out $HYPTEST_HOME/.hyptest_workflow_skill/reports/case_postcheck.md --postcheck-json-out $HYPTEST_HOME/.hyptest_workflow_skill/reports/case_postcheck.json",
                "desc": "Compile/run one case, early-stop after compile failure, capture direct run logs, classify failures, and collect postcheck evidence with timing; add --env only for prompt-provided runner overrides.",
            },
            {
                "name": "batch-gate-pack",
                "cmd": "python3 scripts/case_batch_gate_pack.py --repo-root $HYPTEST_HOME --test-point-file <test_point_file> --case <case1> --case <case2> --platform spike --spec-profile <spec_profile> --json-out $HYPTEST_HOME/.hyptest_workflow_skill/reports/case_batch_gate.json --md-out $HYPTEST_HOME/.hyptest_workflow_skill/reports/case_batch_gate.md",
                "desc": "Run independent gate packs for multiple cases while keeping per-case evidence and tier decisions separate.",
            },
            {
                "name": "multi-platform-gate-pack",
                "cmd": "python3 scripts/case_multi_platform_gate_pack.py --repo-root $HYPTEST_HOME --test-point-file <test_point_file> --case <case_name> --platform spike --platform linknan --spec-profile <spec_profile> --json-out $HYPTEST_HOME/.hyptest_workflow_skill/reports/case_multi_platform_gate.json --md-out $HYPTEST_HOME/.hyptest_workflow_skill/reports/case_multi_platform_gate.md",
                "desc": "Run case_gate_pack.py for one case across multiple platforms in parallel without merging tier decisions.",
            },
            {
                "name": "submission-card",
                "cmd": "python3 scripts/make_case_submission_card.py --preflight-json $HYPTEST_HOME/.hyptest_workflow_skill/reports/case_preflight.json --gate-json $HYPTEST_HOME/.hyptest_workflow_skill/reports/case_gate.json --emit-final-draft --json-out $HYPTEST_HOME/.hyptest_workflow_skill/reports/submission_card.json --md-out $HYPTEST_HOME/.hyptest_workflow_skill/reports/submission_card.md",
                "desc": "Summarize preflight/gate/postcheck evidence into a final human-tiering card and optional delivery draft without deciding the tier.",
            },
            {
                "name": "timing-summary",
                "cmd": "python3 scripts/case_timing_summary.py --reports '$HYPTEST_HOME/.hyptest_workflow_skill/reports/*.json' --json-out $HYPTEST_HOME/.hyptest_workflow_skill/reports/timing_summary.json --md-out $HYPTEST_HOME/.hyptest_workflow_skill/reports/timing_summary.md",
                "desc": "Summarize timing and cache hit data from workflow pack reports.",
            },
            {
                "name": "workflow-ledger",
                "cmd": "python3 scripts/case_workflow_ledger.py --case <case_name> --preflight-json $HYPTEST_HOME/.hyptest_workflow_skill/reports/case_preflight.json --gate-json $HYPTEST_HOME/.hyptest_workflow_skill/reports/case_gate.json --submission-json $HYPTEST_HOME/.hyptest_workflow_skill/reports/submission_card.json --json-out $HYPTEST_HOME/.hyptest_workflow_skill/reports/workflow_ledger.json --md-out $HYPTEST_HOME/.hyptest_workflow_skill/reports/workflow_ledger.md",
                "desc": "Build an end-to-end timing and rework ledger for one case workflow without deciding tier.",
            },
            {
                "name": "workflow-timeline-start",
                "cmd": "python3 scripts/workflow_timeline.py start --repo-root $HYPTEST_HOME --timeline-id <case_or_task>_<timestamp> --test-point-file <test_point_file> --platform spike --spec-profile <spec_profile> --task-mode <task_mode> --target-module <module> --phase prompt_intake [--prompt-received-at <iso_time>]",
                "desc": "Start prompt-to-final phase timing before repo analysis or editing begins; optional prompt boundary records pre-start model time.",
            },
            {
                "name": "workflow-timeline-enter",
                "cmd": "python3 scripts/workflow_timeline.py enter --repo-root $HYPTEST_HOME --timeline <timeline_id> --phase <phase_name>",
                "desc": "Mark a major workflow phase boundary for prompt-to-final timing.",
            },
            {
                "name": "workflow-timeline-finish",
                "cmd": "python3 scripts/workflow_timeline.py finish --repo-root $HYPTEST_HOME --timeline <timeline_id> --json-out $HYPTEST_HOME/.hyptest_workflow_skill/reports/<timeline_id>_workflow_timeline.json --md-out $HYPTEST_HOME/.hyptest_workflow_skill/reports/<timeline_id>_workflow_timeline.md",
                "desc": "Finish prompt-to-final timing immediately before the final answer and write JSON/Markdown reports.",
            },
            {
                "name": "workflow-timed-cmd",
                "cmd": "python3 scripts/workflow_timed_cmd.py --repo-root $HYPTEST_HOME --timeline <timeline_id> --name <span_name> --phase <phase_name> -- <command> <args>",
                "desc": "Run a concrete command while recording command wall time inside the workflow timeline for attribution and gap diagnostics.",
            },
            {
                "name": "workflow-memory-append",
                "cmd": "python3 scripts/workflow_memory.py --repo-root $HYPTEST_HOME append --phase compile --status fixed --case <case_name> --module <module> --platform spike --symptom '<short symptom>' --fix '<short fix>'",
                "desc": "Append one local memory record for a failure, fix, or workflow lesson.",
            },
            {
                "name": "workflow-memory-query",
                "cmd": "python3 scripts/workflow_memory.py --repo-root $HYPTEST_HOME query --term '<keyword>' --limit 10",
                "desc": "Query local workflow memory before repeating a risky pattern; current source/log evidence still wins.",
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
                "name": "rtl-bug-history",
                "cmd": "python3 scripts/query_rtl_bug_history.py --module <module> --limit 10 --markdown",
                "desc": "Auto-invoked by skill in bug hunt tasks; results are one evidence source (commit heuristic misses non-'fix' commits and unmerged bugs). Do not rely on alone.",
            },
            {
                "name": "uncovered-bug-neighbors",
                "cmd": "python3 scripts/query_uncovered_bug_neighbors.py --module <module> --limit 20 --markdown",
                "desc": "Cross-reference RTL fix commits against test_point/*.md references; surface 'already fixed but no nearby test_point coverage' bug hunt candidates. Pairs with rtl-bug-history.",
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
                "cmd": "python3 scripts/clean_generated.py --repo-root $HYPTEST_HOME",
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
    "platform-env": "检查 hyptest、Spike、LinkNan、difftest-ref 环境变量，以及从 LinkNan submodule 推导出的 Nanhu 源码路径。",
    "doctor-all": "运行 doctor 分组检查，包含 Spike 和 LinkNan 环境检查。",
    "similar-cases": "写新 case 前搜索已有 ai/manual case 源文件。",
    "repo-evidence-index": "构建或复用全仓 case、test_point、注册状态证据索引缓存。",
    "workflow-paths": "显示统一的 .hyptest_workflow_skill cache/report/memory/tmp 路径。",
    "case-preflight-pack": "写 case 前聚合任务、规格/平台口径、环境、repo 快照和相似 case reading pack；覆盖范围可按 task_mode 自动推导。",
    "case-skeleton": "从 preflight 证据生成保守 C 骨架，不裁决 case 语义。",
    "case-name-suggest": "根据 preflight/test_point 术语建议 case 名，并做全仓精确/相似命名冲突检查。",
    "case-uniqueness": "写新 case 前检查精确函数名唯一性，默认复用 repo evidence cache，避免每次 rg 冷扫。",
    "case-lint": "检查已改 case 源文件的测试框架结构问题。",
    "case-lint-baseline": "只对不在已知 baseline 内的活跃 lint 问题报错。",
    "cli-contract": "检查编译/运行脚本的平台名、case_elf_asm、必需环境变量和个人路径回归。",
    "repo-snapshot": "只读汇总 case 源、注册状态、test_point 覆盖、产物和最新日志。",
    "baseline-diff": "接受新 baseline 前查看新增/删除的 lint baseline 问题。",
    "writeback-check": "检查 test_point 轻量回填格式和注册一致性。",
    "case-postcheck-pack": "写 case 后聚合 lint、回填、注册、产物和最新日志证据。",
    "case-gate-pack": "单 case 编译、运行并聚合 postcheck 证据；编译失败会跳过运行，本轮运行日志会直接捕获，失败日志会自动分类，同时记录每步耗时。",
    "batch-gate-pack": "对多个 case 分别跑 gate pack，保留每个 case 独立证据和独立分层边界。",
    "multi-platform-gate-pack": "对同一个 case 并行跑多个平台的 gate pack，但不合并成最终分层裁决。",
    "submission-card": "把 preflight/gate/postcheck 证据整理成最终交付卡片和可选交付草稿，但不自动裁决分层。",
    "timing-summary": "汇总 workflow pack 报告中的耗时和缓存命中率，用于观察瓶颈。",
    "workflow-ledger": "汇总单个 case 的端到端耗时、缓存命中和返工信号，不裁决分层。",
    "workflow-timeline-start": "在 repo 分析或编辑前启动 prompt-to-final 阶段耗时记录；可选 prompt 边界用于记录第一次工具调用前模型时间。",
    "workflow-timeline-enter": "记录 prompt-to-final workflow 的主要阶段切换。",
    "workflow-timeline-finish": "最终答复前结束 prompt-to-final 计时并写出 JSON/Markdown 报告。",
    "workflow-timed-cmd": "运行具体命令并把命令 wall time 记录到 timeline，区分真实命令耗时、命令前/后空档和阶段未归属时间。",
    "workflow-memory-append": "追加一条本地 workflow memory，用于记录失败、修复或流程教训。",
    "workflow-memory-query": "检索本地 workflow memory，作为避免重复踩坑的证据线索。",
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
    "clean-generated": "删除 workflow cache/report/tmp；默认保留 memory。",
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
