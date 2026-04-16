---
name: hyptest-workflow
description: 用于 https://github.com/wuyl10/riscv-hyp-tests-nhv5.git 仓库（nhv5.1 分支目录）的 hyptest 测试点到用例落地工作流。凡是涉及新增/修改 ai_test_cases 用例、更新 test_register.c、根据 test_point 回填映射、执行 compile_elf.py 和 get_result.py 编译批跑、分析 Spike 日志并做 default/manual/compile-only 分层决策时，都应触发此技能；当用户要求检查“类似测试点是否已经覆盖”“其它文件里有没有重复 case”“跨 test_point 文件排重/扩点”时也必须使用本技能。当前默认 no-H 策略：不依赖 H 特有指令/CSR；仓库内 HS 路径按项目约定作为 S 语义别名使用。
---

# HYPTEST Workflow

该 skill 用于 `riscv-hyp-tests-nhv5` 的 hyptest 闭环工作：从 `test_point` 分析，到 `ai_test_cases/*.c` 落地、`test_register.c` 注册、单 case 编译/运行、日志归因、分层决策和轻量回填。

## Use This Skill When

- 根据 `test_point/*` 新增或修改 `ai_test_cases/*.c`
- 更新 `test_register.c`
- 跑 `compile_elf.py` / `get_result.py` 做单 case 或小批量验证
- 判断 case 应进入 `default` / `manual` / `compile-only`
- 回填 `test_point` 映射与短状态说明
- 检查跨 `test_point/*.md` 的类似测试点是否已覆盖
- 检查跨 `ai_test_cases/*.c` 的相似 case / 重复 case 风险

## Repo Anchors

- 框架宏与异常结构：`inc/rvh_test.h`
- 注册表：`test_register.c`
- AI 用例目录：`ai_test_cases/`
- 编译脚本：`compile_elf.py`
- 批跑脚本：`get_result.py`
- 项目规则：`test_point/Manual_Reference.md`
- 历史线索：`test_point/CRITICAL_ISSUES_LOG.md`

## Test Point Scope

- `test_point_file` 是测试点容器文件，不是单个测试点；文件中的每个 `### PnX` 才是独立测试点条目。去重、扩写、复用、完成判定都按条目级进行，不按整个文件级进行。
- 若用户明确指定已有 `### PnX`，或明确表达“补已有测试点的用例 / 继续补 P6B / 给这个条目再补 case”，默认进入“补已有测试点模式”：围绕该条目做局部排重、局部补 case、局部回填，不为整个文件重新扫描新条目。
- 若用户只给 `test_point_file`，要求“补充测试点 / 去模块里继续找 bug 点 / new-case-only”且未指定已有条目，默认进入“新增测试点模式”：先扫描文件已有 `###` 条目与 `已实现 case`，再继续新增新的 `PnX` 条目与对应 case。
- 新条目编号默认沿当前文件前缀继续递增，例如 `*_points_7.md` 默认继续补 `P7D/P7E/...`；只有用户明确指定已有条目时，才回到旧条目做增补。

## Coverage Scope

- `coverage_scope=file`：仅围绕当前 `test_point_file` 或指定 `### PnX` 做局部测试点排重；适合“补已有测试点模式”。
- `coverage_scope=repo`：扫描全仓 `test_point/*.md` 做类似测试点覆盖检查；适合“新增测试点模式”和用户明确要求跨文件排重的任务。
- `case` 去重始终是 repo 级；`find_similar_cases.py` 始终搜索全仓 `ai_test_cases/*.c`。
- 详细口径、比较准则和命令模板见 `references/coverage_and_dedupe.md`。

## Non-Negotiables

- 默认按 no-H 策略写用例：不引入 H 特有指令/CSR；HS helper 按项目约定视为 S 语义别名。
- 一个 case 函数只能有一个 `TEST_END(...)`。
- 只要本步骤要断言 `excpt.triggered/cause/tval`，都先调用 `TEST_SETUP_EXCEPT()`。
- 注册统一放在 `test_register.c`，不在 `ai_test_cases/*.c` 末尾注册。
- 写新 case 前，先检索 2~5 个相似存量 case；模板只作骨架提醒，不替代存量 case 学习。
- `test_point` 默认只回填正文和 `已实现 case`；默认只写 `case_name`，必要时才补短状态。
- 禁止在 `test_point` 条目后追加审计式后半段块，例如 `[新增 case]`、`[质量门禁结果]`、`[分层结论]`、`[编译/运行统计]`。
- 遇到历史大文件或用户明确不想继续堆叠时，必须新建 `ai_test_cases/*.c` 文件承载新 case。
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
3. `references/rules_and_pitfalls.md` + `references/writing_cases.md` + `references/build_run_debug.md`
4. `test_point/CRITICAL_ISSUES_LOG.md`

补充：

- 顺序问题一律以日志和最小复现实验为准，不以视觉顺序经验做硬判断。
- 存量 case 是学习样本，不高于项目规则。

## What To Read

- 标准新 case 落地：`references/quick_execution.md` + `references/writing_cases.md` + `references/quality_gate.md`
- 失败定位：`references/build_run_debug.md` + `references/rules_and_pitfalls.md`
- 非 default 分层：`references/tiering_decision.md` + `references/reason_code_catalog.md`
- 交付前复核：`references/submission_card.md`
- 涉及跨文件测试点覆盖检查或 case 去重：`references/coverage_and_dedupe.md`

