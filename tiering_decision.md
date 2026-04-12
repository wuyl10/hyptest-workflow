# HYPTEST 自动分层裁决规则

本文给出 default/manual/compile-only 的可重复判定流程，用于减少主观波动并保留完整质量证据。

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
2. 若 `spike_gate_applicable = true`：
   - 且 `run_attempted = false`：结论 `blocked`
   - 且 `run_pass = true`：结论 `default`
   - 且 `run_pass = false` 且 `run_explainable = true`：结论 `manual`
   - 且 `run_attempted = true` 且 `run_explainable = false`：结论 `blocked`
   - 其他：结论 `blocked`
3. 若 `spike_gate_applicable = false`：
   - 且 `run_attempted = true` 且 `run_explainable = true`：结论 `manual`
   - 且 `run_attempted = false`：结论 `compile-only`
   - 且 `run_attempted = true` 但结果不可归因：结论 `blocked`
4. 其他情况：
   - 结论：`manual`
5. 分层落位后检查：
   - 若 `decision in {default, manual, compile-only}` 且 `register_consistent_post = false`：
     - 最终结论改为 `blocked`（原因：分层与注册状态不一致）

## 4. 建议原因码（用于追溯）

标准来源：`reason_code_catalog.md`

- `D-PASS-DEFAULT`: 编译通过 + 运行通过 + 规则一致 + 可作为 Spike gate
- `D-MANUAL-NONGATE`: 场景不宜 Spike gate（PMA/TLB/cache 等）
- `D-MANUAL-UNSTABLE`: 运行不稳定但语义可解释
- `D-COMPILE-ONLY-ENV`: 仅具备编译条件，且本轮不执行运行 gate
- `D-BLOCK-RUN-NOT-ATTEMPTED`: 需要运行 gate 但本轮未执行
- `D-BLOCK-RUN-UNEXPLAINED`: 已运行但结果不可归因
- `D-BLOCK-UNTSTD`: 存在原因不明 untested exception
- `D-BLOCK-RULE`: 规则未对齐
- `D-BLOCK-EVIDENCE`: 证据不完整
- `D-BLOCK-REGISTER`: 分层与注册状态不一致

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

- 流程入口：`quick_execution.md`
- 质量约束：`quality_gate.md`
- 原因码标准：`reason_code_catalog.md`
- 提交勾选：`submission_card.md`
- 语义依据：`rules_and_pitfalls.md`

本文不替代规则文档，只统一裁决动作与输出格式。
