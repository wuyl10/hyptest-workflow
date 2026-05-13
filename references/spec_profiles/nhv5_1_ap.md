# NHV5.1AP 规格与平台模型边界

本文是 NHV5.1AP 当前项目 profile。写 NHV5.1AP case、判断 official Spike/LinkNan 结果、决定 default/manual/compile-only/blocked 时，以本文作为项目专属规则入口。

具体 harness/API 用法看 `references/framework_usage_pitfalls.md`，编译运行看 `references/build_run_debug.md`。

```hyptest-profile
profile: nhv5_1_ap
project_or_core: NHV5.1AP
default_privilege_scope: no-H
pmp_granularity: 4KB
official_spike_has_tlb_model: false
official_spike_has_cache_model: false
official_spike_has_pma_csr: false
default_spike_gate: ordinary_cacheable_dram_arch_only
default_case_elf_dir: case_elf_asm
linknan_mmio_requires_responder: true
```

## 1. 口径优先级

语义/规格冲突时按以下顺序裁决：

1. 本文（项目真值）
2. memory `events.jsonl` 中 `status=confirmed` 的已确认历史
3. `references/spec_and_model_limits.md`
4. `test_point/CRITICAL_ISSUES_LOG.md`（历史问题库，主要用于线索，不直接覆盖当前门禁）

流程、输出、分层格式按以下文档执行，但不得覆盖本文的规格语义：

- `references/quality_gate.md`
- `references/tiering_decision.md`
- `references/reason_code_catalog.md`（**reason_code 的权威来源**；任何分层归因时先查这里）
- `references/submission_card.md`
- `references/writing_cases.md`
- `references/build_run_debug.md`

注：完整 Source Priority 见 `SKILL.md`（本文在 SKILL.md 的 §2，位于通用 Gate/tiering 规则之上；memory 不参与规则冲突裁决，仅作查询辅助）。

## 2. 项目范围

- 当前默认 no-H：不依赖 H 特有指令/CSR。
- 仓库里的 HS helper 按项目约定可作为 S 语义路径别名使用，不表示要求启用 H 扩展验证。
- NMI、double trap 不属于本轮 NHV5.1AP 常规验证项目范围；相关 case 不进入常规 default gate。
- project/custom CSR 或 custom instruction 若 official Spike 不支持，按 official Spike model gap 处理；是否属于项目验证范围由测试点/项目需求决定，不自动等同于范围外。
- WFI 可能导致模拟器卡死；优先测试权限与控制位语义，不强制执行真实等待路径。

## 3. PMP 粒度约定

- 当前项目默认按 4KB page 粒度构造 PMP 相关 case。
- 不默认依赖 sub-4KB PMP 隔离精度；除非用户明确要求且平台/源码证据支持。
- PMP 边界类测试优先使用 4KB page boundary、page offset、跨页/页内权限组合来表达。
- 不要写出“只有 4KB 内小区域被隔离、同页其它区域仍可访问”的隐含假设。

## 4. PMA / PBMT / MMIO / cacheability

必须区分：

- `PMA=IO`：物理地址区域语义。
- `PBMT=IO`：PTE 属性语义。
- `PBMT=NC`：页表属性指定 non-cacheable 语义，不等价于 PMA IO。

硬规则：

- case 注释和测试点回填必须写清 Device/NC 属性来源。
- PMA/PBMT 与物理地址区间组合只能使用下表中标为“允许”的组合；未标允许的组合不要构造为有效正向测试。
- 不要为了让 Spike 通过，把 PMA/PBMT/IO 目标搬到普通 DRAM/cacheable 区域。
- PMA/PBMT/MMIO/cacheability 相关场景默认先判为 `spike_gate_applicable=false`，除非有明确证据说明该场景只依赖 Spike 可建模的普通架构行为。
- legal PMA/peripheral PA 不等于 testbench 有响应路径；没有 responder 时应标 `blocked` / `manual`，不要伪造 pass。
- MMIO/Device 访问除了满足下表允许组合外，还必须确认当前 LinkNan testbench 对目标 PA 有模拟 IO responder；部分允许区间当前没有模拟 IO 返回路径，访问会无响应并导致卡死。
- UART/IntrGen 这类 register-like responder 不能替代 memory-like MMIO scratch；若 case 需要 byte/half/word lane merge、整行 readback 或任意地址可读写，必须确认 responder 语义足够。

