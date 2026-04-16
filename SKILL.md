---
name: hyptest-workflow
description: 用于 https://github.com/wuyl10/riscv-hyp-tests-nhv5.git 仓库（nhv5.1 分支目录）的 hyptest 测试点到用例落地工作流。凡是涉及新增/修改 ai_test_cases 用例、更新 test_register.c、根据 test_point 回填映射、执行 compile_elf.py 和 get_result.py 编译批跑、分析 Spike 日志并做 default/manual/compile-only 分层决策时，都应触发此技能。当前默认 no-H 策略：不依赖 H 特有指令/CSR；仓库内 HS 路径按项目约定作为 S 语义别名使用。
---

# HYPTEST Workflow

该 skill 用于 `riscv-hyp-tests-nhv5` 的 hyptest 闭环工作：从 `test_point` 分析，到 `ai_test_cases/*.c` 落地、`test_register.c` 注册、单 case 编译/运行、日志归因、分层决策和轻量回填。

## Use This Skill When

- 根据 `test_point/*` 新增或修改 `ai_test_cases/*.c`
- 更新 `test_register.c`
- 跑 `compile_elf.py` / `get_result.py` 做单 case 或小批量验证
- 判断 case 应进入 `default` / `manual` / `compile-only`
- 回填 `test_point` 映射与短状态说明

## Repo Anchors

- 框架宏与异常结构：`inc/rvh_test.h`
- 注册表：`test_register.c`
- AI 用例目录：`ai_test_cases/`
- 编译脚本：`compile_elf.py`
- 批跑脚本：`get_result.py`
- 项目规则：`test_point/Manual_Reference.md`
- 历史线索：`test_point/CRITICAL_ISSUES_LOG.md`

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

## Workflow

1. 锁定输入：确认 `repo_root`、测试点条目、平台、case 名、目标分层。
2. 判断 default/manual/compile-only 候选，不要先写完再临时补判定。
3. 检索存量 case：
   - 常规检索：
   ```bash
   python3 scripts/find_similar_cases.py \
     --repo-root <repo_root> \
     --from-file <test_point_file> \
     --query <axis> --query <axis> \
     --show-snippet \
     --limit 5
   ```
   - 大文本或复杂场景优先 reading pack：
   ```bash
   python3 scripts/find_similar_cases.py \
     --repo-root <repo_root> \
     --from-file <test_point_file> \
     --query <axis> --query <axis> \
     --assert-only \
     --emit-reading-pack \
     --limit 3
   ```
   - 若 `test_point_file` 里有多个 `###` 条目，而本轮目标不是最新条目，显式指定 section，避免被最新条目带偏：
   ```bash
   python3 scripts/find_similar_cases.py \
     --repo-root <repo_root> \
     --from-file <test_point_file> \
     --heading-pattern "<heading regex>" \
     --query <axis> --query <axis>
   ```
   或：
   ```bash
   python3 scripts/find_similar_cases.py \
     --repo-root <repo_root> \
     --from-file <test_point_file> \
     --section-index <1-based or negative index> \
     --query <axis> --query <axis>
   ```
4. 写或改 case：放在 `ai_test_cases/*.c`，结构和断言以 `references/writing_cases.md` 为准。
5. 调整 `test_register.c` 注册状态，使其与目标分层一致。
6. 先做单 case 编译：
   ```bash
   python3 compile_elf.py --plat spike --name <case_name>
   ```
7. 非 `compile-only` 必须做单 case 运行；`compile-only` 允许 Gate D=`N/A`，但必须写明不运行原因。
8. 更新 `test_point`：
   - 默认模板：`测试点 / 构建场景 / 已实现 case`
   - 需要 RTL/源码怀疑点时：`测试点 / 怀疑点 / 对应场景 / 已实现 case`
   - 若复用已有 case，固定只补两行 `复用依据`：`顺序一致性`、`断言一致性`
9. 回填后建议执行：
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
- `scripts/find_similar_cases.py`
  - 检索相似存量 case；支持 `--assert-only --emit-reading-pack`，以及 `--heading-pattern` / `--section-index` 做多条目 markdown 定位。
- `scripts/check_writeback_format.py`
  - 校验轻量回填格式，并可选核对 `test_register.c`。
- `scripts/eval_check_writeback_format.py`
  - 仅在修改写回校验逻辑时使用；跑固定 fixtures，避免把状态校验、注释注册识别和禁止块判定改坏。
- `scripts/eval_find_similar_cases.py`
  - 仅在修改检索逻辑时使用；跑固定 eval fixtures，避免把 `strong/weak/no_close`、Top1 排序和 markdown section 选择调坏。
- `assets/templates/new_case_template.c`
  - 最小骨架提醒，不是 case 设计真值。
