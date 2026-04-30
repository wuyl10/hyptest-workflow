# HYPTEST 规则入口索引

本文只作为兼容旧引用的索引，不再承载完整规则内容。人工写用例、判断 Spike 结果、处理 harness/API 问题时，请按下面入口读取。

## 1. 规格与平台模型入口

先看：

- `references/spec_and_model_limits.md`
- `references/spec_profiles/<spec_profile>.md`

适用场景：

- 写新 case 前确认规格来源和验证目标。
- 判断 `spike_gate_applicable`。
- 处理 Spike 结果与预期不一致。
- 判断 PMA/PBMT/MMIO/cacheability、PMP 粒度、TLB/cache/CBO/refill/replay/sbuffer/MSHR 等模型边界。
- 决定 default/manual/compile-only/blocked 候选。

## 2. 框架与工具入口

再看：

- `references/framework_usage_pitfalls.md`

适用场景：

- `TEST_SETUP_EXCEPT()`、`TEST_END(...)`、`reset_state()` 使用问题。
- `test_register.c` 注册和执行顺序问题。
- 新文件是否被 Makefile 收集。
- `compile_elf.py` / `get_result.py` / `LOG_LEVEL` 相关问题。

## 3. 具体写法与运行入口

- case 结构、断言、回填模板：`references/writing_cases.md`
- 快速执行和 Gate 对照：`references/quick_execution.md`
- 编译、运行、日志判读：`references/build_run_debug.md`
- 分层裁决：`references/tiering_decision.md`
- 原因码：`references/reason_code_catalog.md`
- 交付前复核：`references/submission_card.md`

失败闭环边界：

- 写 case、初步编译运行、默认分层判断属于 `hyptest-workflow`。
- stuck/timeout、Spike/LinkNan difftest mismatch、`HIT GOOD TRAP` 但 `FAILED`、FSDB 波形定位、50000 cycles no commit、suspected RTL bug 归因属于 `hyptest-failure-triage`。

## 4. 口径优先级

冲突时按以下顺序裁决：

1. `test_point/Manual_Reference.md`
2. `references/spec_and_model_limits.md`
3. `references/spec_profiles/<spec_profile>.md`
4. `references/quality_gate.md` + `references/tiering_decision.md` + `references/reason_code_catalog.md` + `references/submission_card.md`
5. `references/writing_cases.md` + `references/framework_usage_pitfalls.md` + `references/build_run_debug.md`
6. `test_point/CRITICAL_ISSUES_LOG.md`（历史问题库，主要用于线索，不直接覆盖当前门禁）
