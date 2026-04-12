# HYPTEST 规则与坑点清单

本文汇总 `CRITICAL_ISSUES_LOG.md`、`Manual_Reference.md`、`codex_rollout_20260409_154542_summary.md` 的可执行规则。

## 0. 口径优先级（冲突时）

当文档之间出现冲突时，按以下顺序裁决：

1. `test_point/Manual_Reference.md`
2. `quality_gate.md` + `tiering_decision.md` + `reason_code_catalog.md` + `submission_card.md`
3. 本文 + `writing_cases.md` + `build_run_debug.md`
4. `CRITICAL_ISSUES_LOG.md`（历史问题库，主要用于线索，不直接覆盖当前门禁）

补充：

- `CRITICAL_ISSUES_LOG.md` 中“从下往上执行”等历史经验，不作为固定规则；顺序问题一律以日志与最小复现实验为准。
- `TEST_SETUP_EXCEPT()` 以当前统一口径执行：凡断言 `excpt.triggered/cause/tval`（包括预期 `triggered == false`）都应先初始化。

## 1. 先定规则，再写 case

优先级顺序：

1. 项目规则（`test_point/Manual_Reference.md`）
2. 框架约束（`inc/rvh_test.h` + 现有代码风格）
3. Spike 观测

说明：Spike 是重要参考，但不是所有场景的最终真值。

## 2. 关键策略（必须遵守）

### 2.1 no-H 默认策略

- 当前平台和流程默认不依赖 H 扩展。
- 新 case 避免使用 H 特有指令/CSR 作为必要条件。
- 项目里的 HS helper 按约定可作为 S 语义路径别名使用（不是要求启用 H 扩展验证）。

### 2.2 WFI 风险控制

- WFI 可能导致模拟器卡死。
- 优先测试权限与控制位语义，不强制执行真实等待路径。

### 2.3 注册与执行管理

- 注册统一放在 `test_register.c`。
- 新 case 是否进 default 要单独评审，不自动放行。
- 调试顺序问题时，优先以日志与最小复现实验为准，不以 `test_register.c` 的视觉顺序做硬判断。

### 2.4 default/manual/compile-only 三层管理

- default：稳定且可重复。
- manual：规则已明确，但 Spike 不宜作为 gate。
- compile-only：仅保留编译与场景表达，后续交由 RTL/人工环境验证。

## 3. PMA/TLB 一致性/cache 一致性相关硬规则

### 3.1 PMA 依赖场景不强绑 Spike

依赖 `PMAADDR*`、`PMACFG*`、TLB 一致性、cache 一致性的场景，允许：

- 先落代码
- 先回填测试点
- 默认不进 Spike gate

建议回填标注：

- `(case_name, 依赖PMA CSR/TLB一致性/cache一致性, 未跑Spike)`

### 3.2 区分 PMA=IO 与 PBMT=IO

不要混淆：

- `PMA=IO`（物理地址区域语义）
- `PBMT=IO`（PTE 属性语义）

case 注释必须写清“Device 属性来源”。

### 3.3 非对齐规则

- Device/MMIO 上的非对齐访存按 AF 口径处理。
- 标量 NC 非对齐按 addr misalign fault 处理。
- 向量 NC/MMIO 非对齐直接按 AF 处理。
- 原子非对齐直接按 AF 处理。
- 不要仍按 misalign 旧口径写断言。

### 3.4 非对齐判定速查（推荐作为评审清单）

- 标量 + cacheable：优先按常规 misalign 语义检查（结合页表/PMP 环境）。
- 标量 + NC：按 addr misalign 口径断言。
- 向量 + NC/MMIO：按 AF 口径断言。
- AMO + 非对齐：按 AF 口径断言。

若同一 case 包含多种访问形态，必须在断言文案里标明“本条断言对应哪一类访问”。

### 3.5 规则冲突裁决顺序

当出现“测试点描述 vs Spike 观测 vs 规则文档”冲突时，按以下顺序裁决：

1. `Manual_Reference.md`（项目规则）
2. `CRITICAL_ISSUES_LOG.md`（已确认坑点）
3. 当前 case 日志观测（仅作证据，不直接改规则）

