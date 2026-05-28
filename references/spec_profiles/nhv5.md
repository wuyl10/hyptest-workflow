# NHV5 规格与平台模型边界

本文是 NHV5 当前项目 profile。写 NHV5 case、判断 official Spike/LinkNan 结果、决定 default/manual/compile-only/blocked 时，以本文作为项目专属规则入口。

具体 harness/API 用法看 `references/framework_usage_pitfalls.md`，编译运行看 `references/build_run_debug.md`。

```hyptest-profile
profile: nhv5
project_or_core: NHV5
default_privilege_scope: no-H-no-V
pmp_granularity: 4KB
official_spike_has_tlb_model: false
official_spike_has_cache_model: false
official_spike_has_pma_csr: false
default_spike_gate: ordinary_cacheable_dram_arch_only
default_case_elf_dir: case_elf_asm
linknan_mmio_requires_responder: true
smrnmi: not_default_or_unconfirmed
vmodule_interrupt_injection: not_default_plain_nhv5
vmodule_requires_compile_flag: unsupported_in_plain_nhv5
vmodule_spike_gate_applicable: false
vmodule_current_linknan_gate_applicable: false
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
- `references/reason_code_catalog.md`（reason_code 的权威来源）
- `references/submission_card.md`
- `references/writing_cases.md`
- `references/build_run_debug.md`

注：完整 Source Priority 见 `SKILL.md`。本文位于通用 Gate/tiering 规则之上；memory 不参与规则冲突裁决，仅作查询辅助。

## 2. 项目范围

- 当前 NHV5 默认配置不启用 V 扩展，也不启用 H 扩展；case 不能依赖 RVV/vector 指令、vector CSR、VS/G-stage、HLV/HSV、HFENCE、H-extension CSR 或 H 扩展异常语义。
- 仓库里的 `hs`/`hu` 命名和 helper 是历史路径命名，按项目约定可分别当作 S/U 语义路径别名使用；它们不表示启用 H 扩展，也不表示进入 HS/VS 两级虚拟化语义。
- `compile_elf.py` 默认应保持 `ENABLE_V_EXT=0`、`ENABLE_H_EXT=0` 口径。带 `vector`、`rvv`、`vset*`、`vle/vse`、`vcsr/vtype/vl/vstart`、`hgatp/vsatp/hstatus/vsstatus`、`hfence/hlv/hsv` 等硬依赖的 case 不进入本 profile 默认回归。
- 当前 profile 目标是最大化保留 NHV5 可运行的普通 M/S/U、PMP/PTE/Svpbmt、异常、trigger、interrupt、memblock 标量路径用例。来自 NHV5.1AP 的 case 迁入时，应只做最小语义改动：删除 V/H 专属片段、保留可映射到 M/S/U 标量路径的断言。
- Smrnmi/RNMI 在本 profile 不作为默认已启用能力。若目标 runner 明确支持 Smrnmi/RNMI，可以按专门任务补充 profile override 或新增 profile；缺少 runner/oracle 前，RNMI 外部源、vector 注入、unexpected-trap timing、double-trap 交叉不进 default。
- VModule/AP-IT 注入模块不属于普通 NHV5 默认运行口径。任何依赖 `vm_reg`、`VMODULE=1`、force NMI/debug interrupt/error inject 的 case，默认视为 plain NHV5 范围外或 special-run 占位，不应混进普通 NHV5 default 回归。
- project/custom CSR 或 custom instruction 若 official Spike 不支持，按 official Spike model gap 处理；是否属于项目验证范围由测试点/项目需求决定，不自动等同于范围外。
- WFI 可能导致模拟器卡死；优先测试权限与控制位语义，不强制执行真实等待路径。
- 当前 NHV5/LinkNan simv 不假设支持运行时动态更新 `misa` 扩展位；写 `misa` 后不要假设 `C` 等扩展位可以被临时清除/打开并立即改变执行语义。
- 依赖动态清 `misa.C` 将当前核从 IALIGN=16 切到 IALIGN=32 的 case，不进入默认 selfcheck/default gate。若要测 JAL/JALR/branch 半字对齐目标 IAM，必须使用已确认支持 IALIGN=32 的构建配置，或把当前配置下的失败归为平台约束/用例假设不成立。

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
- AMO/LR/SC 是否允许由有效 memory type/cacheability 与 PMA `Atomic` 位共同决定：MMIO/Device 路径无论 `Atomic` 开关与否，原子访问都不能执行；cacheable memory 且 `Atomic` 开时，原子访问能执行；cacheable memory 但 `Atomic` 关时，原子访问不能执行。
- M-mode direct physical read/write 或 cacheable alias 访问没有 PBMT=NC 属性；PBMT=NC store/load 的自校验不要用后续 `read64(paddr)`、普通 M-mode direct 访问、或 cacheable alias convergence 作为唯一 oracle。若测试意图是验证 NC 路径本身，应优先通过同一个 PBMT=NC alias seed/readback；若测试意图确实是跨 cacheable/NC 视图一致性，必须额外建立 flush/ordering/responder 条件并把该语义写清楚。

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

LinkNan responder/source evidence（当前 NHV5 项目口径）：

- 普通 DRAM/cacheable memory 使用 `0x80000000..0x2000000000` 这类 memory-like response 路径。
- 低地址或高地址 Device/MMIO window 是否有返回路径取决于当前 testbench 连接，不能只按 PA 合法性推导。
- register-like responder 只适合对应寄存器语义，不替代任意地址 scratch。
- 若当前 simv 复用已有 build，profile 不能假设额外 NC memory 或 MMIO responder 已存在；必须按当前生成产物、log 或波形确认。

机器可读 responder 表：

```hyptest-mmio-responder-matrix
[
  {
    "id": "dram_cacheable",
    "target": "ordinary_dram_cacheable",
    "responder_type": "memory",
    "memory_like_scratch": true,
    "spike_gate_applicable": true,
    "default_decision": "default_candidate_if_no_other_model_limit",
    "notes": "ordinary cacheable DRAM can be used for normal architectural Spike gate cases"
  },
  {
    "id": "device_low_0_2g",
    "target": "0x0-0x80000000_device_mmio",
    "responder_type": "testbench_dependent",
    "memory_like_scratch": false,
    "spike_gate_applicable": false,
    "default_decision": "manual_or_blocked_until_responder_confirmed",
    "notes": "legal PMA/PBMT combination is not enough; no simulated IO return can hang"
  },
  {
    "id": "device_high_3t_4t",
    "target": "0x30000000000-0x40000000000_device_mmio",
    "responder_type": "testbench_dependent",
    "memory_like_scratch": false,
    "spike_gate_applicable": false,
    "default_decision": "manual_or_blocked_until_responder_confirmed",
    "notes": "allowed window still needs a concrete responder and width/readback support"
  },
  {
    "id": "register_like_peripheral",
    "target": "uart_intrgen_or_register_like_peripheral",
    "responder_type": "register-like",
    "memory_like_scratch": false,
    "spike_gate_applicable": false,
    "default_decision": "manual_for_device_specific_semantics_only",
    "notes": "does not replace arbitrary-address memory-like MMIO scratch"
  },
  {
    "id": "extra_nc_mem",
    "target": "0x30000000000-0x40000000000_extra_nc_mem",
    "responder_type": "testbench_dependent",
    "memory_like_scratch": true,
    "spike_gate_applicable": false,
    "default_decision": "manual_or_blocked_until_current_config_confirms_extraNcMem",
    "notes": "NC window can be memory-like only after current testbench config proves a response path exists"
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
- 运行时动态更新 `misa` 扩展位，以及依赖动态清 `misa.C` 切换 IALIGN=32 的场景。当前 NHV5/LinkNan simv 不支持这类动态切换；相关 case 不能按普通 default gate 判断。
- LR/SC reservation timeout、同 PA 不同 VA 的 cache hit / set index 条件、或其它实现特定 reservation 策略。
- project/custom CSR、custom instruction 等 selected runner 不支持的路径。
- Smrnmi/RNMI 外部源、RNMI vector 注入、unexpected-trap timing、double-trap 交叉等不属于本 profile 默认 gate；除非 runner/profile 另行确认支持。
- VModule/AP-IT 注入普通 interrupt、NMI、debug interrupt、WDT、CHI/AXI error inject 等不属于 plain NHV5 default gate。它们既不是 official Spike 可建模行为，也不是普通 NHV5 runner 默认覆盖范围。
- V 扩展/RVV/vector 指令、vector CSR、vector misalignment 等场景属于本 profile 范围外；不要把 vector case 注释注册保留为 NHV5 default 候选。
- H 扩展/VS/G-stage/HLV/HSV/HFENCE 等场景属于本 profile 范围外；`hs` 名称只能按 S 语义别名处理。
- Debug trigger 中 data trigger、3 层及以上 chain、超出当前 trigger slot 数的设计，若没有 NHV5 实现证据，不应设计为 default case。

机器可读 nongate keyword 速查（供 `scripts/query_spec_profile.py --nongate-summary` 使用；与上文 prose 保持一致，prose 仍为真值）：

```hyptest-nongate-keywords
[
  {
    "category": "V extension out of scope",
    "keywords": ["rvv", "vector", "vset", "vle", "vse", "vtype", "vl", "vstart", "vcsr", "v_ext", "ENABLE_V_EXT"],
    "module_hints": ["vector", "memblock", "translation", "interrupt"],
    "classification": "nanhu_not_impl_for_plain_nhv5",
    "note": "Plain NHV5 profile is no-V. Delete or rewrite vector-only case content into scalar M/S/U coverage before enabling."
  },
  {
    "category": "H extension out of scope",
    "keywords": ["hgatp", "vsatp", "vsstatus", "hstatus", "hlv", "hsv", "hfence", "g_stage", "two_stage", "ENABLE_H_EXT"],
    "module_hints": ["translation", "csr", "trap", "interrupt", "memblock"],
    "classification": "nanhu_not_impl_for_plain_nhv5",
    "note": "Plain NHV5 profile is no-H. HS/HU helper names are S/U aliases only and must not imply H-extension behavior."
  },
  {
    "category": "TLB/cache consistency",
    "keywords": ["tlb", "cache", "stale_translation", "cache_residency", "dirty_line", "refill", "cacheline"],
    "module_hints": ["dcache", "icache", "mmu", "tlb", "ptw", "load_queue", "store_queue", "memblock"],
    "classification": "rtl_testbench_only",
    "note": "Spike has no TLB/cache model; route to RTL/LinkNan."
  },
  {
    "category": "PMA CSR",
    "keywords": ["pmaaddr", "pmacfg", "pma_csr"],
    "module_hints": ["csr", "pma", "mmu"],
    "classification": "spike_gap",
    "note": "PMA CSR is not implemented in this Spike."
  },
  {
    "category": "CBO internal line state",
    "keywords": ["cbo_line_state", "cbo_refill", "cbo_side_effect"],
    "module_hints": ["dcache", "cbo", "memblock"],
    "classification": "rtl_testbench_only",
    "note": "Architectural CBO exceptions are fine; internal state is not."
  },
  {
    "category": "Ordering / queues",
    "keywords": ["replay_queue", "sbuffer", "uncache_buffer", "mshr", "rob_head", "response_context"],
    "module_hints": ["memblock", "load_queue", "store_queue", "sbuffer", "mshr", "rob"],
    "classification": "rtl_testbench_only"
  },
  {
    "category": "PMA/PBMT/MMIO routing",
    "keywords": ["pma_routing", "pbmt_routing", "mmio_responder", "cacheability_routing", "pbmt_nc", "pbmt_io"],
    "module_hints": ["memblock", "dcache", "pbmt", "pma"],
    "classification": "platform_guarded"
  },
  {
    "category": "NHV5 strict misalignment",
    "keywords": ["misaligned", "unaligned", "crosspage", "split_load", "split_store", "nonaligned", "non_aligned"],
    "module_hints": ["memblock", "load_queue", "store_queue", "atomicsunit", "translation"],
    "classification": "profile_specific_behavior",
    "note": "NHV5 does not support ordinary misaligned scalar access. Ordinary scalar MEM/NC misaligned raises address-misaligned; atomic/LRSC, PBMT=IO and PMA IO misaligned raise access fault."
  },
  {
    "category": "LR/SC timeout / alias",
    "keywords": ["lr_timeout", "sc_timeout", "same_pa_diff_va", "reservation_timeout", "reservation_policy"],
    "module_hints": ["memblock", "load_queue", "atomicsunit", "reservation"],
    "classification": "rtl_testbench_only"
  },
  {
    "category": "Custom CSR / instruction",
    "keywords": ["custom_csr", "custom_instruction"],
    "module_hints": ["csr", "rob", "trap"],
    "classification": "spike_gap"
  },
  {
    "category": "Smrnmi/RNMI not default",
    "keywords": ["smrnmi", "rnmi", "nmi_source", "rnmi_vector", "rnmi_injection", "unexpected_trap", "mnstatus_nmie", "mnepc", "mncause", "mnret", "double_trap"],
    "module_hints": ["csr", "rob", "trap", "interrupt"],
    "classification": "platform_guarded",
    "note": "Plain NHV5 profile does not assume Smrnmi/RNMI by default. Use a confirmed runner/profile override before default gate."
  },
  {
    "category": "VModule / AP-IT interrupt injection",
    "keywords": ["vmodule", "vm_reg", "VMODULE=1", "HYPTEST_VMODULE", "vmodule_interrupt", "vm_reg_0", "vm_reg_8", "vm_reg_9", "vm_reg_12", "vm_reg_13", "vm_reg_14", "force_nmi", "debug_interrupt", "chi_error_inject", "axi_error_inject"],
    "module_hints": ["interrupt", "csr", "trap", "vmodule", "linknan"],
    "classification": "out_of_scope_plain_nhv5",
    "note": "VModule/AP-IT injection is not part of plain NHV5 default regression. Keep out or move to a dedicated special-run profile."
  },
  {
    "category": "Runtime misa update / IALIGN32 dynamic switch",
    "keywords": ["misa_dynamic", "misa_update", "misa_c_clear", "misa_c_toggle", "ialign32_dynamic", "ialign32", "clear_misa_c"],
    "module_hints": ["csr", "trap", "frontend", "branch", "exception_priority"],
    "classification": "nanhu_not_impl",
    "note": "Current NHV5 / LinkNan simv does not support runtime dynamic misa extension-bit updates. Cases that clear misa.C to force IALIGN=32 should not be default-gated unless a dedicated IALIGN=32 build/config is confirmed."
  },
  {
    "category": "Debug trigger implementation limits",
    "keywords": ["chain_depth_limit", "data_trigger", "more_than_two_triggers", "trigger_num", "trigger_slot", "tselect_range", "TriggerNum", "TriggerChainMaxLength"],
    "module_hints": ["trigger", "atomicsunit"],
    "classification": "nanhu_not_impl",
    "note": "Unless current NHV5 source proves support, do not design data trigger or 3+ level chain cases as default coverage."
  }
]
```

Spike 结果使用口径：

- 普通 cacheable DRAM、ISA 可见、无平台私有依赖的 case，可以用 Spike 做 default gate。
- Spike fail 但场景属于上述模型边界时，先标 `manual` / `compile-only` / `blocked`；涉及 TLB/cache 一致性或访问 PMA CSR 的 case 直接按 RTL-only/LinkNan 仿真路径处理，不要直接改弱断言。
- Spike pass 也不证明 PMA/PBMT/MMIO/cache/TLB 微架构路径正确；这类仍需要 LinkNan/RTL/波形证据。

### 5.1 LR/SC 同 PA 不同 VA 口径

同 PA 不同 VA 的 LR/SC case 需要显式写清 VA alias、PA、访问宽度、地址偏移、reservation 时间窗口和 DCache 命中状态。NHV5 当前口径如下：

- 若 LR 和 SC 映射到同一 PA，访问宽度一致，访问的字节范围/地址一致，地址自然对齐，reservation 未超时，且 SC 路径不是 DCache miss，则 SC 可以成功。
- 若同 PA 不同 VA 但 VA 的 set index 不同，或者前面没有预热对应 alias 导致 SC 访问成为 DCache miss，即使宽度一致、PA/地址一致、reservation 未超时，SC 也按失败处理。
- 因此同 PA 不同 VA 的 LR/SC 成功断言必须同时保证 cache residency / set index / 预热条件；若 case 故意构造不同 set index、未预热 alias、miss/refill/replay、TLB/cache stale 等场景，不应断言 SC 必然成功。
- 这类规则依赖 LinkNan DCache/TLB/reservation 实现状态，不适合作为 official Spike default gate；默认走 RTL-only/LinkNan difftest 或 manual 分层。

## 6. 非对齐与异常优先级

当前 NHV5 项目不支持非对齐访问。迁入或修改 NHV5.1AP 用例时，凡原来依赖普通非对齐成功、跨页 split 成功、vector 非对齐、或把普通 cacheable 非对齐当作可执行路径的部分，都必须改成以下 NHV5 口径，或删除无法映射到标量 NHV5 的部分。

当前项目口径：

- 普通标量 load/store 非对齐访问会触发地址非对齐异常；这包括普通 cacheable DRAM 路径。
- `PBMT=NC`（PBMT=1）普通标量 load/store 非对齐访问仍触发地址非对齐异常。
- 原子、AMO、LR/SC 非对齐访问触发 access fault。
- `PBMT=IO`（PBMT=2）非对齐访问触发 access fault。
- PMA IO / MMIO / Device 非对齐访问触发 access fault；IO 非对齐不按普通地址非对齐处理。
- 本 profile 无 V 扩展；vector 非对齐相关断言应删除，或改写成等价的标量普通/原子/LRSC/PBMT/IO 非对齐断言。
- 若翻译/权限阶段已经先遇到 PF/TLB AF，按当前流水线 first encountered fault 判定；不要在尚未拿到物理属性或权限失败已经发生的场景中机械套用 PBMT/IO 非对齐结论。
- 对非对齐异常的 `tval`，默认检查触发该访问的有效地址；若 case 组合了跨页、权限、PMP/PMA 或 split helper，断言文案必须标明期待的是地址非对齐、access fault、PF 还是 TLB/PMP AF。
- 因 NHV5 不支持普通非对齐成功路径，case 不应断言“first fragment 可见”“second fragment fault 后前半写入保留”“跨页 low-half 正常 high-half fault”等 split-side-effect 行为。相关 NHV5 case 应改成异常分类和无部分写入检查。

若同一 case 包含多种访问形态，断言文案必须标明“本条断言对应哪一类访问”。

## 7. 分层默认口径

- `default`：编译稳定、运行稳定、规则一致，且 `spike_gate_applicable=true`。典型候选是普通 cacheable DRAM、ISA 可见、无平台私有依赖、无 V/H/RNMI/VModule/Device responder 依赖的标量 case。
- `manual`：规则已明确，但 Spike 不宜作为 gate，或运行结果可归因但不适合常规批跑。
- `compile-only`：只保留编译与场景表达，本轮不执行 Spike/LinkNan gate。
- `blocked`：规格/环境/证据不完整，或当前 testbench 缺少必要 responder。

本 profile 下 `spike_gate_applicable` 的判定原则：

- 普通 M/S/U、普通 cacheable DRAM、自然对齐标量 load/store/AMO/LRSC、普通异常/CSR/PTE/PMP 行为，若 selected runner 支持且不依赖平台私有路径，可以作为 default 候选。
- 任何 V 扩展、H 扩展、VModule/AP-IT 注入、未确认 Smrnmi/RNMI、TLB/cache 内部一致性、PMA CSR、PBMT/MMIO/cacheability routing、Device responder、同 PA 不同 VA reservation 策略、runtime `misa` 动态切换，都先视为 `spike_gate_applicable=false`。
- 非对齐 case 只有在断言改成 NHV5 当前异常口径后才可进入对应分层；普通标量 MEM/NC 非对齐可以作为架构/实现口径 default 候选，Device/PBMT IO/原子/LRSC/PMA routing 相关通常需要 manual 或 LinkNan 证据。

常见 `manual` / `compile-only` / `blocked` 候选：

- PMA/PBMT/MMIO/cacheability。
- TLB/cache 一致性、访问 PMA CSR、CBO/refill/replay/sbuffer/MSHR。
- PMP sub-4KB 精度假设。
- LR/SC reservation timeout、同 PA 不同 VA alias 的 DCache hit / set index 条件。
- custom CSR/instruction 等 selected runner 不支持的路径。
- Smrnmi/RNMI 外部源、RNMI vector 注入、unexpected-trap timing、double-trap 交叉等缺少 runner/testbench oracle 的路径。
- VModule/AP-IT 注入普通 interrupt、NMI、debug interrupt、WDT、CHI/AXI error inject 等 special-run 场景。
- 无法删除或改写的 V 扩展/RVV/vector-only 和 H 扩展/VS/G-stage-only case。

## 8. Spike 不一致时的 NHV5 处理流程

当 Spike 结果和预期不一致：

1. 先确认 case 是否仍在测原测试点目标，没有偷换地址类型、权限、宽度、访问顺序、扩展依赖或 profile。
2. 判断不一致是否落在本文的 Spike 模型边界。
3. 若是普通架构 DRAM 行为，继续按 `references/build_run_debug.md` 定位断言/环境问题。
4. 若是 PMA/PBMT/MMIO/cache/TLB/CBO 等模型边界，优先转 `manual` / `compile-only` / `blocked`，必要时用 `hyptest-failure-triage` 做失败归因。
5. 若不一致来自 V/H/RVV/VModule/RNMI 等本 profile 范围外能力，不要为了保留数量而弱化成 default；应删除范围外片段、改写为 no-V/no-H 标量等价路径，或转专门 profile。
6. 不要因为单次 Spike 结果反向改写长期规则口径。

若日志表现为 stuck/timeout、Spike/LinkNan difftest mismatch、`HIT GOOD TRAP` 但 `FAILED`、50000 cycles no commit、FSDB 波形定位、或需要判断 suspected RTL bug，切到 `hyptest-failure-triage` 做失败闭环。本文只负责 profile 口径和分层默认判断，不替代失败 triage。

## 9. 本 profile 常见 reason_code 映射

通用 reason_code 定义仍以 `references/reason_code_catalog.md` 为准。本文只补 NHV5 常见场景映射，避免把项目专属例子写进通用 catalog。

- TLB/cache 一致性、stale translation、cache residency、dirty line preservation、refill image：优先 `D-MANUAL-NONGATE`，走 RTL-only/LinkNan 证据，不走 official Spike gate。
- 访问 `PMAADDR*` / `PMACFG*` 等 PMA CSR：优先 `D-MANUAL-NONGATE` 或 `compile-only`，因为本版本 official Spike 没有 PMA CSR 模型。
- PMA/PBMT/MMIO/cacheability routing、Device responder 行为：优先 `D-MANUAL-NONGATE`；若当前 testbench 没有 responder 或访问会无返回，则 `blocked`。
- 原子、AMO、LR/SC 非对齐、PBMT=IO 非对齐、PMA IO/MMIO 非对齐：若 case 只验证 NHV5 当前异常口径且 runner 支持，可按普通异常用例处理；若同时依赖 PMA/PBMT/MMIO routing 或 responder，则优先 `D-MANUAL-NONGATE`。
- 普通标量 MEM/NC 非对齐：按 NHV5 地址非对齐异常口径处理；原来期待 split 成功或部分写入的 NHV5.1AP 用例，应改写断言或删除相关片段。
- LR/SC reservation timeout、同 PA 不同 VA alias 的 DCache hit / set index 条件、或其它实现特定 reservation 策略：优先 `D-MANUAL-NONGATE`。
- V 扩展/RVV/vector-only case：plain NHV5 不保留；能改成标量等价路径就改，不能改则删除或移出本 profile。
- H 扩展/VS/G-stage-only case：plain NHV5 不保留；`hs` 命名可改按 S 语义，但 H 专属 CSR/指令/两级翻译路径应删除或移出本 profile。
- Smrnmi/RNMI：本 profile 不默认支持。基础 CSR/`mnret` 只有在 runner 明确启用后才可走 default candidate；RNMI 外部源/vector/timing、unexpected trap 以及 double-trap 交叉优先 `D-MANUAL-NONGATE` 或 special-run，缺少注入/观测路径时转 `compile-only` / `blocked`。
- VModule/AP-IT 注入：plain NHV5 默认不保留。若未来确实需要，应建 dedicated special-run profile；不要放在 `nhv5` default 回归里。
- project/custom CSR 或 custom instruction 且 official Spike 不支持：先按 official Spike model gap 归因；是否保留为 manual/compile-only 取决于测试点/项目需求。
