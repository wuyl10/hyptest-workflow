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
smrnmi: supported
vmodule_interrupt_injection: vmodule_capable_ap_it_special_run_only
vmodule_requires_compile_flag: VMODULE=1
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
- `references/reason_code_catalog.md`（**reason_code 的权威来源**；任何分层归因时先查这里）
- `references/submission_card.md`
- `references/writing_cases.md`
- `references/build_run_debug.md`

注：完整 Source Priority 见 `SKILL.md`（本文在 SKILL.md 的 §2，位于通用 Gate/tiering 规则之上；memory 不参与规则冲突裁决，仅作查询辅助）。

## 2. 项目范围

- 当前默认 no-H：不依赖 H 特有指令/CSR。
- 仓库里的 HS helper 按项目约定可作为 S 语义路径别名使用，不表示要求启用 H 扩展验证。
- 当前 NHV5.1AP 支持 Smrnmi/RNMI；`mnstatus/mnepc/mncause/mnscratch` 与 `mnret` 相关 case 属于项目验证范围。
- Smrnmi/RNMI case 需要按平台能力分层：CSR/`mnret` 基础语义在 runner 明确启用 Smrnmi 时可作为 default candidate；外部 RNMI 源、RNMI vector 注入、unexpected-trap timing、与 breakpoint/interrupt 同窗交叉通常需要 LinkNan/RTL 或 special-run 证据。
- double trap 不再和 NMI 混为“范围外”判断；只有在 Smdbltrp/Ssdbltrp、RNMI 入口和 runner oracle 都确认后才进入对应分层，否则保持 manual/compile-only/blocked。
- project/custom CSR 或 custom instruction 若 official Spike 不支持，按 official Spike model gap 处理；是否属于项目验证范围由测试点/项目需求决定，不自动等同于范围外。
- WFI 可能导致模拟器卡死；优先测试权限与控制位语义，不强制执行真实等待路径。
- 当前 NHV5.1AP / LinkNan simv 不支持运行时动态更新 `misa` 扩展位；写 `misa` 后不要假设 `C` 等扩展位可以被临时清除/打开并立即改变执行语义。
- 依赖动态清 `misa.C` 将当前核从 IALIGN=16 切到 IALIGN=32 的 case，不进入默认 selfcheck/default gate。若要测 JAL/JALR/branch 半字对齐目标 IAM，必须使用已确认支持 IALIGN=32 的构建配置，或把当前配置下的失败归为平台约束/用例假设不成立，而不是直接判 RTL 控制转移异常实现错误。

### 2.1 VModule / AP-IT 中断注入口径

VModule 是 NHV5.1AP AP-IT / 专项 RTL testbench 环境中的注入模块，可用于定向注入普通 interrupt、NMI、debug interrupt、WDT、CHI/AXI error inject 等信号；它不是 official Spike 可建模的普通 ISA 行为。当前普通 LinkNan runner 未接入 VModule 注入链路，也不能作为 VModule 注入 gate。

当用户明确要求“用 VModule”“VMODULE=1”“通过 `vm_reg` 注入中断/NMI/debug interrupt/error inject”，或测试点依赖 VModule 寄存器时，写 case 前必须先阅读并遵守仓库内文档：

- `docs/interrupt-vmodule-support/VModule模块说明.md`
- `docs/interrupt-vmodule-support/Nanhuv5.1-AP-IT环境中断产生方法说明.md`

VModule 相关 case 的默认口径：

