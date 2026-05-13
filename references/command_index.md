# Command Index

本文是 `hyptest-workflow` 的常用命令索引。README 只保留最高频入口；完整命令由 `scripts/list_skill_commands.py --markdown` 生成到这里。

命令中的 `$HYPTEST_HOME` 表示 `riscv-hyp-tests` 仓库根目录（具体 fork/分支以团队约定为准），`<test_point_file>` 表示测试点文件路径。脚本 CLI 参数仍叫 `--repo-root`，但它和 prompt 里的 `HYPTEST_HOME` 是同一含义：

```bash
python3 scripts/validate_task_request.py --repo-root $HYPTEST_HOME --test-point-file test_point/<file>.md ...
```

如果当前进程已经能读到 `HYPTEST_HOME`，命令可以直接写 `$HYPTEST_HOME`；如果没有设置，就把 `$HYPTEST_HOME` 替换成实际仓库路径。对外 prompt 和共享配置统一写 `HYPTEST_HOME`。

所有带 `--spec-profile <spec_profile>` 的命令都可以省略该参数；省略时使用 `references/spec_profiles/index.json` 中的 `default_profile`。需要复核实际解析结果时，先跑 `python3 scripts/resolve_spec_profile.py --spec-profile <spec_profile>`。

<!-- BEGIN GENERATED COMMANDS -->
### self-check

- `quick`: 快速检查 skill 本身；不需要模拟器环境。

  ```bash
  python3 scripts/self_check.py --quick --spec-profile <spec_profile>
  ```

- `repo`: 在 quick 基础上检查仓库迁移、CLI 约定和 lint baseline。

  ```bash
  python3 scripts/self_check.py --repo --repo-root $HYPTEST_HOME --spec-profile <spec_profile>
  ```

- `full`: 完整检查，包含真实仓库相似 case eval，并保存报告。

  ```bash
  python3 scripts/self_check.py --full --repo-root $HYPTEST_HOME --spec-profile <spec_profile> --json --json-out $HYPTEST_HOME/.hyptest_workflow_skill/reports/self_check_full.json --md-out $HYPTEST_HOME/.hyptest_workflow_skill/reports/self_check_full.md
  ```

### doctor

- `repo-health`: 按 profile、skill、repo、CLI、lint baseline、环境和 self-check 分组输出健康报告。

  ```bash
  python3 scripts/doctor.py --repo-root $HYPTEST_HOME --pre-submit --strict --spec-profile <spec_profile>
  ```

- `task-request`: 修改或运行 case 前校验任务输入参数。

  ```bash
  python3 scripts/validate_task_request.py --repo-root $HYPTEST_HOME --test-point-file <test_point_file> --platform spike --spec-profile <spec_profile> --task-mode new-case-only --new-case-count 1-3
  ```

- `platform-env`: 检查 hyptest、Spike、LinkNan、difftest-ref 环境变量，以及从 LinkNan submodule 推导出的 Nanhu 源码路径。

  ```bash
  python3 scripts/check_env.py --repo-root $HYPTEST_HOME --platform all --explain --print-exports
  ```

- `target-module-check`: Bug-hunt prerequisite: validate target_module name with exact/CamelCase/Levenshtein fuzzy matching against the Nanhu RTL source tree before reading source.

  ```bash
  python3 scripts/check_target_module.py --module <target_module>
  ```

- `nongate-summary`: Compact Spike-nongate keyword summary for a target_module, driven by the profile's hyptest-nongate-keywords block. Used at Workflow step 4 to avoid reading the full profile markdown.

  ```bash
  python3 scripts/query_spec_profile.py --spec-profile <spec_profile> --nongate-summary --match-module <target_module> --json
  ```

- `manual-reference-topic`: Workflow step 16 pre-check: decide whether to append a new Manual_Reference entry by consulting profile nongate keywords, memory confirmed entries, and unresolved MR entries. Returns verdict = profile_covered / memory_confirmed / manual_reference_open / new_entry_needed.

  ```bash
  python3 scripts/check_manual_reference_topic.py --repo-root $HYPTEST_HOME --case <case_name> --module <target_module> --topic <kw1> --topic <kw2> --spec-profile <spec_profile>
  ```

- `doctor-all`: 运行 doctor 分组检查，包含 Spike 和 LinkNan 环境检查。

  ```bash
  python3 scripts/doctor.py --repo-root $HYPTEST_HOME --platform all --pre-submit --spec-profile <spec_profile>
  ```

### case-workflow