允许组合表：

| PMA | PBMT | MemAttr.Device | 0x0~2G | 2G~128G | 3T~4T |
| --- | --- | --- | --- | --- | --- |
| IO | None | true | 允许 |  | 允许 |
| IO | IO | true | 允许 |  | 允许 |
| IO | NC | false |  |  | 允许 |
| MEM | None | false |  | 允许 | 允许 |
| MEM | IO | true |  |  | 允许 |
| MEM | NC | false |  | 允许 | 允许 |

机器可读组合表：

```hyptest-pma-pbmt-matrix
[
  {
    "id": "io_none_low_0_2g",
    "window": "0x0-0x80000000",
    "pma": "IO",
    "pbmt": "None",
    "memattr_device": true,
    "allowed": true,
    "responder_required": true,
    "responder_status": "must_confirm",
    "spike_gate_applicable": false,
    "default_decision": "manual_or_blocked_until_responder_confirmed"
  },
  {
    "id": "io_io_low_0_2g",
    "window": "0x0-0x80000000",
    "pma": "IO",
    "pbmt": "IO",
    "memattr_device": true,
    "allowed": true,
    "responder_required": true,
    "responder_status": "must_confirm",
    "spike_gate_applicable": false,
    "default_decision": "manual_or_blocked_until_responder_confirmed"
  },
  {
    "id": "mem_none_2g_128g",
    "window": "0x80000000-0x2000000000",
    "pma": "MEM",
    "pbmt": "None",
    "memattr_device": false,
    "allowed": true,
    "responder_required": false,
    "responder_status": "dram_memory",
    "spike_gate_applicable": true,
    "default_decision": "default_candidate_if_no_other_model_limit"
  },
  {
    "id": "mem_nc_2g_128g",
    "window": "0x80000000-0x2000000000",
    "pma": "MEM",
    "pbmt": "NC",
    "memattr_device": false,
    "allowed": true,
    "responder_required": false,
    "responder_status": "dram_memory",
    "spike_gate_applicable": false,
    "default_decision": "manual_unless_arch_only_and_model_supported"
  },
  {
    "id": "io_none_3t_4t",
    "window": "0x30000000000-0x40000000000",
    "pma": "IO",
    "pbmt": "None",
    "memattr_device": true,
    "allowed": true,
    "responder_required": true,
    "responder_status": "must_confirm",
    "spike_gate_applicable": false,
    "default_decision": "manual_or_blocked_until_responder_confirmed"
  },
  {
    "id": "io_io_3t_4t",
    "window": "0x30000000000-0x40000000000",
    "pma": "IO",
    "pbmt": "IO",
    "memattr_device": true,
    "allowed": true,
    "responder_required": true,
    "responder_status": "must_confirm",
    "spike_gate_applicable": false,
    "default_decision": "manual_or_blocked_until_responder_confirmed"
  },
  {
    "id": "io_nc_3t_4t",
    "window": "0x30000000000-0x40000000000",
    "pma": "IO",
    "pbmt": "NC",
    "memattr_device": false,
    "allowed": true,
    "responder_required": true,
    "responder_status": "must_confirm",
    "spike_gate_applicable": false,
    "default_decision": "manual_or_blocked_until_responder_confirmed"
  },
  {
    "id": "mem_none_3t_4t",
    "window": "0x30000000000-0x40000000000",
    "pma": "MEM",
    "pbmt": "None",
    "memattr_device": false,
    "allowed": true,
    "responder_required": false,
    "responder_status": "memory_if_testbench_maps_it",
    "spike_gate_applicable": true,
    "default_decision": "default_candidate_if_no_other_model_limit"
  },
  {
    "id": "mem_io_3t_4t",
    "window": "0x30000000000-0x40000000000",
    "pma": "MEM",
    "pbmt": "IO",
    "memattr_device": true,
    "allowed": true,
    "responder_required": true,
    "responder_status": "must_confirm",
    "spike_gate_applicable": false,
    "default_decision": "manual_or_blocked_until_responder_confirmed"
  },
  {
    "id": "mem_nc_3t_4t",
    "window": "0x30000000000-0x40000000000",
    "pma": "MEM",
    "pbmt": "NC",
    "memattr_device": false,
    "allowed": true,
    "responder_required": false,
    "responder_status": "memory_if_testbench_maps_it",
    "spike_gate_applicable": false,
    "default_decision": "manual_unless_arch_only_and_model_supported"
  }
]
```

