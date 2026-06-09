# Triage Handoff Schema

`hyptest-workflow` 在遇到失败但不继续深入 FSDB/RTL 定位时，使用该结构把上下文交给
`hyptest-failure-triage`。字段可以为空，`runner_request` 可以为 `null`，
但键名保持稳定，方便后续复制、检索或脚本处理。

```json
{
  "case_name": "ai_example_case",
  "case_names": ["ai_example_case"],
  "platform": "spike|linknan|unknown",
  "spec_profile": "<spec_profile>",
  "scenario": ["pma", "pbmt", "store"],
  "assert_site": "path/file.c:123",
  "assert_expr": "excpt.triggered && excpt.cause == ...",
  "exception_observed": {
    "triggered": 1,
    "cause": "0xf",
    "tval": "0x1000"
  },
  "excpt_dump": {
    "triggered": "1",
    "cause": "0xf",
    "tval": "0x...",
    "tval2": "0x...",
    "tinst": "0x..."
  },
  "log_markers": {
    "has_passed": false,
    "has_failed": true,
    "has_difftest_failed": false,
    "has_mismatch": false,
    "has_ref_dut_delta": false,
    "has_selfcheck_failed": true,
    "has_error": false,
    "has_untested_exception": false,
    "has_hit_good_trap": false,
    "has_bad_trap": false,
    "timed_out": false,
    "rc": null,
    "missing_required": ["PASSED"],
    "found_forbidden": ["FAILED"]
  },
  "runner_context": {
    "official_spike": false,
    "linknan_platform": true,
    "linknan_difftest": true,
    "difftest_disabled": false,
    "linknan_no_diff": false,
    "difftest_mode_conflict": false,
    "multi_run": false,
    "runner_conflict": false,
    "runner_ambiguous": false
  },
  "error_points": ["case assertion failed"],
  "reason_code_candidates": ["D-BLOCK-RUN-UNEXPLAINED"],
  "reason_code_details": [
    {
      "code": "D-BLOCK-RUN-UNEXPLAINED",
      "class": "BLOCK",
      "default_decision": "blocked",
      "meaning": "已运行，但失败结果不可归因。",
      "typical_followup": "先完成归因，再继续分层。",
      "evidence": "failed/assert_site/assert_expr in log"
    }
  ],
  "next_single_run": "python3 get_result.py ...",
  "runner_request": {
    "runner_mode": "spike-gate|linknan-difftest|linknan-no-diff",
    "compile_plat": "spike|linknan",
    "run_platform": "spike|linknan",
    "difftest_mode": "not-applicable|enabled|disabled",
    "include_commented": true,
    "cleanup_allowed": false,
    "purpose": "why this rerun is needed"
  },
  "waveform_needed": false,
  "waveform_context": {
    "waveform_path": null,
    "rtl_root": null,
    "top_module": null,
    "debug_target": null,
    "time_window": null,
    "expected_behavior": null,
    "observed_behavior": null,
    "suggested_waveform_report": null
  },
  "log_paths": ["run.log", "assert.log"]
}
```

## Usage

- workflow 初判时可用 `scripts/make_triage_handoff.py --log-file <log> --json` 生成草稿。
- 可用 `scripts/validate_triage_handoff.py --handoff-json <handoff.json>` 校验字段 contract。
- 如果需要 FSDB、stuck、difftest mismatch 深挖，把该 JSON 连同日志路径交给
  `hyptest-failure-triage`。
- `runner_request` 键固定存在但可以为 `null`；当 `hyptest-failure-triage`
  已经决定需要 workflow 执行 rerun 时填入对象。已有 LinkNan difftest
  mismatch 默认用 `runner_mode=linknan-difftest` 保留 REF-DUT 证据；
  `linknan-no-diff` 只作为 RTL/waveform/no-response 补充观察，不能清理
  mismatch 列表。
- `make_triage_handoff.py` 只有在显式传 `--runner-mode` 时才会填充
  `runner_request`；不要从 `--include-commented`、`--cleanup-allowed` 或
  `--runner-purpose` 等附属参数推断 runner。
- `runner_context.linknan_platform=true` 只说明日志/路径来自 LinkNan 平台；
  只有 `linknan_difftest=true` 才说明存在 difftest-enabled / REF-DUT 证据。
  `difftest_disabled=true` 表示日志明确出现 disabled/no-diff 证据；
  `linknan_no_diff=true` 只在 LinkNan 平台 + difftest disabled + 无
  difftest-enabled/REF-DUT 证据时成立。`difftest_mode_conflict=true`
  表示同一段日志同时出现 difftest-enabled 和 disabled/no-diff 证据，通常是
  batch 或多次观察混在一起，先拆 run 再做 cleanup 或 runner 归因。
  `multi_run=true` 表示同一日志中出现多个
  compile/run 命令，先拆 batch 再做单 case 归因。`runner_conflict=true` 表示
  official Spike 与任意 LinkNan 平台/difftest/no-diff/RTL 证据混在同一段日志里，必须先拆分 runner
  证据再做 model-gap 或 RTL 归因。
- `case_names` 是 workflow 从命令行、测试 header 或 case 名行提取出的候选
  case 列表；batch log 中可以有多个，`case_name` 只保留第一个候选作为兼容字段。
  schema validator 会要求 `case_names` 中每项都是非空字符串、无重复；若
  `case_name` 非空，它必须等于 `case_names[0]` 且包含在 `case_names` 内。
- `log_markers.has_difftest_failed` / `has_mismatch` / `has_ref_dut_delta`
  与 `has_selfcheck_failed` 用于把 difftest mismatch 和 case 自检失败拆开。
  裸 `FAILED` 不应覆盖 REF-DUT first-divergence 判断。
- 如果 workflow 已经知道 waveform 文件、RTL 根目录、top、debug target 或希望
  failure-triage 生成 waveform-aware report，可以把这些信息放进
  `waveform_context`。这个字段是可选的，用于把“直接波形分析”与“失败闭环里需要
  波形”的场景区分开。
- 不要把该 handoff 当作最终 RTL 结论；它只是交接卡片。
