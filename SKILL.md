---
name: hyptest-workflow
description: 用于 https://github.com/wuyl10/riscv-hyp-tests-nhv5.git 仓库（nhv5.1 分支目录）的 hyptest 测试点到用例落地工作流。凡是涉及新增/修改 ai_test_cases 或 manual_test_cases 用例、更新 test_register.c、根据 test_point 回填映射、执行 compile_elf.py 和 get_result.py 编译批跑、分析 Spike/LinkNan 日志并做 default/manual/compile-only 分层决策时，都应触发此技能；当用户要求检查“类似测试点是否已经覆盖”“其它文件里有没有重复 case”“跨 test_point 文件排重/扩点”时也必须使用本技能；涉及规格/平台模型边界时通过 spec_profile=<name> 选择 references/spec_profiles/<name>.md。
---

# HYPTEST Workflow

该 skill 用于 `riscv-hyp-tests-nhv5` 的 hyptest 闭环工作：从 `test_point` 分析，到 `ai_test_cases/*.c` 或 `manual_test_cases/**/*.c` 落地、`test_register.c` 注册、单 case 编译/运行、日志归因、分层决策和轻量回填。

## Use This Skill When

- 根据 `test_point/*` 新增或修改 `ai_test_cases/*.c` / `manual_test_cases/**/*.c`
- 更新 `test_register.c`
- 跑 `compile_elf.py` / `get_result.py` 做单 case 或小批量验证
- 判断 case 应进入 `default` / `manual` / `compile-only`
- 回填 `test_point` 映射与短状态说明
- 检查跨 `test_point/*.md` 的类似测试点是否已覆盖
- 检查跨 `ai_test_cases/*.c` 与 `manual_test_cases/**/*.c` 的相似 case / 重复 case 风险

## Repo Anchors

See `references/repo_layout.md` for the current full layout, generated
directories, platform names, and environment variables. The fast anchors are:

- 框架宏与异常结构：`inc/rvh_test.h`
- 框架实现：`src/`
- 全局汇编入口：`asm/`
- 注册表：`test_register.c`
- AI 用例目录：`ai_test_cases/`
- 人工维护用例目录：`manual_test_cases/`
- 编译脚本：`compile_elf.py`
- 批跑脚本：`get_result.py`
- 项目规则：`test_point/Manual_Reference.md`
- 历史线索：`test_point/CRITICAL_ISSUES_LOG.md`

## Spec Profile Parameter

- `spec_profile=<name>` 选择规格 profile，读取 `references/spec_profiles/<name>.md`。
- 示例：`spec_profile=<name>` 对应 `references/spec_profiles/<name>.md`。
- 若用户给的是 profile 文件路径，按该文件路径读取；若只给名称，按 `references/spec_profiles/<name>.md` 解析。
- 显式 `spec_profile` 优先；未指定时读取 `references/spec_profiles/index.json` 的 `default_profile`。
- 最终交付摘要中应记录实际使用的 `spec_profile`。
- 需要确认 profile 路径时，使用 `python3 scripts/resolve_spec_profile.py --spec-profile <name>`。
- 可选 profile 与默认 profile 记录在 `references/spec_profiles/index.json`。
- `SKILL.md` 不承载 profile 专属规则；no-H、PMP 粒度、PMA/PBMT/MMIO、Spike gate 等具体规格只写在对应 profile 中。

## Test Point Scope

- `test_point_file` 是测试点容器文件，不是单个测试点；文件中的每个 `### PnX` 才是独立测试点条目。去重、扩写、复用、完成判定都按条目级进行，不按整个文件级进行。
- 若用户明确指定已有 `### PnX`，或明确表达“补已有测试点的用例 / 继续补 P6B / 给这个条目再补 case”，默认进入“补已有测试点模式”：围绕该条目做局部排重、局部补 case、局部回填，不为整个文件重新扫描新条目。
- 若用户只给 `test_point_file`，要求“补充测试点 / 去模块里继续找 bug 点 / new-case-only”且未指定已有条目，默认进入“新增测试点模式”：先扫描文件已有 `###` 条目与 `已实现 case`，再继续新增新的 `PnX` 条目与对应 case。
- 新条目编号默认沿当前文件前缀继续递增，例如 `*_points_7.md` 默认继续补 `P7D/P7E/...`；只有用户明确指定已有条目时，才回到旧条目做增补。

## Coverage Scope

- `coverage_scope=file`：仅围绕当前 `test_point_file` 或指定 `### PnX` 做局部测试点排重；适合“补已有测试点模式”。
- `coverage_scope=repo`：扫描全仓 `test_point/*.md` 做类似测试点覆盖检查；适合“新增测试点模式”和用户明确要求跨文件排重的任务。
- `case` 去重始终是 repo 级；`find_similar_cases.py` 始终搜索全仓 `ai_test_cases/*.c` 与 `manual_test_cases/**/*.c`。
- 详细口径、比较准则和命令模板见 `references/coverage_and_dedupe.md`。

## Quick Decision Table