- `similar-cases`: 写新 case 前搜索已有 ai/manual case 源文件。

  ```bash
  python3 scripts/find_similar_cases.py --repo-root $HYPTEST_HOME --query '<scenario terms>' --limit 5 --explain-score
  ```

- `repo-evidence-index`: 构建或复用全仓 case、test_point、注册状态证据索引缓存。

  ```bash
  python3 scripts/repo_evidence_index.py --repo-root $HYPTEST_HOME --query '<scenario terms>' --json
  ```

- `workflow-paths`: 显示统一的 .hyptest_workflow_skill cache/report/memory/tmp 路径。

  ```bash
  python3 scripts/workflow_paths.py --repo-root $HYPTEST_HOME
  ```

- `case-preflight-pack`: 写 case 前聚合任务、规格/平台口径、环境、repo 快照和相似 case reading pack；覆盖范围可按 task_mode 自动推导。

  ```bash
  python3 scripts/case_preflight_pack.py --repo-root $HYPTEST_HOME --test-point-file <test_point_file> --platform spike --spec-profile <spec_profile> --task-mode new-case-only --new-case-count 1 --query '<scenario terms>' --md-out $HYPTEST_HOME/.hyptest_workflow_skill/reports/case_preflight.md --json-out $HYPTEST_HOME/.hyptest_workflow_skill/reports/case_preflight.json
  ```

- `case-skeleton`: 从 preflight 证据生成保守 C 骨架，不裁决 case 语义。

  ```bash
  python3 scripts/make_case_skeleton.py --case <case_name> --preflight-json $HYPTEST_HOME/.hyptest_workflow_skill/reports/case_preflight.json --test-point-id <PnX>
  ```

- `case-name-suggest`: 根据 preflight/test_point 术语建议 case 名，并做全仓精确/相似命名冲突检查。

  ```bash
  python3 scripts/suggest_case_name.py --repo-root $HYPTEST_HOME --preflight-json $HYPTEST_HOME/.hyptest_workflow_skill/reports/case_preflight.json --prefix ai_micro --json
  ```

- `case-uniqueness`: 写新 case 前检查精确函数名唯一性，默认复用 repo evidence cache，避免每次 rg 冷扫。

  ```bash
  python3 scripts/check_case_uniqueness.py --repo-root $HYPTEST_HOME --case <case_name> --expect absent --json
  ```

- `case-lint`: 检查已改 case 源文件的测试框架结构问题。

  ```bash
  python3 scripts/check_case_lint.py --repo-root $HYPTEST_HOME --changed-only --strict-case-end --warnings-as-errors
  ```

- `case-lint-baseline`: 只对不在已知 baseline 内的活跃 lint 问题报错。

  ```bash
  python3 scripts/check_case_lint.py --repo-root $HYPTEST_HOME --baseline assets/baselines/case_lint_baseline.json --warnings-as-errors
  ```

- `cli-contract`: 检查编译/运行脚本的平台名、case_elf_asm、必需环境变量和个人路径回归。

  ```bash
  python3 scripts/check_hyptest_cli_contract.py --repo-root $HYPTEST_HOME
  ```

- `repo-snapshot`: 只读汇总 case 源、注册状态、test_point 覆盖、产物和最新日志。

  ```bash
  python3 scripts/repo_snapshot.py --repo-root $HYPTEST_HOME
  ```

- `baseline-diff`: 接受新 baseline 前查看新增/删除的 lint baseline 问题。

  ```bash
  python3 scripts/case_lint_baseline_diff.py --old <old_baseline.json> --new <new_baseline.json>
  ```

- `writeback-check`: 检查 test_point 轻量回填格式和注册一致性。

  ```bash
  python3 scripts/check_writeback_format.py --repo-root $HYPTEST_HOME --file <test_point_file> --check-register --spec-profile <spec_profile>
  ```

- `case-postcheck-pack`: 写 case 后聚合 lint、回填、注册、产物和最新日志证据。

  ```bash
  python3 scripts/case_postcheck_pack.py --repo-root $HYPTEST_HOME --test-point-file <test_point_file> --case <case_name> --platform spike --spec-profile <spec_profile> --md-out $HYPTEST_HOME/.hyptest_workflow_skill/reports/case_postcheck.md --json-out $HYPTEST_HOME/.hyptest_workflow_skill/reports/case_postcheck.json
  ```

