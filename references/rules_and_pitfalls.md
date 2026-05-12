# HYPTEST 规则入口索引

本文是规则入口索引。人工写用例、判断 Spike 结果、处理 harness/API 问题时，请按下面入口读取。

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

仲裁顺序以 `SKILL.md` 的 `Source Priority` 为准，本文件不再维护副本以避免两处漂移。

补充说明（不在 SKILL.md 重复）：

- Gate 在 spec_profile 之前，是为了让工作流优先走"跑一遍看结果"的闭环；Spike 跑通即按 default 落位。
- 若后续 RTL 或其它平台（LinkNan / difftest）与 Spike 结果出现分歧，转 `hyptest-failure-triage` 反向定位，再回 profile 修分层。
