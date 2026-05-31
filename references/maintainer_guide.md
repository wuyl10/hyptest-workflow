# Maintainer Guide

本文给维护 `hyptest-workflow` skill 时使用。它不是 agent 执行规则入口；执行规则仍从 `SKILL.md` 开始。

## Table of Contents

- [修改原则](#修改原则)
- [新增或修改 Profile](#新增或修改-profile) — `new_spec_profile.py` + registry 登记
- [新增脚本](#新增脚本) — script_manifest + resource_index 流程
- [修改相似检索](#修改相似检索) — case_extractor / similar_case_* 模块
- [修改 Reason Code](#修改-reason-code) — catalog 与 JSON 同步
- [修改 Case Lint 或 Writeback Checker](#修改-case-lint-或-writeback-checker)
- [修改 Preflight/Postcheck Pack](#修改-preflightpostcheck-pack) — 维护原则与边界
- [Generated Cleanup](#generated-cleanup) — 清理 workflow 生成物
- [Cross-Skill Consistency](#cross-skill-consistency) — workflow↔failure-triage 一致性
- [推荐自检顺序](#推荐自检顺序) — `self_check --quick/--repo/--full` / `doctor`
- [修改 README 命令块](#修改-readme-命令块) — `update_readme_commands`
- [修改任务参数或失败日志规则](#修改任务参数或失败日志规则)

## 修改原则

- 通用流程放 `SKILL.md` 或通用 `references/*.md`。
- 项目/规格事实只放 `references/spec_profiles/<profile>.md`。
- 资源清单只维护在 `references/resource_index.md`，`SKILL.md` 只保留精简入口。
- 脚本能机器检查的规则，优先落到 `scripts/check_*.py` 或 `scripts/eval_*.py`。

## 新增或修改 Profile

1. 优先用脚手架生成新 profile：

```bash
python3 $HYPTEST_WORKFLOW_SKILL_HOME/scripts/new_spec_profile.py --name <name> --title "<project/core title>" --update-registry
```

也可以手工从 `references/spec_profiles/template.md` 复制新 profile。
2. 在 `references/spec_profiles/index.json` 注册 profile 名、路径、状态和说明。
3. 填写 `hyptest-profile` 机器可读块。
4. 填写 `hyptest-pma-pbmt-matrix` 和 `hyptest-mmio-responder-matrix` JSON fence。
5. 用查询脚本抽查关键窗口、PMA/PBMT 组合和 MMIO responder：

```bash
python3 $HYPTEST_WORKFLOW_SKILL_HOME/scripts/query_spec_profile.py --spec-profile <name> --address <pa> --json
python3 $HYPTEST_WORKFLOW_SKILL_HOME/scripts/query_spec_profile.py --spec-profile <name> --address <pa> --summary
python3 $HYPTEST_WORKFLOW_SKILL_HOME/scripts/query_spec_profile.py --spec-profile <name> --address <pa> --decision-only
python3 $HYPTEST_WORKFLOW_SKILL_HOME/scripts/query_spec_profile.py --spec-profile <name> --pma IO --pbmt IO
python3 $HYPTEST_WORKFLOW_SKILL_HOME/scripts/query_spec_profile.py --spec-profile <name> --responder-target <target>
```

6. 跑：

```bash
python3 $HYPTEST_WORKFLOW_SKILL_HOME/scripts/check_spec_profile_registry.py --policy all
python3 $HYPTEST_WORKFLOW_SKILL_HOME/scripts/check_spec_profile.py --spec-profile <name> --strict
python3 $HYPTEST_WORKFLOW_SKILL_HOME/scripts/eval_spec_profile_registry.py
python3 $HYPTEST_WORKFLOW_SKILL_HOME/scripts/eval_spec_profile.py
python3 $HYPTEST_WORKFLOW_SKILL_HOME/scripts/eval_profile_decisions.py
python3 $HYPTEST_WORKFLOW_SKILL_HOME/scripts/eval_profile_portability.py
```

不要把 NHV5.1AP 的 no-H、PMP 粒度、PMA/PBMT/MMIO 表直接写入通用文档。

## 新增脚本

1. 新脚本放 `scripts/`。
2. 用 `python3 $HYPTEST_WORKFLOW_SKILL_HOME/scripts/update_script_manifest.py --write` 刷新 `assets/script_manifest.json`。
3. 在 `references/resource_index.md` 加一条说明；不确定缺项时先跑 `python3 $HYPTEST_WORKFLOW_SKILL_HOME/scripts/update_resource_index.py --suggest`。
4. 如脚本属于维护/门禁检查，确认 `scripts/self_check.py` 会通过 manifest 覆盖它。
5. 若脚本暴露公共行为，补一个轻量 eval 或 smoke fixture。
6. 跑：

```bash
python3 $HYPTEST_WORKFLOW_SKILL_HOME/scripts/update_script_manifest.py --check
python3 $HYPTEST_WORKFLOW_SKILL_HOME/scripts/check_skill_consistency.py
python3 $HYPTEST_WORKFLOW_SKILL_HOME/scripts/check_resource_index.py
python3 $HYPTEST_WORKFLOW_SKILL_HOME/scripts/list_skill_commands.py
python3 $HYPTEST_WORKFLOW_SKILL_HOME/scripts/skill_summary.py
python3 $HYPTEST_WORKFLOW_SKILL_HOME/scripts/self_check.py --quick --spec-profile <spec_profile>
```

## 修改相似检索

相似检索模块拆分如下：

- `scripts/case_extractor.py`：case 提取、注册状态、helper 关系、缓存 builder。
- `scripts/similar_case_terms.py`：term/Markdown 提取和打分基础。
- `scripts/term_aliases.py`：term canonical key、alias 展开、canonical 去重。
- `scripts/markdown_sections.py`：Markdown heading section split/filter/index 选择。
- `scripts/similar_case_ranker.py`：相似度排序、多样性选择、retrieval assessment。
- `scripts/similar_case_render.py`：snippet、match note、reading pack。

修改后至少跑：

```bash
python3 $HYPTEST_WORKFLOW_SKILL_HOME/scripts/check_hyptest_cli_contract.py --repo-root $HYPTEST_HOME
python3 $HYPTEST_WORKFLOW_SKILL_HOME/scripts/eval_hyptest_cli_contract.py
python3 $HYPTEST_WORKFLOW_SKILL_HOME/scripts/eval_find_similar_cache.py
python3 $HYPTEST_WORKFLOW_SKILL_HOME/scripts/eval_workflow_smoke.py
```

有 hyptest 仓库时再跑：

```bash
python3 $HYPTEST_WORKFLOW_SKILL_HOME/scripts/eval_find_similar_cases.py --repo-root $HYPTEST_HOME
python3 $HYPTEST_WORKFLOW_SKILL_HOME/scripts/find_similar_cases.py --repo-root $HYPTEST_HOME --query "<scenario>" --limit 3 --explain-score
```

## 修改 Reason Code

1. 同时更新 `references/reason_code_catalog.md` 和 `assets/reason_codes.json`。
2. JSON 字段必须包含 `code`、`class`、`default_decision`、`meaning`、`typical_followup`、`owner`、`next_required_evidence`。
3. 更新 `scripts/suggest_reason_code.py` 的关键词映射，保证常见现象能返回合理候选。
4. 抽查一个现象：

```bash
python3 $HYPTEST_WORKFLOW_SKILL_HOME/scripts/suggest_reason_code.py --symptom "PMA PBMT MMIO no responder" --json
```

5. 跑：

```bash
python3 $HYPTEST_WORKFLOW_SKILL_HOME/scripts/check_reason_codes.py
```

## 修改 Case Lint 或 Writeback Checker

改 `scripts/check_case_lint.py` 后跑：

```bash
python3 $HYPTEST_WORKFLOW_SKILL_HOME/scripts/eval_check_case_lint.py
python3 $HYPTEST_WORKFLOW_SKILL_HOME/scripts/check_case_lint.py --repo-root $HYPTEST_HOME --changed-only --strict-case-end
python3 $HYPTEST_WORKFLOW_SKILL_HOME/scripts/check_case_lint.py --repo-root $HYPTEST_HOME --changed-only --strict-case-end --warnings-as-errors
python3 $HYPTEST_WORKFLOW_SKILL_HOME/scripts/check_case_lint.py --repo-root $HYPTEST_HOME --baseline assets/baselines/case_lint_baseline.json --warnings-as-errors
```

若历史 warning 太多，先生成 baseline，再只关注新增问题：

```bash
python3 $HYPTEST_WORKFLOW_SKILL_HOME/scripts/check_case_lint.py --repo-root $HYPTEST_HOME --write-baseline assets/baselines/case_lint_baseline.json
```

改 `scripts/check_writeback_format.py` 后跑：

```bash
python3 $HYPTEST_WORKFLOW_SKILL_HOME/scripts/eval_check_writeback_format.py
```

`test_register.c` 注册状态解析在 `scripts/writeback_register.py`，若修改该部分也跑同一个 eval。

对真实仓库做快速增量检查：

```bash
python3 $HYPTEST_WORKFLOW_SKILL_HOME/scripts/check_case_lint.py --repo-root $HYPTEST_HOME --changed-only --strict-case-end
python3 $HYPTEST_WORKFLOW_SKILL_HOME/scripts/check_writeback_format.py --repo-root $HYPTEST_HOME --file <test_point_file> --check-register --spec-profile <spec_profile>
```

## 修改 Preflight/Postcheck Pack

`scripts/repo_evidence_index.py`、`scripts/case_preflight_pack.py`、`scripts/case_postcheck_pack.py`、`scripts/case_gate_pack.py`、`scripts/case_batch_gate_pack.py`、`scripts/case_multi_platform_gate_pack.py`、`scripts/make_case_skeleton.py`、`scripts/suggest_case_name.py`、`scripts/make_case_submission_card.py`、`scripts/case_timing_summary.py` 和 `scripts/case_workflow_ledger.py` 是保质量提速入口，只聚合现有检查、执行、耗时、骨架、命名建议和证据，不重新定义质量口径。

修改后至少跑：

```bash
python3 $HYPTEST_WORKFLOW_SKILL_HOME/scripts/case_preflight_pack.py \
  --repo-root $HYPTEST_HOME \
  --test-point-file <test_point_file> \
  --platform spike \
  --spec-profile <spec_profile> \
  --task-mode new-case-only \
  --new-case-count 1 \
  --coverage-scope repo \
  --query memblock \
  --json

python3 $HYPTEST_WORKFLOW_SKILL_HOME/scripts/case_postcheck_pack.py \
  --repo-root $HYPTEST_HOME \
  --test-point-file <test_point_file> \
  --case <case_name> \
  --platform spike \
  --spec-profile <spec_profile> \
  --json

python3 $HYPTEST_WORKFLOW_SKILL_HOME/scripts/case_gate_pack.py \
  --repo-root $HYPTEST_HOME \
  --test-point-file <test_point_file> \
  --case <case_name> \
  --platform spike \
  --spec-profile <spec_profile> \
  --json

python3 $HYPTEST_WORKFLOW_SKILL_HOME/scripts/case_batch_gate_pack.py \
  --repo-root $HYPTEST_HOME \
  --test-point-file <test_point_file> \
  --case <case_name> \
  --platform spike \
  --spec-profile <spec_profile> \
  --json

python3 $HYPTEST_WORKFLOW_SKILL_HOME/scripts/make_case_submission_card.py \
  --preflight-json $HYPTEST_HOME/.hyptest_workflow_skill/reports/case_preflight.json \
  --gate-json $HYPTEST_HOME/.hyptest_workflow_skill/reports/case_gate.json \
  --emit-final-draft \
  --json

python3 $HYPTEST_WORKFLOW_SKILL_HOME/scripts/suggest_case_name.py \
  --repo-root $HYPTEST_HOME \
  --preflight-json $HYPTEST_HOME/.hyptest_workflow_skill/reports/case_preflight.json \
  --prefix ai_micro \
  --json

python3 $HYPTEST_WORKFLOW_SKILL_HOME/scripts/case_multi_platform_gate_pack.py \
  --repo-root $HYPTEST_HOME \
  --test-point-file <test_point_file> \
  --case <case_name> \
  --platform spike \
  --platform linknan \
  --spec-profile <spec_profile> \
  --json

python3 $HYPTEST_WORKFLOW_SKILL_HOME/scripts/case_timing_summary.py \
  --reports '$HYPTEST_HOME/.hyptest_workflow_skill/reports/*.json' \
  --json

python3 $HYPTEST_WORKFLOW_SKILL_HOME/scripts/case_workflow_ledger.py \
  --case <case_name> \
  --preflight-json $HYPTEST_HOME/.hyptest_workflow_skill/reports/case_preflight.json \
  --gate-json $HYPTEST_HOME/.hyptest_workflow_skill/reports/case_gate.json \
  --submission-json $HYPTEST_HOME/.hyptest_workflow_skill/reports/submission_card.json \
  --json
```

维护原则：

- 不在 pack 脚本里复制 `validate_task_request.py`、`find_similar_cases.py`、`check_case_lint.py`、`check_writeback_format.py` 的规则。
- `repo_evidence_index.py` 只能做 repo-wide 缓存索引，不能按模块缩小覆盖检查口径；缓存必须随 case 源、`test_point/**/*.md` 和 `test_register.c` 变化失效。
- pack 脚本可以整理证据、执行单 case gate 和给出 next steps，但最终分层仍以 profile、tiering decision 和日志证据为准。
- `case_gate_pack.py` 可调用 `compile_elf.py` / `get_result.py` / `case_postcheck_pack.py`，但不能把 runner returncode 直接等同于 default 分层。
- `case_gate_pack.py` 编译失败时可以跳过运行，但必须继续保留 postcheck 证据，并在 skipped/next_steps 中说明原因。
- `case_gate_pack.py` 可以优先使用本轮 run 后新出现/更新的日志做证据和分类；如果直接日志定位失败，仍要保留 postcheck/latest-log fallback。
- `case_gate_pack.py` 可以调用 `classify_failure_log.py` 辅助归因，但 classification 只能作为候选证据，不能作为最终分层。
- `case_batch_gate_pack.py` 必须保留每个 case 的独立 gate payload；默认应保守串行，只有用户或维护者明确确认产物隔离时才使用并行。
- `case_multi_platform_gate_pack.py` 必须保留每个平台的独立 gate payload，不能合并成最终 default/manual/compile-only 结论。
- `make_case_skeleton.py` 只能生成 TODO 骨架和参考线索，不能生成看似通过的断言，不能让 skeleton 绕过相似检索、profile 判断、编译运行或回填。
- `suggest_case_name.py` 只能建议命名和暴露同名/相似名风险，不能把“命名可用”当作 case 唯一性证明；repo 级相似 case 检索仍然必须执行。
- `case_preflight_pack.py` 的缓存必须保守失效；只要输入参数、目标 test_point、case 源、`test_register.c`、`test_point/**/*.md`、关键环境变量、toolchain 命中路径、profile 文件或相关 skill 脚本变化，就不能复用旧报告。
- `case_postcheck_pack.py` 的日志 fast path 必须保留 fallback；不能因为精确 glob 未命中就声称没有日志。
- `make_case_submission_card.py` 只能生成 evidence card 和 final summary draft，不能输出或暗示最终分层；`decision_final` 必须显式留给 workflow 最终确认。
- `case_timing_summary.py` 只能统计耗时和 cache hit/miss，不能作为质量门禁。
- `case_workflow_ledger.py` 只能统计端到端耗时、cache 命中和返工信号，不能作为质量门禁或最终分层依据。
- 三个 pack 脚本都应保留 `timing.total_seconds` 和 `timing.by_step`，便于长期观察耗时瓶颈。
- 新增输出字段时，同步 README 命令清单、resource index 和公共指南中的提速章节。

## Generated Cleanup

skill eval、自检和真实 hyptest 仓库的新 workflow 生成物都默认放在对应根目录下的 `.hyptest_workflow_skill/`。

验证结束后跑：

```bash
python3 $HYPTEST_WORKFLOW_SKILL_HOME/scripts/clean_generated.py --repo-root $HYPTEST_HOME
```

## Cross-Skill Consistency

`hyptest-workflow` 负责写 case、编译运行和分层初判。

`hyptest-failure-triage` 负责 selfcheck/stuck/difftest mismatch/FSDB/疑似 RTL bug 的失败闭环。

修改任一 skill 的触发词、旧路径、平台名或失败分类时，跑：

```bash
python3 $HYPTEST_WORKFLOW_SKILL_HOME/scripts/check_cross_skill_consistency.py
python3 $HYPTEST_WORKFLOW_SKILL_HOME/scripts/eval_joint_handoff.py
```

若 workflow 交给 triage 的字段变化，同时更新：

```text
references/triage_handoff_schema.md
<agents-skills-root>/hyptest-failure-triage/SKILL.md
```

`<agents-skills-root>` 是 skill 安装根目录，具体路径因机器而异；不要在 skill 文档里写死个人 `/nfs/...` 绝对路径。

## 推荐自检顺序

快速：

```bash
python3 $HYPTEST_WORKFLOW_SKILL_HOME/scripts/self_check.py --quick --spec-profile <spec_profile>
```

带真实 hyptest 仓库但不依赖仿真器环境：

```bash
python3 $HYPTEST_WORKFLOW_SKILL_HOME/scripts/self_check.py --repo --repo-root $HYPTEST_HOME --spec-profile <spec_profile>
```

检查平台环境变量：

```bash
python3 $HYPTEST_WORKFLOW_SKILL_HOME/scripts/self_check.py --platform-check --repo-root $HYPTEST_HOME --platform spike --spec-profile <spec_profile>
python3 $HYPTEST_WORKFLOW_SKILL_HOME/scripts/self_check.py --platform-check --repo-root $HYPTEST_HOME --platform linknan --spec-profile <spec_profile>
python3 $HYPTEST_WORKFLOW_SKILL_HOME/scripts/check_env.py --repo-root $HYPTEST_HOME --platform all --explain --print-exports
```

完整检查：

```bash
python3 $HYPTEST_WORKFLOW_SKILL_HOME/scripts/self_check.py --full --repo-root $HYPTEST_HOME --spec-profile <spec_profile>
python3 $HYPTEST_WORKFLOW_SKILL_HOME/scripts/self_check.py --full --repo-root $HYPTEST_HOME --spec-profile <spec_profile> --json --json-out $HYPTEST_HOME/.hyptest_workflow_skill/reports/self_check_full.json --md-out $HYPTEST_HOME/.hyptest_workflow_skill/reports/self_check_full.md
```

综合健康检查：

```bash
python3 $HYPTEST_WORKFLOW_SKILL_HOME/scripts/doctor.py --repo-root $HYPTEST_HOME --pre-submit --strict --platform spike --spec-profile <spec_profile>
```

## 修改 README 命令块

README 的“常用命令”由 `scripts/list_skill_commands.py` 生成。改命令清单后跑：

```bash
python3 $HYPTEST_WORKFLOW_SKILL_HOME/scripts/update_readme_commands.py
python3 $HYPTEST_WORKFLOW_SKILL_HOME/scripts/list_skill_commands.py --markdown
```

## 修改任务参数或失败日志规则

任务参数规格入口：

```bash
python3 $HYPTEST_WORKFLOW_SKILL_HOME/scripts/validate_task_request.py --repo-root $HYPTEST_HOME --test-point-file <test_point_file> --platform spike --spec-profile <spec_profile> --task-mode new-case-only --new-case-count 1-3
```

失败日志分类入口：

```bash
python3 $HYPTEST_WORKFLOW_SKILL_HOME/scripts/classify_failure_log.py --log-file <log> --json
python3 $HYPTEST_WORKFLOW_SKILL_HOME/scripts/eval_failure_log_workflow.py
```

## 修改触发条件或核心规则时跑 skill-creator Evals

`evals/evals.json` 是 skill 整体的端到端 prompt eval 集（和 `scripts/eval_*.py` 测脚本不同）。以下情况应该跑一次 benchmark：

- 改动 `SKILL.md` 的 `description`（触发边界）
- 改动 Non-Negotiables 的硬规则（尤其是 Workflow 步骤增删）
- 新增或移除 `scripts/` 下被 Workflow 默认调用的脚本
- 准备把 skill 发给其他团队/用户

操作（skill-creator 手册 §"Running and evaluating test cases"）：

1. 对每个 eval spawn 两个 subagent（with-skill / without-skill）
2. 输出保存到 `../hyptest-workflow-workspace/iteration-N/eval-<id>/{with_skill,without_skill}/outputs/`
3. 跑 grader → `grading.json`（每条 expectation 评 passed/evidence）
4. `aggregate_benchmark` 聚合成 `benchmark.json`
5. `eval-viewer/generate_review.py` 打开对比

更新 `evals/evals.json` 时需要保持：

- `id` 唯一递增
- expectations 里的宏名（`CAUSE_*` / `TEST_*` / `TEST_REGISTER`）、路径（`test_point/**/*.md`、`ai_test_cases/*.c`、`references/spec_profiles/*`）和 skill 当前实际一致
- 引用的 spec_profile 应和 `references/spec_profiles/index.json` 的 `default_profile` 一致