- **选点**：当测试点/用户任务目标是“可控 interrupt 注入”“interrupt 与 breakpoint/debug trigger 交叉”“interrupt delay/到达窗口”“外部/force/timer/software 注入源”时，可以设计 VModule/AP-IT 版本，但必须先确认 runner 支持 VModule 注入；当前 LinkNan/Spike 不支持时只能作为 AP-IT/special-run 占位。CSR `mip/sip` pending 版本只可作为 architecture/default-friendly baseline 或对照组；除非测试点明确写“纯 CSR pending / official Spike default gate”，否则不能替代 VModule 注入覆盖。若已写 CSR baseline，还应继续补 VModule `vm_reg_0/vm_reg_8` 版本，或在交付摘要中明确说明 VModule 覆盖未完成。
- **分层/运行**：VModule case 的 `spike_gate_applicable=false` 且 `current_linknan_gate_applicable=false`，遵守全局“nongate 不等于低价值”原则；不要求、也不应以 official Spike 或当前普通 LinkNan run pass 作为通过门槛。Spike 只可作为普通 ISA/编译 smoke，当前 LinkNan 也只可验证非 VModule baseline；两者都不能作为 VModule 注入链路有效证据。
- **环境**：需要已确认支持 `VMODULE=1` 且接入 `vm_reg` 注入链路的 AP-IT/special-run/RTL runner。当前普通 LinkNan 与 official Spike 均不运行 VModule 注入；相关 case 应保持注释注册并标 `manual` / `compile-only` / `blocked`，不要伪装成 default。VModule case 默认不进入普通 Spike 或当前 LinkNan 回归，除非 CI/runner 明确声明自己是 VModule-capable special-run。
- **代码边界**：`VMODULE=1` 是 whole-ELF/harness 语义开关，会改变 `src/rvh_test.c` 的普通 interrupt handler pending/source clear 路径；不要把 `VMODULE=1` 当作单个 case 的局部开关。VModule-only case 优先放独立文件，用文件头和注释注册说明 special-run 口径，不在普通 CSR/default case 文件里用 per-case `#if VMODULE` 混住业务逻辑。

VModule 写 case 时的硬要求：

- 优先复用仓库已有 VModule helper；没有 helper 时再封装 `vm_reg` 写接口，不要在每个 case 中散落裸 magic。
- VModule 命令序列需要按文档使用 address command / data command；中断注入相关序列保留 `fence.i`，避免后续触发不稳定。
- `vm_reg_8` 只控制 VModule 注入到 core 顶层前的额外 delay；core 顶层到后端/ROB/trap handler 的延迟不可预测。selfcheck 不得断言固定第 N 条指令、固定 cycle 或固定单拍先后。
- VModule interrupt selfcheck 的稳定 oracle 应放在事件集合和状态合同：是否至少观察到目标 interrupt cause、pending/source 是否按 handler 清理、breakpoint/exception side effect 是否被抑制或保留、handler 返回后 marker 是否 exactly-once。不要把“官方 Spike 可跑”或“CSR pending 可设置”当作 VModule 注入链路的替代 oracle。
- level-sensitive / force 类普通 interrupt 源需要通过 VModule 对应寄存器写 0 清源；不要依赖 `CSRC(mip/sip)` 清掉所有中断 pending，因为很多外部/定时/force 源不是 CSR 写清。
- case 开始和结束都要显式清 VModule source，并恢复 `vm_reg_8=0` 或 testcase 约定值，避免污染后续 case。
- 若涉及 RNMI/NMI，检查 `mnepc/mncause/mnstatus` 和 `mnret` 路径，不用普通 `mip/mie/mstatus.MIE` oracle 判断 NMI 是否进入。
- 旧 `manual_test_cases/interrupt` 中未经审计的历史写法不作为 VModule interrupt case 的语义模板；以 profile、VModule docs、当前 harness helper 为准。

常用 VModule 寄存器摘要（以仓库 docs 为准）：

- `vm_reg_0 @ 0x1000`：普通主中断 `SEI/MEI/MTI/MSI` 注入与关闭；写 1 拉高对应源，写 0 拉低。
- `vm_reg_8 @ 0x1028`：VModule 到 core 顶层前的 delay count，不代表 handler 零延迟。
- `vm_reg_9 @ 0x1030`：直接 force NMI；`bit0=nmi_31`，`bit1=nmi_43`。
- `vm_reg_12 @ 0x1048`：force debug interrupt。
- `vm_reg_13 @ 0x1050`：CHI error inject，通过正常 error path 触发 NMI。
- `vm_reg_14 @ 0x1060`：AXI error inject。

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
- AMO/LR/SC 是否允许由有效 memory type/cacheability 与 PMA `Atomic` 位共同决定：MMIO/Device 路径无论 `Atomic` 开关与否，原子访问都不能执行；cacheable memory 且 `Atomic` 开时，原子访问能执行；cacheable memory 但 `Atomic` 关时，原子访问不能执行。相关 case 必须同时写清目标地址的 MMIO/cacheable 属性和 `Atomic` 位状态，不能只凭其中一个条件下结论。
- `MENVCFG.CBIE=Flush` 时，当前实现会把 `CBO.INVAL` 走成 flush 语义而不是普通“只失效不回写”的清线语义；具体是否触发该特殊路径还取决于当前特权级和 `CBIE` 生效层级。写 `cbo_inval` 相关 selfcheck 时，不能默认它一定只是清掉 cacheline，更不能默认它会把另一个 alias 的 NC 写入立即传播成 cacheable/backing 视图的一致值。
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