使用约束：

- `0x0~2G`：只允许 `PMA=IO, PBMT=None/IO`。
- `2G~128G`：只允许 `PMA=MEM, PBMT=None/NC`。
- `3T~4T`：允许上表全部列出的 PMA/PBMT 组合。
- 上表只说明规格允许性，不保证 testbench 有 responder；所有 `MemAttr.Device=true` 或 MMIO/Device 访问都要先确认可返回。
- 需要读写返回值、lane merge、整行 readback 或任意地址 readback 的 MMIO case，必须使用 memory-like responder；没有等价 responder 时保持 `blocked` / `manual`，不要改成 DRAM/cacheable 替代。

MMIO responder matrix：

| 访问目标 | responder 类型 | 可作为 memory-like scratch | 默认处理 |
| --- | --- | --- | --- |
| 普通 DRAM/cacheable 区域 | memory | 是 | 可作为 default Spike gate 候选 |
| `0x0~2G` Device/MMIO 区域 | 依 testbench 连接而定 | 未确认前否 | 先确认 responder；否则 `blocked` / `manual` |
| `3T~4T` Device/MMIO 区域 | 依 testbench 连接而定 | 未确认前否 | 只按规格允许不够；无返回路径会卡死 |
| UART/IntrGen 等寄存器型外设 | register-like | 否 | 只适合对应寄存器语义，不替代任意地址 MMIO memory |

机器可读 responder 表：

```hyptest-mmio-responder-matrix
[
  {
    "id": "dram_cacheable",
    "target": "ordinary_dram_cacheable",
    "responder_type": "memory",
    "memory_like_scratch": true,
    "default_decision": "default_candidate_if_no_other_model_limit",
    "notes": "ordinary cacheable DRAM can be used for normal architectural Spike gate cases"
  },
  {
    "id": "device_low_0_2g",
    "target": "0x0-0x80000000_device_mmio",
    "responder_type": "testbench_dependent",
    "memory_like_scratch": false,
    "default_decision": "manual_or_blocked_until_responder_confirmed",
    "notes": "legal PMA/PBMT combination is not enough; no simulated IO return can hang"
  },
  {
    "id": "device_high_3t_4t",
    "target": "0x30000000000-0x40000000000_device_mmio",
    "responder_type": "testbench_dependent",
    "memory_like_scratch": false,
    "default_decision": "manual_or_blocked_until_responder_confirmed",
    "notes": "allowed window still needs a concrete responder and width/readback support"
  },
  {
    "id": "register_like_peripheral",
    "target": "uart_intrgen_or_register_like_peripheral",
    "responder_type": "register-like",
    "memory_like_scratch": false,
    "default_decision": "manual_for_device_specific_semantics_only",
    "notes": "does not replace arbitrary-address memory-like MMIO scratch"
  }
]
```

新增或修改 MMIO case 前必须写清：

