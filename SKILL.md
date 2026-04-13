---
name: hyptest-workflow
description: 用于 https://github.com/wuyl10/riscv-hyp-tests-nhv5.git 仓库（nhv5.1 分支目录）的 hyptest 测试点到用例落地工作流。凡是涉及新增/修改 ai_test_cases 用例、更新 test_register.c、根据 test_point 回填映射、执行 compile_elf.py 和 get_result.py 编译批跑、分析 Spike 日志并做 default/manual/compile-only 分层决策时，都应触发此技能。当前默认 no-H 策略：不依赖 H 特有指令/CSR；仓库内 HS 路径按项目约定作为 S 语义别名使用。
---

# HYPTEST Workflow Skill

该技能用于在 https://github.com/wuyl10/riscv-hyp-tests-nhv5.git 的 nhv5.1 分支目录内完成完整的 hyptest 研发闭环：

- 测试点分析
- 用例编写
- 编译与批量执行
- 异常/失败定位
- 回填与分层管理

## 适用场景

当用户提出以下需求时，优先使用本技能：

- 基于 `test_point/*` 生成或完善用例
- 让某个测试点变成可编译、可运行、可回归的 case
- 只编译某批 case 或单 case（不影响默认回归）
- 批量跑 Spike 并汇总日志
- 对 `untested exception`、`FAILED`、`TIMEOUT` 做定位
- 决定 case 应进入 default、manual 还是 compile-only

## 必要输入

执行前尽量明确：

- 目标测试点来源文件（例如 `test_point/architectural_test_point`）
- 目标平台（通常 `spike`）
- 是否要求进入 default 回归
- 是否允许以 `manual/compile-only` 形式先落地

## 仓库来源与分支要求

- 仓库来源统一为：https://github.com/wuyl10/riscv-hyp-tests-nhv5.git
- 使用范围为该仓库的 `nhv5.1` 分支工作目录。
- 只要当前工作目录来自该仓库且分支为 `nhv5.1`，即可直接应用本 skill。

### 输入检查清单（执行前逐项确认）

- 测试点是否已明确到具体条目（不是仅给目录）。
- 目标 case 名是否已唯一（避免与 `ai_test_cases/` 现有函数重名）。
- 目标平台是否明确（`spike` / 其他）。
- 是否允许先 `manual/compile-only`（避免被 default gate 阻塞）。
- 是否存在 PMA/PBMT/TLB/cache 依赖（决定是否走 Spike gate）。

## 仓库关键入口

- 测试框架宏与异常结构：`inc/rvh_test.h`
- 默认注册表：`test_register.c`
- AI 用例目录：`ai_test_cases/`
- 编译脚本：`compile_elf.py`
- 批跑脚本：`get_result.py`
- 人工规则中心：`test_point/Manual_Reference.md`
- 历史坑点沉淀：`test_point/CRITICAL_ISSUES_LOG.md`

## 强约束

- 默认按 no-H 策略写用例：不引入 H 特有指令/CSR。仓库中的 HS helper 按项目约定视为 S 语义路径别名。允许 runner 使用 ISA 超集运行（例如命令行含 H 位），不代表启用 H 语义断言。
- 不要在一个函数内写多个 `TEST_END(...)`。
- 只要本步骤要断言 `excpt.triggered/cause/tval`（包括预期 `triggered == false`），都先调用 `TEST_SETUP_EXCEPT()` 初始化状态。
- 测试注册统一在 `test_register.c` 管理，不在 case 文件中注册。
- 对 PMA/PBMT/cache/uncache 强相关场景，不要强行以 Spike 作为唯一准入条件。
- 写回 `test_point_file` 的测试点正文时，默认使用固定三段式结构：`怀疑点：`、`对应场景：`、`已实现 case：`；不要只回填 case 名而缺少源码怀疑点和场景描述。
- 新增 case 必须与测试点逐项对齐，显式构造该测试点描述的 bug 场景；禁止用“相邻近似场景”替代“目标测试点场景”来充数。
- 当目标源文件已经过长、可读性明显下降，或用户已明确指出“不希望继续堆到旧大文件”时，必须新建 `ai_test_cases/*.c` 文件承载新 case，而不是继续往超大历史文件中追加。

## 口径优先级（冲突时）

当不同文档表述不一致时，按以下顺序执行：

1. `test_point/Manual_Reference.md`
2. `quality_gate.md` + `tiering_decision.md` + `reason_code_catalog.md` + `submission_card.md`
3. `rules_and_pitfalls.md` + `writing_cases.md` + `build_run_debug.md`
4. `CRITICAL_ISSUES_LOG.md`（历史问题库，主要用于背景和排错线索）

补充说明：