- `case-gate-pack`: 单 case 编译、运行并聚合 postcheck 证据；编译失败会跳过运行，本轮运行日志会直接捕获，失败日志会自动分类，同时记录每步耗时。

  ```bash
  python3 scripts/case_gate_pack.py --repo-root $HYPTEST_HOME --test-point-file <test_point_file> --case <case_name> --platform spike --spec-profile <spec_profile> --md-out $HYPTEST_HOME/.hyptest_workflow_skill/reports/case_gate.md --json-out $HYPTEST_HOME/.hyptest_workflow_skill/reports/case_gate.json --postcheck-md-out $HYPTEST_HOME/.hyptest_workflow_skill/reports/case_postcheck.md --postcheck-json-out $HYPTEST_HOME/.hyptest_workflow_skill/reports/case_postcheck.json
  ```

- `batch-gate-pack`: 对多个 case 分别跑 gate pack，保留每个 case 独立证据和独立分层边界。

  ```bash
  python3 scripts/case_batch_gate_pack.py --repo-root $HYPTEST_HOME --test-point-file <test_point_file> --case <case1> --case <case2> --platform spike --spec-profile <spec_profile> --json-out $HYPTEST_HOME/.hyptest_workflow_skill/reports/case_batch_gate.json --md-out $HYPTEST_HOME/.hyptest_workflow_skill/reports/case_batch_gate.md
  ```

- `multi-platform-gate-pack`: 对同一个 case 并行跑多个平台的 gate pack，但不合并成最终分层裁决。

  ```bash
  python3 scripts/case_multi_platform_gate_pack.py --repo-root $HYPTEST_HOME --test-point-file <test_point_file> --case <case_name> --platform spike --platform linknan --spec-profile <spec_profile> --json-out $HYPTEST_HOME/.hyptest_workflow_skill/reports/case_multi_platform_gate.json --md-out $HYPTEST_HOME/.hyptest_workflow_skill/reports/case_multi_platform_gate.md
  ```

- `submission-card`: 把 preflight/gate/postcheck 证据整理成最终交付卡片和可选交付草稿，但不自动裁决分层。

  ```bash
  python3 scripts/make_case_submission_card.py --preflight-json $HYPTEST_HOME/.hyptest_workflow_skill/reports/case_preflight.json --gate-json $HYPTEST_HOME/.hyptest_workflow_skill/reports/case_gate.json --emit-final-draft --json-out $HYPTEST_HOME/.hyptest_workflow_skill/reports/submission_card.json --md-out $HYPTEST_HOME/.hyptest_workflow_skill/reports/submission_card.md
  ```

- `timing-summary`: 汇总 workflow pack 报告中的耗时和缓存命中率，用于观察瓶颈。

  ```bash
  python3 scripts/case_timing_summary.py --reports '$HYPTEST_HOME/.hyptest_workflow_skill/reports/*.json' --json-out $HYPTEST_HOME/.hyptest_workflow_skill/reports/timing_summary.json --md-out $HYPTEST_HOME/.hyptest_workflow_skill/reports/timing_summary.md
  ```

- `workflow-ledger`: 汇总单个 case 的端到端耗时、缓存命中和返工信号，不裁决分层。

  ```bash
  python3 scripts/case_workflow_ledger.py --case <case_name> --preflight-json $HYPTEST_HOME/.hyptest_workflow_skill/reports/case_preflight.json --gate-json $HYPTEST_HOME/.hyptest_workflow_skill/reports/case_gate.json --submission-json $HYPTEST_HOME/.hyptest_workflow_skill/reports/submission_card.json --json-out $HYPTEST_HOME/.hyptest_workflow_skill/reports/workflow_ledger.json --md-out $HYPTEST_HOME/.hyptest_workflow_skill/reports/workflow_ledger.md
  ```

- `workflow-timeline-start`: 在 repo 分析或编辑前启动 prompt-to-final 阶段耗时记录；可选 prompt 边界用于记录第一次工具调用前模型时间。

  ```bash
  python3 scripts/workflow_timeline.py start --repo-root $HYPTEST_HOME --timeline-id <case_or_task>_<timestamp> --test-point-file <test_point_file> --platform spike --spec-profile <spec_profile> --task-mode <task_mode> --target-module <module> --phase prompt_intake [--prompt-received-at <iso_time>]
  ```

- `workflow-timeline-enter`: 记录 prompt-to-final workflow 的主要阶段切换。

  ```bash
  python3 scripts/workflow_timeline.py enter --repo-root $HYPTEST_HOME --timeline <timeline_id> --phase <phase_name>
  ```