- 目标 PA window。
- Device/NC 来源是 PMA 还是 PBMT。
- 当前 testbench 是否存在 responder。
- responder 是否支持本 case 需要的读写宽度、lane merge、readback 或整行可见性。

## 5. Official Spike 模型边界

以下场景不宜把 official Spike 当 default gate：

- 本版本 official Spike 没有 TLB/cache 模型；凡涉及 TLB 一致性、cache 一致性、stale translation、cache residency、dirty line preservation、refill image、cacheline side effect 的 case，都只能走 RTL-only/LinkNan 仿真，不走 official Spike gate。
- 本版本 official Spike 没有实现 PMA CSR；凡涉及访问 `PMAADDR*`、`PMACFG*` 等 PMA CSR 的 case，都只能走 RTL-only/LinkNan 仿真，不走 official Spike gate。
- CBO 的架构可见异常、权限、编码语义可以作为测试目标；是否可作为 Spike gate 取决于是否只依赖 Spike 可建模的普通架构行为。
- CBO 的内部 line 状态、cache side effect、refill image、以及无 A/D 权限时的实现分类差异，不作为 official Spike default gate。
- replay queue、sbuffer、uncache buffer、MSHR、ROB head、response-context binding。
- PMA/PBMT/MMIO/cacheability routing 和平台 responder 行为。
- LR/SC reservation timeout、同 PA 不同 VA 的 cache hit / set index 条件、或其它实现特定 reservation 策略。
- project/custom CSR、custom instruction、NMI/double trap 等非本轮 NHV5.1AP 验证范围或 official Spike 不支持的路径。
- Debug trigger: `mcontrol6` chain 闭合后 AMO 的 breakpoint 语义在 Spike 不建模——chain mismatch 抑制路径在 Spike 上可观测（符合 spec），但 chain 闭合后 spec 要求的 BP 在 Spike 不抛（详见 `test_point/Manual_Reference.md#C7`）。

**Nanhu NHV5.1AP Debug trigger 实现约束**（Nanhu 侧的裁剪，超出部分 **测试点本身不应设计**）：

- chain 最多支持 **2 层**（即只支持两个 trigger 的级联；3 层及以上 chain 不支持，case 不应覆盖）。
- 仅支持 **address trigger（访存地址）** 和 **execute-PC trigger（取指地址）**。
- **不支持 data trigger**（trigger 匹配数据值）；相关 case 不应设计。

机器可读 nongate keyword 速查（供 `scripts/query_spec_profile.py --nongate-summary` 使用；与上文 prose 保持一致，prose 仍为真值）：