- 调试顺序以日志与最小复现实验为准，不以视觉顺序经验做硬判断。
- 只要断言 `excpt.triggered/cause/tval`（包括预期 `triggered == false`），都先调用 `TEST_SETUP_EXCEPT()`。

## 执行模式（保质量）

- 快速执行版：`quick_execution.md`
	- 用于减少执行路径切换，但不减少质量检查项。
- 完整执行版：`writing_cases.md` + `build_run_debug.md` + `rules_and_pitfalls.md`
	- 用于复杂场景、语义冲突、疑难失败定位。

统一门禁：

- 无论使用哪种执行模式，最终都必须通过 `quality_gate.md`。
- 快速执行版任一门禁失败时，必须切换到完整执行版排查。
- 提交前建议再勾选 `submission_card.md`，确保执行动作与证据输出都完整。

## 工作流

1. 读取测试点与规则：先看 `test_point/*` 和 `Manual_Reference.md`。
2. 归类测试目标：判断是 default、manual 还是 compile-only 候选。
3. 编写/修改 case：放入 `ai_test_cases/*.c`，遵循命名与模板。
4. 注册策略：在 `test_register.c` 中控制是否开启注册。
5. 编译验证：优先用 `compile_elf.py` 做单 case 或小批量编译。
6. 运行验证：非 `compile-only` 用 `get_result.py` 或直接 Spike 运行 ELF；`compile-only` 在结论中标注 Gate D=`N/A` 与不运行原因。
7. 日志归档：读取 `result_log/spike/*.log` 判定失败类型。
8. 回填闭环：更新 `test_point` 对应用例名及状态说明。

### 测试点回填正文格式（默认执行）

写回 `test_point_file` 的测试点条目时，优先按以下三段式组织正文：

```text
怀疑点：

- ...
- ...

对应场景：

- ...
- ...

已实现 case：

- `case_name`
```

要求：

- `怀疑点` 段优先引用 RTL/源码位置，并说明为什么这里可能出 bug。
- `对应场景` 段必须把 fault/repair/success/producer-switch/template-switch 等关键顺序写清楚，确保能从文本直接映射到 case 构造。
- `已实现 case` 段只列真正对应该测试点的 case；若尚未新增成功，不得拿相邻 case 顶替。

### 失败分叉（强制执行）

- 编译失败：先修复语法/宏/链接，再进入运行阶段。
- 运行失败且出现 `untested exception`：先核查异常准备与特权态，不直接改预期。
- 运行失败且语义与规则冲突：先对照 `Manual_Reference.md`，再决定是修用例还是改分层。
- 语义合理但 Spike 不稳定：转 `manual` 或 `compile-only`，并在回填中显式标注原因。

## 结果分层标准

- default：Spike 语义稳定、结果可重复、行为与项目规则一致。
- manual：场景合理但 Spike 行为不稳定或需人工确认语义。
- compile-only：用于覆盖 RTL 风险路径，当前不以 Spike 结果作为 gate。

## 输出要求

执行本技能后，结论至少应包含：

- 修改了哪些文件
- 新增/修改了哪些 case
- 编译结果（成功/失败数量）
- 运行结果（非 compile-only：pass/fail/timeout/missing；compile-only：Gate D=N/A + 不运行原因）
- 自动裁决（`decision_prelim` / `decision_final`）
- 分层原因码（`reason_code`，建议参考 `tiering_decision.md`）
- 后续建议动作（若有）

### 输出模板（建议直接复用）

```text
[范围]
- 测试点:
- 平台:
- 分层目标:

[改动]
- 文件:
- case:

[验证]
- 编译: x pass / y fail
- 运行: x pass / y fail / z untested / 或 Gate D=N/A(compile-only, reason=...)
- 关键日志: result_log/spike/...（compile-only 可填 N/A，并给出分层依据）

[结论]
- decision_prelim:
- decision_final:
- reason_code:
- 判定依据:
- 下一步:
```

## 默认禁止事项

- 禁止在未完成单 case 编译前直接全量批跑。
- 禁止未核对 `test_register.c` 注册状态就宣称“可回归”。
- 禁止把“可编译”直接等价为“default 可准入”。
- 禁止删减已有规则细节来换取表面通过率。

## 详细文档

- 快速执行流程：`quick_execution.md`
- 质量门禁清单：`quality_gate.md`
- 自动分层裁决：`tiering_decision.md`
- 原因码目录：`reason_code_catalog.md`
- 一页提交核对卡：`submission_card.md`
- 用例编写细则：`writing_cases.md`
- 编译/运行/调试细则：`build_run_debug.md`
- 规则与坑点清单：`rules_and_pitfalls.md`
- 可复用代码模板：`templates/new_case_template.c`
