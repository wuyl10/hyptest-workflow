# HYPTEST 质量门禁清单

本文定义“可提交”的最小质量线。快速执行版和完整执行版都必须通过这些门禁。

实操建议：

- 门禁判定完成后，再使用 `submission_card.md` 做提交前最后勾选确认。
- 分层结论建议按 `tiering_decision.md` 统一输出 `decision_prelim` + `decision_final` + `reason_code`。
- reason_code 必须来自 `reason_code_catalog.md`，禁止临时自造。

与 `quick_execution.md` 的 Gate 对照：

- Gate A/B/C/D/E/F/G/H 分别对应 Gate-0/1/2/3/4/5/6/7。

## Gate A: 输入清晰度

必须满足：

- 测试点条目明确
- case 名唯一
- 平台明确
- 目标分层明确

证据：

- 任务说明或交付摘要中的输入段落

失败处理：

- 禁止开始写 case

## Gate B: 代码结构完整性

必须满足：

- 单函数仅一个 `TEST_END(...)`
- 只要该步骤检查 `excpt.*`，都已先调用 `TEST_SETUP_EXCEPT()` 初始化状态
- 至少包含可观测断言
- case 构造与测试点要求逐项对齐，不是只覆盖一个相邻近似场景

证据：

- `ai_test_cases/*.c` 变更内容

失败处理：

- 回到 `writing_cases.md` 重构

## Gate C: 编译通过

必须满足：

- 单 case 编译成功
- 生成目标 ELF

证据：

- `compile_elf.py --name <case>` 执行结果

失败处理：

- 仅修编译问题，不进入运行

## Gate D: 运行可解释

必须满足：

- 非 `compile-only`：单 case 运行完成，且结果可归因（pass/fail/untested）
- `compile-only`：本轮可不运行，Gate D 记为 `N/A`，但需在结论中写明“不跑单 case 的原因”

证据：

- 非 `compile-only`：`get_result.py --case <case>` 输出 + 对应 `result_log/spike/*.log`
- `compile-only`：Gate D=`N/A` 说明（含不运行原因）+ 分层依据/原因码

失败处理：

- 按 `build_run_debug.md` 失败映射定位

## Gate E: 语义一致性

必须满足：

- 与 `Manual_Reference.md` 和 `rules_and_pitfalls.md` 一致
- 或已标注该场景不走 Spike gate

证据：

- 断言语义 + 规则引用 + 分层原因

失败处理：

- 禁止进入 default

## Gate F: 分层与注册一致

必须满足：

- default/manual/compile-only 与 `test_register.c` 状态一致

证据：

- `test_register.c` 注册项状态

失败处理：

- 修正注册策略后再提交

## Gate G: 回填闭环完整

必须满足：

- 测试点映射已回填
- 若改写/新增了测试点正文，已按 `怀疑点 / 对应场景 / 已实现 case` 三段式组织
- 特殊约束（PMA/TLB/cache）已标注

证据：

- `test_point/*` 对应条目

失败处理：

- 禁止标记“完成”

## Gate H: 交付证据完整

必须满足：

- 文件改动清单
- case 清单
- 编译/运行结果统计
- 关键日志路径（compile-only 可标 `N/A`，并附不运行原因）
- 分层结论（`decision_prelim` / `decision_final`）与依据
- `reason_code`

证据：

- 交付摘要

失败处理：

- 不允许结束任务

## 分层判定矩阵（执行时直接套用）

- default:
  - 条件：编译稳定 + Spike 稳定 + 语义一致 + 证据完整
- manual:
  - 条件：语义合理；并且已运行且结果可归因，但 Spike 不稳定或不宜做 gate
- compile-only:
  - 条件：当前仅保证可编译，本轮不执行运行 gate（或运行 gate 不成立）

## 一票否决项

出现以下任一情况，不得进入 default：

- 语义未对齐项目规则
- `untested exception` 原因不明
- PMA/TLB/cache 依赖场景未标注却按 default 放行
- 回填与注册状态不一致

## 最终结论模板

```text
[质量门禁结果]
- Gate A: pass/fail
- Gate B: pass/fail
- Gate C: pass/fail
- Gate D: pass/fail/N/A(compile-only)
- Gate E: pass/fail
- Gate F: pass/fail
- Gate G: pass/fail
- Gate H: pass/fail

[分层结论]
- decision_prelim: default/manual/compile-only/blocked
- decision_final: default/manual/compile-only/blocked
- reason_code:
- 依据:
```