```hyptest-nongate-keywords
[
  {
    "category": "TLB/cache consistency",
    "keywords": ["tlb", "cache", "stale_translation", "cache_residency", "dirty_line", "refill", "cacheline"],
    "module_hints": ["dcache", "icache", "mmu", "tlb", "ptw", "load_queue", "store_queue", "memblock"],
    "note": "Spike has no TLB/cache model; route to RTL/LinkNan."
  },
  {
    "category": "PMA CSR",
    "keywords": ["pmaaddr", "pmacfg", "pma_csr"],
    "module_hints": ["csr", "pma", "mmu"],
    "note": "PMA CSR not implemented in this Spike."
  },
  {
    "category": "CBO internal line state",
    "keywords": ["cbo_line_state", "cbo_refill", "cbo_side_effect"],
    "module_hints": ["dcache", "cbo", "memblock"],
    "note": "Architectural CBO exceptions are fine; internal state is not."
  },
  {
    "category": "Ordering / queues",
    "keywords": ["replay_queue", "sbuffer", "uncache_buffer", "mshr", "rob_head", "response_context"],
    "module_hints": ["memblock", "load_queue", "store_queue", "sbuffer", "mshr", "rob"]
  },
  {
    "category": "PMA/PBMT/MMIO routing",
    "keywords": ["pma_routing", "pbmt_routing", "mmio_responder", "cacheability_routing"],
    "module_hints": ["memblock", "dcache", "pbmt", "pma"]
  },
  {
    "category": "LR/SC timeout / alias",
    "keywords": ["lr_timeout", "sc_timeout", "same_pa_diff_va", "reservation_timeout", "reservation_policy"],
    "module_hints": ["memblock", "load_queue", "atomicsunit", "reservation"]
  },
  {
    "category": "Custom CSR / instruction",
    "keywords": ["custom_csr", "custom_instruction", "nmi", "double_trap"],
    "module_hints": ["csr", "rob", "trap"]
  },
  {
    "category": "Debug trigger chain AMO (Spike gap)",
    "keywords": ["mcontrol6_chain", "trigger_chain_amo", "chain_breakpoint_amo", "chain_closed_bp"],
    "module_hints": ["atomicsunit", "trigger", "memblock"],
    "classification": "spike_gap",
    "note": "Nanhu implements spec correctly (chain mismatch suppression + chain closed BP); Spike only models the suppression path, not the chain-closed BP. Reason code: D-MANUAL-SPIKE-GAP."
  },
  {
    "category": "Debug trigger Nanhu implementation limits",
    "keywords": ["chain_depth_limit", "data_trigger", "more_than_two_triggers"],
    "module_hints": ["trigger", "atomicsunit"],
    "classification": "nanhu_not_impl",
    "note": "Nanhu only supports 2-level chain, address-trigger and execute-PC trigger; data trigger NOT implemented. Case designs targeting 3+ level chain or data trigger are out of scope. Reason code: D-MANUAL-NANHU-NOT-IMPL."
  }
]
```

Spike 结果使用口径：

- 普通 cacheable DRAM、ISA 可见、无平台私有依赖的 case，可以用 Spike 做 default gate。
- Spike fail 但场景属于上述模型边界时，先标 `manual` / `compile-only` / `blocked`；涉及 TLB/cache 一致性或访问 PMA CSR 的 case 直接按 RTL-only/LinkNan 仿真路径处理，不要直接改弱断言。
- Spike pass 也不证明 PMA/PBMT/MMIO/cache/TLB 微架构路径正确；这类仍需要 LinkNan/RTL/波形证据。

### 5.1 LR/SC 同 PA 不同 VA 口径

同 PA 不同 VA 的 LR/SC case 需要显式写清 VA alias、PA、访问宽度、地址偏移、reservation 时间窗口和 DCache 命中状态。NHV5.1AP 当前口径如下：

- 若 LR 和 SC 映射到同一 PA，访问宽度一致，访问的字节范围/地址一致，地址自然对齐，reservation 未超时，且 SC 路径不是 DCache miss，则 SC 可以成功。
- 若同 PA 不同 VA 但 VA 的 set index 不同，或者前面没有预热对应 alias 导致 SC 访问成为 DCache miss，即使宽度一致、PA/地址一致、reservation 未超时，SC 也按失败处理。
- 因此同 PA 不同 VA 的 LR/SC 成功断言必须同时保证 cache residency / set index / 预热条件；若 case 故意构造不同 set index、未预热 alias、miss/refill/replay、TLB/cache stale 等场景，不应断言 SC 必然成功。
- 这类规则依赖 LinkNan DCache/TLB/reservation 实现状态，不适合作为 official Spike default gate；默认走 RTL-only/LinkNan difftest 或 manual 分层。

## 6. 非对齐与异常优先级

当前项目口径：

- 若翻译/权限阶段已经先遇到 PF/TLB AF，则按 first encountered fault 判定。
- 标量 Device 区域非对齐按 AF 口径处理。Device 区域包括：
  - `PBMT=IO`
  - `PBMT=None` 且物理地址通过 PMA 限制为 IO 区域