| 场景 | 先查什么 | 初始处理 |
| --- | --- | --- |
| 新增普通架构 case | `references/spec_profiles/<spec_profile>.md` + 相似 case | 先争取 `default`，再编译/运行闭环 |
| PMA/PBMT/MMIO/cache/TLB/CBO 等 profile-sensitive case | `scripts/query_spec_profile.py` + profile 的 Spike gate | 若 `spike_gate_applicable=false`，不要用 official Spike 结果当 default gate |
| 访问 MMIO/Device 区间 | profile 的 MMIO responder 表 | 未确认 responder 会返回时，优先 `manual` / `compile-only` / `blocked` |
| 只改回填或注册状态 | `test_register.c` + `scripts/check_writeback_format.py --check-register` | 保证 `已实现 case` 状态与注册一致 |
| Spike/LinkNan 运行失败 | `references/build_run_debug.md` + `references/tiering_decision.md` | 先定位用例/assert/环境/model gap，再给 `reason_code` |
| 不确定 `reason_code` | `scripts/suggest_reason_code.py --symptom "<现象>"` | 把建议当候选，最终仍以日志和 profile 证据为准 |

## Non-Negotiables

- 写新 case 或判断 Spike 结果前，必须先确定 `spec_profile`（未指定则用 profile registry 中的 `default_profile`），再看 `references/spec_and_model_limits.md` 与 `references/spec_profiles/<spec_profile>.md`，明确规格来源、平台模型边界、`spike_gate_applicable` 和初始分层候选。
- 一个 case 函数只能有一个 `TEST_END(...)`。
- 只要本步骤要断言 `excpt.triggered/cause/tval`，都先调用 `TEST_SETUP_EXCEPT()`。
- 注册统一放在 `test_register.c`，不在 case 源文件末尾注册。
- 写新 case 前，先检索 2~5 个相似存量 case；模板只作骨架提醒，不替代存量 case 学习。
- `test_point` 默认只回填正文和 `已实现 case`；默认只写 `case_name`，必要时才补短状态。
- 禁止在 `test_point` 条目后追加审计式后半段块，例如 `[新增 case]`、`[质量门禁结果]`、`[分层结论]`、`[编译/运行统计]`。
- 新增 AI/批量生成 case 默认放 `ai_test_cases/*.c`；人工维护 case 按模块放 `manual_test_cases/<module>/`。
- 遇到历史大文件或用户明确不想继续堆叠时，必须新建主题明确的 case 文件承载新 case。
- 禁止默认输出 `exclude_check`。
- 禁止默认输出全量 Gate A-H；只有非 pass Gate 或用户明确要求时，才在最终交付摘要里输出 `[质量门禁结果]`。
- 禁止为 `default` case 默认单独输出 `[分层结论]`；只有 `manual` / `compile-only` / `blocked`，或用户明确要求时，才在最终交付摘要里输出 `decision_prelim` / `decision_final` / `reason_code`。
- 严禁文件级误判：不能把整个 `test_point_file` 当成单个测试点，也不能因为文件之前改过，就停止继续处理新条目或误把旧条目当新增结果。
- `new-case-only` 且未指定已有条目时，默认必须新增新的 `### PnX` 条目和新的 `ai_*` case；若属于补已有测试点模式，则默认优先在指定旧条目下补 case，不强行新增新条目。
- 若扫描后未发现新的高价值测试点，必须明确说明“未发现新的测试点 / 未新增 case”，不能把旧条目或旧 case 再次作为新增结果交付。
- 新增测试点前，必须先做测试点覆盖检查；`coverage_scope=repo` 时必须扫描全仓 `test_point/*.md`，不能只看当前文件就声称“全仓未覆盖”。
- 写新 case 前，必须同时做 repo 级 case 相似检索和精确唯一性检索；“相似检索未命中”和“函数名唯一”不是同一件事，两者都要留证据。

## Source Priority

冲突时按以下顺序执行：

1. `test_point/Manual_Reference.md`
2. `references/quality_gate.md` + `references/tiering_decision.md` + `references/reason_code_catalog.md` + `references/submission_card.md`
3. `references/spec_and_model_limits.md` + `references/spec_profiles/<spec_profile>.md` + `references/writing_cases.md` + `references/framework_usage_pitfalls.md` + `references/build_run_debug.md`
4. `references/repo_layout.md`
5. `test_point/CRITICAL_ISSUES_LOG.md`

补充：

- 顺序问题一律以日志和最小复现实验为准，不以视觉顺序经验做硬判断。
- 存量 case 是学习样本，不高于项目规则。

## What To Read

- 规格/profile 路由：`references/spec_and_model_limits.md`
- 当前规格/平台模型边界/Spike gate：`references/spec_profiles/<spec_profile>.md`
- 标准新 case 落地：`references/quick_execution.md` + `references/writing_cases.md` + `references/quality_gate.md`
- 框架 API / 注册 / 工具坑点：`references/framework_usage_pitfalls.md`
- 目录结构 / 平台名 / 环境变量：`references/repo_layout.md`
- 任务参数规格 / preflight：`references/task_input_schema.md`
- 失败定位：`references/build_run_debug.md` + `references/spec_and_model_limits.md` + `references/spec_profiles/<spec_profile>.md`
- 失败交接给 triage：`references/triage_handoff_schema.md`
- 非 default 分层：`references/tiering_decision.md` + `references/reason_code_catalog.md`
- 交付前复核：`references/submission_card.md`
- 涉及跨文件测试点覆盖检查或 case 去重：`references/coverage_and_dedupe.md`
- 需要 RTL 怀疑点示例：`references/rtl_bug_patterns.md`