不要因为单次 Spike 结果就反向改写长期规则口径。

## 4. 异常优先级与 tval 规则

### 4.1 混合异常判定

当 Device 非对齐与 PF/TLB AF 等组合叠加时，遵循项目规则：

- 显式访存先按翻译阶段 first encountered fault 判定。
- 不要机械地把所有 Device 非对齐都改写成 AF。

### 4.2 cross-page high-half tval

历史已确认：

- low-half 正常，high-half fault 时，`tval` 应取 second-half 起始地址。

### 4.3 tval2/tinst 相关说明

- 涉及 guest fault、隐式页表访问或 replay 场景时，必要时同时检查 `tval2/tinst`。
- 若平台差异导致 `tval2/tinst` 不稳定，优先保持主语义断言并按分层策略降级到 manual。

## 5. Spike 已知不可靠点

以下场景不宜作为 default gate：

- PMA/PBMT/cache/uncache 内部路径语义
- `sfence.vma` 相关 stale translation 细节
- 一些 trigger 与复杂组合场景

此外已记录的 Spike 行为偏差包括：

- `MSTATUS.MIE` 写入映射异常（应保持规范测试，不要为兼容偏差改错代码）
- 某些扩展未启用时 CSR 访问触发非法指令（如 `zicntr`）

## 6. 框架 API 常见误用

### 6.1 TEST_SETUP_EXCEPT 滥用

错误：

- 在不检查 `excpt.*` 的路径机械性到处加 `TEST_SETUP_EXCEPT`。
- 把 `TEST_SETUP_EXCEPT` 当成“隐藏异常”的手段。

正确：

- 只要要断言 `excpt.triggered/cause/tval`（包括预期 `triggered == false`），就在该步骤前设置 `TEST_SETUP_EXCEPT` 初始化状态。
- 不读取 `excpt.*` 时，不必强行调用。

### 6.2 TEST_END 重复

错误：一个函数多个 `TEST_END(...)`，会触发重复标签问题。

正确：每个 case 函数只保留一个 `TEST_END(...)`。

### 6.3 reset_state 语义误解

`reset_state()` 主要用于 CSR/状态重置，不等价于“自动清除一切异常痕迹”。

## 7. 编译与脚本层面坑点

### 7.1 新文件未纳入编译

虽然后续 Makefile 已使用 `$(wildcard ai_test_cases/*.c)` 自动收集，仍需确认：

- 文件名在 `ai_test_cases/` 下
- 后缀是 `.c`

### 7.2 compile_elf 并发污染风险

历史经验：并发改写/恢复 `test_register.c` 会引入不稳定。

建议：

- 串行执行关键编译步骤。
- 每轮编译后检查 `test_register.c` 是否恢复。

### 7.3 LOG_LEVEL 影响调试可见性

需要细粒度断言打印时，使用：

- `LOG_LEVEL=LOG_DETAIL`

## 8. 写 case 前检查单

- 是否明确了测试点语义来源（PMA 还是 PBMT）
- 是否存在 TLB 一致性或 cache 一致性依赖
- 是否命中 `test_point/ai_exclude_*.txt` 或 `test_point/human_exclude_*.list`
- 是否判断过 default/manual/compile-only 候选层级
- 是否选择了正确特权态与地址环境
- 是否写了可观测断言（cause/tval/data）
- 是否规避 H 扩展与 WFI 实际执行风险

## 9. 提交前检查单

- 单 case 编译通过
- 非 compile-only：单 case 运行结果可解释；compile-only：Gate D=N/A 原因明确
- `test_register.c` 注册状态符合预期
- `test_point` 已回填 case 名和状态标签
- 若命中排除清单，分层、回填备注与 `reason_code` 已一致
- 日志已归档，失败有定位说明

## 10. 推荐决策语句模板

用于汇报时可直接复用：

- `该 case 已满足 default 准入：编译稳定、Spike 稳定、语义与 Manual_Reference 一致。`
- `该 case 保持 manual：场景合理但 Spike 在该路径不作为可靠 gate。`
- `该 case 保持 compile-only：当前用于覆盖 RTL 风险路径，不并入 default 统计。`