- 标量 `PBMT=NC` 且 PMA 为 memory 区域时，非对齐按地址非对齐异常处理。
- 向量 `PBMT=NC` 或 `PBMT=IO` 非对齐按 AF 口径处理。
- 原子非对齐按 AF 口径处理。
- 显式访存与 Device/MMIO 非对齐、PF/TLB AF 等组合叠加时，不要机械按单一关键词改写预期；先确认 first encountered fault，再按上述访问类型和属性组合判定。
- cross-page low-half 正常、high-half fault 时，`tval` 应取 second-half 起始地址。

若同一 case 包含多种访问形态，断言文案必须标明“本条断言对应哪一类访问”。

## 7. 分层默认口径

- `default`：编译稳定、运行稳定、规则一致，且 `spike_gate_applicable=true`。
- `manual`：规则已明确，但 Spike 不宜作为 gate，或运行结果可归因但不适合常规批跑。
- `compile-only`：只保留编译与场景表达，本轮不执行 Spike/LinkNan gate。
- `blocked`：规格/环境/证据不完整，或当前 testbench 缺少必要 responder。

常见 `manual` / `compile-only` 候选：

- PMA/PBMT/MMIO/cacheability。
- TLB/cache 一致性、访问 PMA CSR、CBO/refill/replay/sbuffer/MSHR。
- PMP sub-4KB 精度假设。
- LR/SC reservation timeout、同 PA 不同 VA alias 的 DCache hit / set index 条件。
- custom CSR/instruction、NMI/double trap 等 official Spike 或本轮项目范围不支持的路径。

## 8. Spike 不一致时的 NHV5.1AP 处理流程

当 Spike 结果和预期不一致：

1. 先确认 case 是否仍在测原测试点目标，没有偷换地址类型、权限、宽度或访问顺序。
2. 判断不一致是否落在本文的 Spike 模型边界。
3. 若是普通架构 DRAM 行为，继续按 `references/build_run_debug.md` 定位断言/环境问题。
4. 若是 PMA/PBMT/MMIO/cache/TLB/CBO 等模型边界，优先转 `manual` / `compile-only` / `blocked`，必要时用 `hyptest-failure-triage` 做失败归因。
5. 不要因为单次 Spike 结果反向改写长期规则口径。

若日志表现为 stuck/timeout、Spike/LinkNan difftest mismatch、`HIT GOOD TRAP` 但 `FAILED`、50000 cycles no commit、FSDB 波形定位、或需要判断 suspected RTL bug，切到 `hyptest-failure-triage` 做失败闭环。本文只负责 profile 口径和分层默认判断，不替代失败 triage。

## 9. 本 profile 常见 reason_code 映射

通用 reason_code 定义仍以 `references/reason_code_catalog.md` 为准。本文只补 NHV5.1AP 常见场景映射，避免把项目专属例子写进通用 catalog。

- TLB/cache 一致性、stale translation、cache residency、dirty line preservation、refill image：优先 `D-MANUAL-NONGATE`，走 RTL-only/LinkNan 证据，不走 official Spike gate。
- 访问 `PMAADDR*` / `PMACFG*` 等 PMA CSR：优先 `D-MANUAL-NONGATE` 或 `compile-only`，因为本版本 official Spike 没有 PMA CSR 模型。
- PMA/PBMT/MMIO/cacheability routing、Device responder 行为：优先 `D-MANUAL-NONGATE`；若当前 testbench 没有 responder 或访问会无返回，则 `blocked`。
- LR/SC reservation timeout、同 PA 不同 VA alias 的 DCache hit / set index 条件、或其它实现特定 reservation 策略：优先 `D-MANUAL-NONGATE`。
- NMI / double trap：本轮 NHV5.1AP 常规验证范围外，默认不进入常规 default gate。
- project/custom CSR 或 custom instruction 且 official Spike 不支持：先按 official Spike model gap 归因；是否保留为 manual/compile-only 取决于测试点/项目需求。