## Workflow

1. 锁定输入：确认 `repo_root`、`test_point_file`、平台、case 名、目标分层和 `spec_profile`（未指定则用 profile registry 中的 `default_profile`）；必要时用 `scripts/check_env.py` 先检查平台环境。
   - 若输入字段较多或存在旧平台名/不确定模式，先用 `scripts/validate_task_request.py` 做 preflight。
2. 区分补已有测试点模式和新增测试点模式；`test_point_file` 是容器文件，每个 `### PnX` 才是独立测试点条目。
3. 按 `references/coverage_and_dedupe.md` 做测试点覆盖检查、repo 级 case 相似检索和精确唯一性检索。
4. 按 `references/spec_and_model_limits.md` 与 `references/spec_profiles/<spec_profile>.md` 判断规格来源、平台模型边界、`spike_gate_applicable` 和 default/manual/compile-only/blocked 候选，不要先写完再临时补判定。
5. 写或改 case：AI/批量生成 case 默认放在 `ai_test_cases/*.c`；人工维护 case 放在 `manual_test_cases/<module>/`；结构和断言以 `references/writing_cases.md` 为准。
6. 调整 `test_register.c` 注册状态，使其与目标分层一致。
7. 先做单 case 编译：
   ```bash
   python3 compile_elf.py --plat spike --name <case_name>
   ```
8. 非 `compile-only` 必须做单 case 运行；`compile-only` 允许 Gate D=`N/A`，但必须写明不运行原因。
9. 更新 `test_point`，默认只做轻量回填；详细模板和复用口径见 `references/writing_cases.md`。
10. 回填后建议执行：
   ```bash
   python3 scripts/check_writeback_format.py \
     --repo-root <repo_root> \
     --file <test_point_file> \
     --check-register
   ```

## Output Defaults

- 默认最终摘要至少包含：改动文件、case 名、编译结果、运行结果、关键日志路径。
- 默认最终摘要记录实际使用的 `spec_profile`。
- 只有存在非 pass Gate 或用户明确要求时，才在最终摘要里输出 `[质量门禁结果]`。
- 只有最终不是 `default`，或用户明确要求时，才在最终摘要里输出 `decision_prelim` / `decision_final` / `reason_code`。
- `compile-only` 必须显式写 Gate D=`N/A` 与不运行原因。
- 若任务是 `new-case-only` 但最终没有新增 `### PnX` 条目和新 case，必须在最终摘要里明确说明原因，不能把旧条目或旧 case 当成“新增结果”。

## Bundled Resources

完整资源清单见 `references/resource_index.md`。常用入口如下：

- `references/resource_index.md`
  - 文档、脚本、eval fixture 的完整索引；维护资源清单时只改这里。
- `references/maintainer_guide.md`
  - 修改 skill、profile、脚本、reason_code、eval 时的自检流程。
- `scripts/find_similar_cases.py`
  - 相似 case 检索；写新 case 前使用。
- `scripts/check_case_lint.py`
  - case 源文件结构检查；新增/改动文件可用 `--changed-only --strict-case-end`。
- `scripts/validate_task_request.py`
  - 校验任务输入参数、profile、平台名、路径和 task_mode 组合。
- `scripts/check_writeback_format.py`
  - `test_point` 轻量回填格式检查；可加 `--spec-profile` 做 profile-aware 警告。
- `scripts/query_spec_profile.py`
  - 查询 profile 里的 PMA/PBMT/MMIO 机器可读表，辅助判断 Spike gate 和初始分层。
- `scripts/suggest_reason_code.py`
  - 根据失败现象给 `reason_code` 候选；最终结论仍以日志、profile 和分层规则为准。
- `scripts/classify_failure_log.py`
  - 从失败日志抽取场景、错误点、候选 `reason_code` 和下一步动作。
- `scripts/make_triage_handoff.py`
  - 按 `references/triage_handoff_schema.md` 生成 workflow-to-triage 交接卡片。
- `scripts/check_hyptest_repo_migration.py`
  - 检查 hyptest 仓库是否仍残留旧目录、旧平台名或旧字段逻辑。
- `scripts/doctor.py`
  - 一条命令汇总 profile、文档链接、reason_code、环境和 quick self-check。
- `scripts/list_skill_commands.py`
  - 打印常用 skill 维护/使用命令。
- `scripts/skill_summary.py`
  - 汇总 skill profile、reference、script、eval asset 和推荐自检命令。
- `scripts/self_check.py`
  - skill 自检总入口；支持 `--quick` / `--repo` / `--platform-check` / `--full`。
