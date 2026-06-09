# <profile_name> 规格与平台模型边界

本文是 `<profile_name>` 的项目 profile。写该 profile 下的 case、判断 official Spike/RTL 结果、决定 default/manual/compile-only/blocked 时，以本文作为项目专属规则入口。

具体 harness/API 用法看 `references/framework_usage_pitfalls.md`，编译运行看 `references/build_run_debug.md`。

先填写这个机器可读块；`scripts/check_spec_profile.py --strict` 会检查关键字段是否存在。

```hyptest-profile
profile: <profile_name>
project_or_core: <project_or_core>
default_privilege_scope: <写清 ISA/privilege/extension 默认范围>
pmp_granularity: <写清 PMP 构造粒度>
official_spike_has_tlb_model: <true|false|unknown>
official_spike_has_cache_model: <true|false|unknown>
official_spike_has_pma_csr: <true|false|unknown>
linknan_difftest_ref_has_pma_csr: <true|false|unknown>
default_spike_gate: <写清哪些场景可作为 default Spike gate>
default_case_elf_dir: case_elf_asm
linknan_mmio_requires_responder: <true|false|unknown>
```

`linknan_difftest_ref_has_pma_csr: unknown` 只表示本 profile 尚未登记或确认
`HYPTEST_DIFFTEST_REF_SO` 的 PMA 能力，不能推导为 false。若当前项目的 LinkNan
difftest reference 已支持 PMA，应显式改成 `true`；若明确不支持，才写 `false`
并补对应 model-gap 说明。

## 1. 口径优先级

语义/规格冲突时按项目约定列出裁决顺序，例如：

1. 本文（项目真值）
2. memory `events.jsonl` 中 `status=confirmed` 的已确认历史
3. `references/spec_and_model_limits.md`
4. `test_point/CRITICAL_ISSUES_LOG.md`（历史问题库，主要用于线索，不直接覆盖当前门禁）

流程、输出、分层格式按通用文档执行，但不得覆盖本文的项目语义。

## 2. 项目范围

- 写清本 profile 覆盖的核/项目/配置范围。
- 写清默认 ISA/privilege/extension 假设。
- 写清本轮范围外项目，例如不测的中断路径、custom 路径、实现私有路径。
- 写清哪些 helper 只是项目别名，不代表扩展语义变化。

## 3. PMP 粒度约定

- 写清 PMP 构造粒度，例如 page 粒度、sub-page 粒度是否允许。
- 写清边界类测试应优先使用哪些地址/权限组合。
- 写清不能默认依赖的平台假设。

## 4. PMA / PBMT / MMIO / cacheability

- 写清允许的 PMA/PBMT/物理地址区间组合。
- 写清 Device/NC/cacheable 属性来源。
- 写清 MMIO/Device 访问是否有 testbench responder。
- 写清哪些场景是 positive valid test，哪些只能 manual/blocked。

如需要表格，建议列出：

| PMA | PBMT | MemAttr.Device | 地址区间 | 是否允许 | responder 要求 |
| --- | --- | --- | --- | --- | --- |
| <填充> | <填充> | <填充> | <填充> | <填充> | <填充> |

必须补机器可读组合表；`scripts/check_spec_profile.py --strict` 会检查字段完整性。示例：

```hyptest-pma-pbmt-matrix
[
  {
    "id": "<unique_combo_id>",
    "window": "<pa_window>",
    "pma": "<IO|MEM|unknown>",
    "pbmt": "<None|IO|NC|unknown>",
    "memattr_device": false,
    "allowed": true,
    "responder_required": false,
    "responder_status": "<confirmed|must_confirm|none|unknown>",
    "spike_gate_applicable": false,
    "default_decision": "<default|manual|compile-only|blocked guidance>"
  }
]
```

建议补 responder matrix：

| 访问目标 | responder 类型 | 可作为 memory-like scratch | 默认处理 |
| --- | --- | --- | --- |
| <PA/window> | <memory/register-like/none/unknown> | <是/否/未知> | <default/manual/blocked 建议> |

必须补机器可读 responder 表。示例：

```hyptest-mmio-responder-matrix
[
  {
    "id": "<unique_responder_id>",
    "target": "<pa_window_or_device>",
    "responder_type": "<memory|register-like|none|unknown>",
    "memory_like_scratch": false,
    "default_decision": "<default|manual|compile-only|blocked guidance>",
    "notes": "<short explanation>"
  }
]
```

## 5. Official Spike 模型边界

- 写清 official Spike 可以作为 gate 的普通架构行为。
- 写清 official Spike 缺失或弱化的模型，例如 TLB/cache/PMA/PBMT/MMIO/CBO/reservation/custom CSR。
- 写清哪些场景应标 `spike_gate_applicable=false`。
- 写清 Spike pass/fail 分别不能证明什么。

## 6. 非对齐与异常优先级

- 写清 scalar/vector/atomic 非对齐异常口径。
- 写清 Device/NC/cacheable 区域下的异常分类。
- 写清 PF/AF/misaligned/illegal/trigger 等组合优先级。
- 写清 `tval/tval2/tinst` 项目口径。

## 7. 分层默认口径

- `default`：<写清准入条件>
- `manual`：<写清手动/RTL-only 候选>
- `compile-only`：<写清只编译不运行的候选>
- `blocked`：<写清环境/规格缺失候选>

必须显式写出本 profile 下 `spike_gate_applicable` 的判定原则。

## 8. Spike 不一致时

当 Spike 结果和预期不一致：

1. 先确认 case 是否仍在测原测试点目标。
2. 判断不一致是否落在本文的 Spike 模型边界。
3. 若是普通架构行为，继续按 `references/build_run_debug.md` 定位断言/环境问题。
4. 若是模型边界，转 `manual` / `compile-only` / `blocked`，必要时用失败 triage 技能归因。
5. 不要因为单次 Spike 结果反向改写长期规则口径。

## 9. 本 profile 常见 reason_code 映射

- 通用 reason_code 定义仍以 `references/reason_code_catalog.md` 为准。
- 如本 profile 有项目专属映射，在这里列出场景 -> reason_code。
- 不要把项目专属例子写进通用 `reason_code_catalog.md`。
