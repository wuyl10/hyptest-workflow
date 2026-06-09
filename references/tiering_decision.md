# HYPTEST 自动分层裁决规则

本文给出 default/manual/compile-only 的可重复判定流程，用于减少主观波动并保留完整质量证据。

分层只描述 **当前 gate/runner 怎么闭环证据**，不描述测试点价值高低。尤其是 `spike_gate_applicable=false`、`manual`、`D-MANUAL-NONGATE` 这类结论，不表示场景低价值、可跳过或可用 Spike-friendly baseline 替代；它们通常表示该场景需要 LinkNan/RTL/special-run/人工证据，而不是 official Spike default gate。

## 1. 输入信号（来自门禁与日志）

- `compile_pass`: 单 case 编译是否通过
- `run_attempted`: 是否实际执行了单 case 运行
- `run_pass`: 单 case 运行是否通过
- `run_explainable`: 运行失败是否可归因
- `untested_unknown`: 是否存在原因不明的 `untested exception`
- `rule_aligned`: 是否与项目规则一致
- `spike_gate_applicable`: 当前场景是否适合以 Spike 作为 gate
- `evidence_complete`: 证据是否完整（日志/统计/回填）
- `register_consistent_post`: 分层落位后与 `test_register.c` 是否一致

## 2. 一票否决（先判定）

出现任一条件，禁止进入 default：

- `untested_unknown = true`
- `rule_aligned = false`
- `evidence_complete = false`

输出：

- 结论：`blocked`
- 动作：先修复问题，不做分层落位

## 3. 主裁决流程

1. 若 `compile_pass = false`：
   - 结论：`blocked`
   - 动作：先修编译问题
2. 若 `spike_gate_applicable = true`（default-first 路径）：
   - 且 `run_attempted = false`：结论 `blocked`
   - 且 `run_pass = true`：结论 `default`
   - 且 `run_pass = false` 且 `run_explainable = true`：结论 `manual`
     - **前置要求**：`run_explainable=true` 必须以 `classify_failure_log.py` 的机器输出为依据（SKILL.md step 11 强制）——没跑 classifier 即 `run_explainable=false`，直接落 `blocked (D-BLOCK-EVIDENCE)`。
   - 且 `run_attempted = true` 且 `run_explainable = false`：结论 `blocked`
   - 其他：结论 `blocked`
3. 若 `spike_gate_applicable = false`（nongate 路由）：
   - 且 `target_policy = compile-only-ok`，或当前只有编译条件、缺少该场景所需 LinkNan/RTL/special-run runner：结论 `compile-only`
   - 且 `target_policy = manual-ok`，或 `spike_gate_applicable=false` 由 step 5 Q2 显式判出且场景有可预期的 LinkNan/RTL/special-run 闭环：结论 `manual`（**不要求 official Spike `run_attempted`**；case 注册注释 + official Spike `--include-commented` 编译 smoke 即可；step 10 可选跑 official Spike 看行为但 Spike PASS 不翻 default。若需要 LinkNan difftest/no-diff/RTL/waveform 证据，先交给 `hyptest-failure-triage` 决定 `runner_request`，workflow 只按请求执行并回传证据）
   - 且 `run_attempted = true` 但结果不可归因：结论 `blocked`
4. 其他情况：
   - 结论：`manual`
5. 分层落位后检查：
   - 若 `decision in {default, manual, compile-only}` 且 `register_consistent_post = false`：
     - 最终结论改为 `blocked`（原因：分层与注册状态不一致）

## 4. 建议原因码（用于追溯）

标准来源：`references/reason_code_catalog.md`（**权威列表 15 个**；本节只列最常用的，遇到本节未列的请直接查 catalog）

- `D-PASS-DEFAULT`：编译通过 + 运行通过 + 规则一致 + 可作为 Spike gate

manual 档（5 个）：
- `D-MANUAL-NONGATE`：场景不宜 Spike gate 的通用兜底（PMA/PBMT/MMIO/cache/TLB/CBO/refill/replay/sbuffer/MSHR/PMP 粒度等 profile §5 类）
- `D-MANUAL-UNSTABLE`：Spike 运行不稳定但语义可解释（flaky）
- `D-MANUAL-RTL-ONLY`：需要 RTL/波形才能观察的现象，LinkNan difftest 或 FSDB 分析为主
- `D-MANUAL-SPIKE-GAP`：Nanhu 按 spec 实现，通常是 official/community Spike (`HYPTEST_SPIKE_BIN`) 有实现 gap（例：mcontrol6 chain 闭合后 AMO BP Spike 不抛）；若暂时复用在 `linknan-difftest` / `HYPTEST_DIFFTEST_REF_SO`，必须已有 REF-DUT first-divergence 证明这是 LinkNan difftest REF/model alignment gap，摘要必须写清 runner 和 first-divergence，不能只写“Spike gap”；未定位的 REF-DUT PMA/MMIO/CSR 对齐问题先交 `hyptest-failure-triage`
- `D-MANUAL-NANHU-NOT-IMPL`：超出 Nanhu 当前实现范围（应回退；仅作为未来支持的占位）

compile-only 档（2 个）：
- `D-COMPILE-ONLY-ENV`：仅具备编译条件，平台环境缺失
- `D-COMPILE-ONLY-STAGE`：本阶段不跑 gate，阶段性暂停

blocked 档（7 个）：
- `D-BLOCK-COMPILE`：编译挂
- `D-BLOCK-RUN-NOT-ATTEMPTED`：需要运行 gate 但本轮未执行
- `D-BLOCK-RUN-UNEXPLAINED`：已运行但结果不可归因（含 classifier 跳过）
- `D-BLOCK-UNTSTD`：存在原因不明 untested exception
- `D-BLOCK-RULE`：规则未对齐
- `D-BLOCK-EVIDENCE`：证据不完整
- `D-BLOCK-REGISTER`：分层与注册状态不一致

## 5. 输出格式（建议直接贴到交付摘要）

```text
[Auto Tiering]
- decision_prelim: default/manual/compile-only/blocked
- decision_final: default/manual/compile-only/blocked
- reason_code:
- key_evidence:
  - compile:
  - run:
  - rule_check:
  - register_check:
  - log:
```

## 6. 与现有文档的关系

- 流程入口：`references/quick_execution.md`
- 质量约束：`references/quality_gate.md`
- 原因码标准：`references/reason_code_catalog.md`
- 提交勾选：`references/submission_card.md`
- 语义依据：`references/spec_and_model_limits.md` + `references/spec_profiles/<spec_profile>.md`
- 框架/API 坑点：`references/framework_usage_pitfalls.md`

本文不替代规则文档，只统一裁决动作与输出格式。