- `workflow-timeline-finish`: 最终答复前结束 prompt-to-final 计时并写出 JSON/Markdown 报告。

  ```bash
  python3 scripts/workflow_timeline.py finish --repo-root $HYPTEST_HOME --timeline <timeline_id> --json-out $HYPTEST_HOME/.hyptest_workflow_skill/reports/<timeline_id>_workflow_timeline.json --md-out $HYPTEST_HOME/.hyptest_workflow_skill/reports/<timeline_id>_workflow_timeline.md
  ```

- `workflow-timed-cmd`: 运行具体命令并把命令 wall time 记录到 timeline，区分真实命令耗时、命令前/后空档和阶段未归属时间。

  ```bash
  python3 scripts/workflow_timed_cmd.py --repo-root $HYPTEST_HOME --timeline <timeline_id> --name <span_name> --phase <phase_name> -- <command> <args>
  ```

- `workflow-memory-append`: 追加一条本地 workflow memory，用于记录失败、修复或流程教训。

  ```bash
  python3 scripts/workflow_memory.py --repo-root $HYPTEST_HOME append --phase compile --status fixed --case <case_name> --module <module> --platform spike --symptom '<short symptom>' --fix '<short fix>'
  ```

- `workflow-memory-query`: 检索本地 workflow memory，作为避免重复踩坑的证据线索。

  ```bash
  python3 scripts/workflow_memory.py --repo-root $HYPTEST_HOME query --term '<keyword>' --limit 10
  ```

### profile-and-tiering

- `profile-query`: 按地址汇总 PMA/PBMT/MMIO profile 规则。

  ```bash
  python3 scripts/query_spec_profile.py --spec-profile <spec_profile> --address <pa> --summary
  ```

- `profile-registry`: 检查 profile 注册表和默认 profile 映射。

  ```bash
  python3 scripts/check_spec_profile_registry.py
  ```

- `new-profile`: 基于模板创建新的 spec profile 骨架并写入注册表。

  ```bash
  python3 scripts/new_spec_profile.py --name <profile_name> --title '<project/core title>' --update-registry
  ```

- `profile-decision`: 只输出匹配地址的 profile default_decision。

  ```bash
  python3 scripts/query_spec_profile.py --spec-profile <spec_profile> --address <pa> --decision-only
  ```

- `reason-code`: 根据失败现象给出候选 reason_code。

  ```bash
  python3 scripts/suggest_reason_code.py --symptom '<failure symptom>'
  ```

- `reason-code-eval`: 检查失败现象到 reason_code 建议的 eval 样例。

  ```bash
  python3 scripts/eval_reason_code_suggestions.py
  ```

- `failure-log`: 从失败日志提取场景、错误点、候选 reason_code 和下一步动作。

  ```bash
  python3 scripts/classify_failure_log.py --log-file <log> --json
  ```

- `triage-handoff`: 生成 workflow 交给 failure-triage 深入分析的交接卡片。

  ```bash
  python3 scripts/make_triage_handoff.py --log-file <log> --platform linknan --spec-profile <spec_profile> --json
  ```

### maintenance

- `readme-check`: 检查 README 生成命令块是否同步。

  ```bash
  python3 scripts/check_readme_commands.py
  ```

- `readme-update`: 刷新 README 生成命令块。

  ```bash
  python3 scripts/update_readme_commands.py
  ```

- `resource-index-check`: 检查 resource_index.md 是否覆盖 public scripts 和关键资产。

  ```bash
  python3 scripts/check_resource_index.py
  ```

- `manifest-check`: 检查 assets/script_manifest.json 是否与 scripts/*.py 同步。

  ```bash
  python3 scripts/update_script_manifest.py --check
  ```

- `manifest-update`: 新增或删除脚本后刷新 assets/script_manifest.json。

  ```bash
  python3 scripts/update_script_manifest.py --write
  ```

- `resource-index-update`: 刷新 resource_index.md 中的资源覆盖生成块。

  ```bash
  python3 scripts/update_resource_index.py --write
  ```

- `profile-portability`: 检查通用 skill 入口没有写死具体默认 profile。

  ```bash
  python3 scripts/eval_profile_portability.py
  ```

- `listed-command-help`: 检查 README/命令清单里的脚本仍然支持 --help。

  ```bash
  python3 scripts/eval_listed_commands_help.py
  ```

### cleanup

- `clean-generated`: 删除 workflow cache/report/tmp；默认保留 memory。

  ```bash
  python3 scripts/clean_generated.py --repo-root $HYPTEST_HOME
  ```

### summary

- `skill-summary`: 汇总 profiles、references、scripts、eval assets 和推荐检查命令。

  ```bash
  python3 scripts/skill_summary.py
  ```
<!-- END GENERATED COMMANDS -->