LinkNan responder/source evidence（NHV5.1AP 当前项目专属）：

- 显式 SimMMIO responder 在 `LinkNan/src/test/scala/lntest/top/SimMMIO.scala`：
  - flash: `AddressSet(0x10000000, 0x0fffffff)` → `0x10000000..0x1fffffff`，flash/ROM 语义，不作为通用 scratch。
  - UART: `AddressSet(0x40600000, 0x0000000f)` → `0x40600000..0x4060000f`，register-like。
  - IntrGen: `AddressSet(0x40070000, 0x0000ffff)` → `0x40070000..0x4007ffff`，register-like。
- IntrGen 语义在 `LinkNan/src/test/scala/lntest/peripheral/AXI4IntrGenerator.scala`：AXI slave 声明 `supportsRead/Write = TransferSizes(1, 8)`，但实现对 AW/AR assert `cache == 0`、`size == log2Ceil(regBits / 8)`、`len == 0`；当前 regBits=64 时等价于单 beat 8B register access。它可用于 8B register-style load/store，不可替代 byte/half/word lane merge、任意地址 scratch 或整行 readback。
- 普通 DRAM/cacheable memory 在 `LinkNan/src/main/scala/linknan/generator/Config.scala` 的 `pmemRange = 0x80000000..0x2000000000`，并由 `LinkNan/src/test/scala/lntest/top/DummyDramMoudle.scala` 普通 mem slave 提供 memory-like response。
- 高地址 NC window 在 `Config.scala` 的 `AddrConfig.mem_nc = (0x300_0000_0000, 0xF00_0000_0000)`；`LinkNan/src/main/scala/linknan/soc/MstAxiFabric.scala` 用 `ucMatcher` 将命中该 window 的地址走 UC 路由。是否有 memory-like response 还取决于当前 config 是否启用 `LinkNanParamsKey.extraNcMem`，以及 `DummyDramMoudle.scala` 是否创建并连接 `pciNode` / `AXI4RAMWrapper`。
- `extraNcMem` 默认值在 `LinkNan/src/main/scala/linknan/soc/LinkNanParams.scala` 为 `true`。`xmake simv` 的默认生成路径会调用 `task.run("soc", sim=true, ...)`，不传 `pldm_verilog`，因此若它重新生成 RTL，默认保持 `extraNcMem=true`；`xmake soc --sim --pldm_verilog` / `xmake soc -s -p` 会在 `xmake.lua` 里追加 `--no-extra-nc-mem`，经 `SimArgParser.scala` 改成 `extraNcMem=false`。若 `xmake simv --no_build_chisel` 或复用已有 build，则不改变已有 RTL 的该配置，只能按当前生成产物确认。
- Zhujiang AXI/TL xbar matcher 是按 slave matcher gate ready/valid；当前 `BaseAxiXbar.scala` / `BaseTLULXbar.scala` 未匹配地址没有 profile 保证的默认 error response。若目标 PA 不落在当前连接的 responder/memory window，可能表现为请求不被接受或无返回，需用 waveform 定位具体卡点。

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
  },
  {
    "id": "linknan_simmmio_flash",
    "target": "0x10000000-0x20000000_flash",
    "responder_type": "testbench_dependent",
    "memory_like_scratch": false,
    "default_decision": "manual_for_flash_semantics_only",
    "source": "LinkNan/src/test/scala/lntest/top/SimMMIO.scala",
    "notes": "AXI4Flash responder; not arbitrary writable MMIO scratch"
  },
  {
    "id": "linknan_simmmio_uart",
    "target": "0x40600000-0x40600010_uart",
    "responder_type": "register-like",
    "memory_like_scratch": false,
    "default_decision": "manual_for_uart_semantics_only",
    "source": "LinkNan/src/test/scala/lntest/top/SimMMIO.scala",
    "notes": "small UART register window"
  },
  {
    "id": "linknan_simmmio_intrgen",
    "target": "0x40070000-0x40080000_intrgen",
    "responder_type": "register-like",
    "memory_like_scratch": false,
    "default_decision": "manual_for_register_8b_semantics_only",
    "source": "LinkNan/src/test/scala/lntest/top/SimMMIO.scala; LinkNan/src/test/scala/lntest/peripheral/AXI4IntrGenerator.scala",
    "notes": "supports register-like single-beat 8B access in current implementation; not arbitrary byte/half/word or whole-line scratch"
  },
  {
    "id": "linknan_extra_nc_mem",
    "target": "0x30000000000-0x40000000000_extra_nc_mem",
    "responder_type": "testbench_dependent",
    "memory_like_scratch": true,
    "default_decision": "manual_or_blocked_until_current_config_confirms_extraNcMem",
    "source": "LinkNan/src/main/scala/linknan/generator/Config.scala; LinkNan/src/test/scala/lntest/top/DummyDramMoudle.scala; LinkNan/src/main/scala/linknan/soc/MstAxiFabric.scala",
    "notes": "spec/window is allowed for multiple PMA/PBMT rows, but current simv must prove extraNcMem/AXI4RAMWrapper is present and response path closes"
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
- 运行时动态更新 `misa` 扩展位，以及依赖动态清 `misa.C` 切换 IALIGN=32 的场景。当前 NHV5.1AP / LinkNan simv 不支持这类动态切换；相关 case 不能按普通 default gate 判断。
- LR/SC reservation timeout、同 PA 不同 VA 的 cache hit / set index 条件、或其它实现特定 reservation 策略。
- project/custom CSR、custom instruction 等 selected runner 不支持的路径。
- Smrnmi/RNMI 外部源、RNMI vector 注入、unexpected-trap timing、以及 double-trap 交叉场景只有在 runner/testbench oracle 明确时才可作为 default gate；否则走 manual/LinkNan/RTL 或 compile-only。
- VModule / AP-IT 注入的普通 interrupt、NMI、debug interrupt、WDT、CHI/AXI error inject 等场景不走 official Spike default gate。Spike 不会通过 VModule 寄存器真实拉高 RTL/testbench 注入信号；即使指令流在 Spike 上执行，也只能作为编译或普通 ISA smoke。VModule 选点优先级与自检 oracle 见 §2.1。
- Debug trigger: `mcontrol6` chain 闭合后 AMO 的 breakpoint 语义在 Spike 不建模——chain mismatch 抑制路径在 Spike 上可观测（符合 spec），但 chain 闭合后 spec 要求的 BP 在 Spike 不抛（详见 `test_point/Manual_Reference.md#C7`）。

**Nanhu NHV5.1AP Debug trigger 实现约束**（Nanhu 侧的裁剪，超出部分 **测试点本身不应设计**）：

- 当前源码口径：debug trigger 总 slot 数为 **4**，`TriggerNum = 4`；合法 `tselect` 编号为 `0..3`。写 `tselect >= 4` 不会选中新 slot，而是保持原 `tselect`。
- chain 最大合法长度为 **2 层**，`TriggerChainMaxLength = 2`；这只限制一次 chain 的级联深度，不等于“总共只有 2 个 slot”。case 可以使用 `slot0/slot1` 或 `slot2/slot3` 组成 2 层 chain，但不能设计 3 层及以上 chain。
- 仅支持 **address trigger（访存地址）** 和 **execute-PC trigger（取指地址）**。
- **不支持 data trigger**（trigger 匹配数据值）；相关 case 不应设计。
- FOF / fault-only-first vector load（`vle*ff.v`、`vlseg*e*ff.v`）的非 0 元素后续异常上报只适用于 Data trigger 语义；NHV5.1AP 不支持 Data trigger，因此非 0 元素的 address trigger 命中不应上报 breakpoint/debug exception，不应设置 `excpt.triggered` / `CAUSE_BKP` / `tval` / `vstart`，也不应仅因此截断 `vl` 或屏蔽元素写回。期望 FOF 非 0 元素 address trigger 报异常的 case 属于 profile-invalid/selfcheck bug；若 Spike/ref model 将其当成 breakpoint 或 `vl` 截断，则按 Spike/model gap 处理。
- 源码证据：`LinkNan/dependencies/nanhu/src/main/scala/xiangshan/Parameters.scala` 定义 `TriggerNum = 4`、`TriggerChainMaxLength = 2`；CSR/DebugLevel 中 `tdata1/tdata2` 用 `Seq.fill(TriggerNum)` / `Range(0, TriggerNum)` 生成，`tselect` 写入以 `wdata < TriggerNum.U` 为合法条件。

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
    "keywords": ["custom_csr", "custom_instruction"],
    "module_hints": ["csr", "rob", "trap"]
  },
  {
    "category": "Smrnmi/RNMI source and timing",
    "keywords": ["smrnmi", "rnmi", "nmi_source", "rnmi_vector", "rnmi_injection", "unexpected_trap", "mnstatus_nmie", "mnepc", "mncause", "mnret", "double_trap"],
    "module_hints": ["csr", "rob", "trap", "interrupt"],
    "classification": "platform_guarded",
    "note": "NHV5.1AP supports Smrnmi/RNMI. Basic CSR/mnret semantics can be tested when the runner enables Smrnmi; external RNMI source/vector/timing and double-trap cross scenarios need runner/testbench/RTL evidence before default gate."
  },
  {
    "category": "VModule / AP-IT interrupt injection",
    "keywords": ["vmodule", "vm_reg", "VMODULE=1", "HYPTEST_VMODULE", "vmodule_interrupt", "vm_reg_0", "vm_reg_8", "vm_reg_9", "vm_reg_12", "vm_reg_13", "vm_reg_14", "force_nmi", "debug_interrupt", "chi_error_inject", "axi_error_inject"],
    "module_hints": ["interrupt", "csr", "trap", "vmodule", "linknan"],
    "classification": "rtl_testbench_only",
    "note": "VModule/AP-IT injection is RTL/testbench controlled. Must read docs/interrupt-vmodule-support before writing cases. official Spike and current ordinary LinkNan are not valid gates; use only a confirmed VMODULE=1 VModule-capable AP-IT/special-run/RTL runner, otherwise keep manual/compile-only/blocked."
  },
  {
    "category": "Runtime misa update / IALIGN32 dynamic switch",
    "keywords": ["misa_dynamic", "misa_update", "misa_c_clear", "misa_c_toggle", "ialign32_dynamic", "ialign32", "clear_misa_c"],
    "module_hints": ["csr", "trap", "frontend", "branch", "exception_priority"],
    "classification": "nanhu_not_impl",
    "note": "Current NHV5.1AP / LinkNan simv does not support runtime dynamic misa extension-bit updates. Cases that clear misa.C to force IALIGN=32 should not be default-gated unless a dedicated IALIGN=32 build/config is confirmed. Reason code: D-MANUAL-NANHU-NOT-IMPL or blocked/manual platform-constraint handling."
  },
  {
    "category": "Debug trigger chain AMO (Spike gap)",
    "keywords": ["mcontrol6_chain", "trigger_chain_amo", "chain_breakpoint_amo", "chain_closed_bp"],
    "module_hints": ["atomicsunit", "trigger", "memblock"],
    "classification": "spike_gap",
    "note": "Nanhu implements spec correctly (chain mismatch suppression + chain closed BP); Spike only models the suppression path, not the chain-closed BP. Reason code: D-MANUAL-SPIKE-GAP."
  },
  {
    "category": "Vector FOF nonzero address trigger",
    "keywords": ["fof_address_trigger", "fof_nonzero_trigger", "vleff_address_trigger", "vlsegff_address_trigger"],
    "module_hints": ["memblock", "load_queue", "trigger", "vector"],
    "classification": "spike_gap",
    "note": "NHV5.1AP does not support Data trigger. For FOF loads, nonzero-element address-trigger matches must not raise breakpoint/debug exception or truncate vl; Spike/ref behavior that does so is a model gap."
  },
  {
    "category": "Debug trigger Nanhu implementation limits",
    "keywords": ["chain_depth_limit", "data_trigger", "more_than_two_triggers", "trigger_num", "trigger_slot", "tselect_range", "TriggerNum", "TriggerChainMaxLength"],
    "module_hints": ["trigger", "atomicsunit"],
    "classification": "nanhu_not_impl",
    "note": "Nanhu NHV5.1AP has 4 debug trigger slots (TriggerNum=4, legal tselect 0..3) but only supports 2-level chain (TriggerChainMaxLength=2), address-trigger and execute-PC trigger; data trigger is NOT implemented. Case designs targeting 3+ level chain or data trigger are out of scope. Reason code: D-MANUAL-NANHU-NOT-IMPL."
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
- 标量 `PBMT=NC` 会覆盖 PMA 的 memory/IO 区域分类；无论 PMA 命中 memory 还是 IO/MMIO 区域，标量非对齐都按地址非对齐异常处理。
- 普通标量访问 cacheable 区域时，非对齐 load/store 不触发异常；实现按 cacheable 数据通路处理非对齐访问，不应期望 LAM/SAM。
- 向量 `PBMT=NC` 或 `PBMT=IO` 非对齐按 AF 口径处理。
- 原子非对齐按 AF 口径处理。
- 显式访存与 Device/MMIO 非对齐、PF/TLB AF 等组合叠加时，不要机械按单一关键词改写预期；先确认 first encountered fault，再按上述访问类型和属性组合判定。
- cross-page low-half 正常、high-half fault 时，`tval` 应取 second-half 起始地址。
- `sd` 跨页或跨 16B split 时，若后半部分发生 PF/AF 等异常，`tval` 应取 split 后的错误地址；整条 store 不产生部分写入，前半部分即使权限/属性检查本身无异常也不能写入 backing memory。相关 case 不应断言 legal first fragment 可见，故障修复前应检查前后 split fragment 均保持原值。

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
- custom CSR/instruction 等 selected runner 不支持的路径。
- Smrnmi/RNMI 外部源、RNMI vector 注入、unexpected-trap timing、double-trap 交叉等缺少 runner/testbench oracle 的路径。
- VModule / AP-IT 注入普通 interrupt、NMI、debug interrupt、WDT、CHI/AXI error inject 等 RTL/testbench-only 场景。

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
- Smrnmi/RNMI：NHV5.1AP 支持。CSR/`mnret` 基础语义在 runner 明确启用 Smrnmi 时可走 default candidate；RNMI 外部源/vector/timing、unexpected trap 以及 double-trap 交叉优先 `D-MANUAL-NONGATE` 或 special-run，缺少注入/观测路径时转 `compile-only` / `blocked`。
- VModule / AP-IT 注入：通常用 `D-MANUAL-NONGATE`，因为注入源来自 AP-IT/VModule-capable RTL testbench，不是 official Spike 可建模行为，且当前普通 LinkNan runner 不运行 VModule 注入链路；若 case 的主要 oracle 必须依赖 RTL 内部信号/波形才能观察，可用 `D-MANUAL-RTL-ONLY`。若只有编译环境、没有已确认的 `VMODULE=1` special-run 环境，则 `compile-only`；若当前 testbench 不支持对应 `vm_reg` 或注入源无响应，则 `blocked`。不要因该分层把 VModule 场景替换成 CSR pending default baseline，也不要把当前 LinkNan/Spike run 当作 VModule gate。
- project/custom CSR 或 custom instruction 且 official Spike 不支持：先按 official Spike model gap 归因；是否保留为 manual/compile-only 取决于测试点/项目需求。