## Workflow

1. 锁定输入：确认 `repo_root`、`test_point_file`、平台、case 名、目标分层；先区分“容器文件”“本轮目标条目”和 `coverage_scope`。
   - 已指定已有条目，或用户明确是在补旧点：按补已有测试点模式执行。
   - 只给 `test_point_file` 且未指定已有条目：先扫描该文件已有 `###` 条目与 `已实现 case`，建立“已覆盖怀疑点 / 已覆盖场景轴 / 已落地 case”的清单；`new-case-only` 默认继续新增新的 `PnX` 条目。
   - 若用户要求查“类似测试点是否已覆盖”或“其它文件有没有重复”，默认把 `coverage_scope` 升级为 `repo`。
2. 按任务意图分流：
   - 补已有测试点模式：围绕目标条目做局部怀疑点细化、局部 case 排重、局部回填一致性检查。
   - 新增测试点模式：从目标模块继续扫描新的怀疑点，并先做测试点覆盖排重，再决定是否在当前文件追加新的 `PnX` 条目。
3. 按 `references/coverage_and_dedupe.md` 先做测试点覆盖检查，明确本轮是 `file` 级还是 `repo` 级，并判断是否真的存在“未覆盖的新测试点”。
4. 判断 default/manual/compile-only 候选，不要先写完再临时补判定。
5. 按 `references/coverage_and_dedupe.md` 做 repo 级 case 相似检索和精确唯一性检索，明确回答“是否已有相似实现”和“case 名是否唯一”。
6. 写或改 case：放在 `ai_test_cases/*.c`，结构和断言以 `references/writing_cases.md` 为准。
7. 调整 `test_register.c` 注册状态，使其与目标分层一致。
8. 先做单 case 编译：
   ```bash
   python3 compile_elf.py --plat spike --name <case_name>
   ```
9. 非 `compile-only` 必须做单 case 运行；`compile-only` 允许 Gate D=`N/A`，但必须写明不运行原因。
10. 更新 `test_point`：
   - 默认模板：`测试点 / 构建场景 / 已实现 case`
   - 需要 RTL/源码怀疑点时：`测试点 / 怀疑点 / 对应场景 / 已实现 case`
   - 若复用已有 case，固定只补两行 `复用依据`：`顺序一致性`、`断言一致性`
   - 新增测试点模式：新增新的 `### PnX` 条目，再在新条目下回填。
   - 补已有测试点模式：在目标旧条目下补充正文与 `已实现 case`，不要额外新增新的 `### PnX` 条目。
11. 回填后建议执行：
   ```bash
   python3 scripts/check_writeback_format.py \
     --repo-root <repo_root> \
     --file <test_point_file> \
     --check-register
   ```

## Output Defaults

- 默认最终摘要至少包含：改动文件、case 名、编译结果、运行结果、关键日志路径。
- 只有存在非 pass Gate 或用户明确要求时，才在最终摘要里输出 `[质量门禁结果]`。
- 只有最终不是 `default`，或用户明确要求时，才在最终摘要里输出 `decision_prelim` / `decision_final` / `reason_code`。
- `compile-only` 必须显式写 Gate D=`N/A` 与不运行原因。
- 若任务是 `new-case-only` 但最终没有新增 `### PnX` 条目和新 `ai_*` case，必须在最终摘要里明确说明原因，不能把旧条目或旧 case 当成“新增结果”。

## Bundled Resources

- `references/writing_cases.md`
  - 用例编写、断言覆盖、回填模板、反模式。
- `references/quick_execution.md`
  - 快速执行入口和 Gate 对照。
- `references/quality_gate.md`
  - Gate A-H 判定与最终结论模板。
- `references/tiering_decision.md`
  - `default` / `manual` / `compile-only` 自动裁决。
- `references/reason_code_catalog.md`
  - `reason_code` 标准来源。
- `references/build_run_debug.md`
  - 编译、运行、日志判读。
- `references/rules_and_pitfalls.md`
  - 项目规则与高频坑点。
- `references/coverage_and_dedupe.md`
  - 测试点覆盖检查、repo/file 级排重口径、case 相似检索和唯一性检索模板。
- `scripts/find_similar_cases.py`
  - 检索相似存量 case；搜索范围是全仓 `ai_test_cases/*.c`。支持 `--assert-only --emit-reading-pack`，以及 `--heading-pattern` / `--section-index` 做多条目 markdown 定位；`--from-file` 只用于提取查询词。
- `scripts/check_writeback_format.py`
  - 校验轻量回填格式，并可选核对 `test_register.c`。
- `scripts/eval_check_writeback_format.py`
  - 仅在修改写回校验逻辑时使用；跑固定 fixtures，避免把状态校验、注释注册识别和禁止块判定改坏。
- `scripts/eval_find_similar_cases.py`
  - 仅在修改检索逻辑时使用；跑固定 eval fixtures，避免把 `strong/weak/no_close`、Top1 排序和 markdown section 选择调坏。
- `assets/templates/new_case_template.c`
  - 最小骨架提醒，不是 case 设计真值。
