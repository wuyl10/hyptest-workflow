# Triage Handoff Schema

`hyptest-workflow` 在遇到失败但不继续深入 FSDB/RTL 定位时，使用该结构把上下文交给
`hyptest-failure-triage`。字段可以为空，但键名保持稳定，方便后续复制、检索或脚本处理。

```json
{
  "case_name": "ai_example_case",
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
    "has_error": false,
    "has_untested_exception": false,
    "has_hit_good_trap": false,
    "has_bad_trap": false,
    "timed_out": false,
    "rc": null,
    "missing_required": ["PASSED"],
    "found_forbidden": ["FAILED"]
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
  "waveform_needed": false,
  "log_paths": ["run.log", "assert.log"]
}
```

## Usage

- workflow 初判时可用 `scripts/make_triage_handoff.py --log-file <log> --json` 生成草稿。
- 可用 `scripts/validate_triage_handoff.py --handoff-json <handoff.json>` 校验字段 contract。
- 如果需要 FSDB、stuck、difftest mismatch 深挖，把该 JSON 连同日志路径交给
  `hyptest-failure-triage`。
- 不要把该 handoff 当作最终 RTL 结论；它只是交接卡片。
