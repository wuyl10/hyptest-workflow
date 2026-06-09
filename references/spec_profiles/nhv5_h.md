# NHV5.1AP + H 规格与平台模型边界（H-extension + AIA profile）

本文是 `nhv5_h` 的项目 profile。写该 profile 下的 case、判断 official Spike/RTL 结果、决定 default/manual/compile-only/blocked 时，以本文作为项目专属规则入口。

具体 harness/API 用法看 `references/framework_usage_pitfalls.md`，编译运行看 `references/build_run_debug.md`。

```hyptest-profile
profile: nhv5_h
project_or_core: NHV5.1AP+H
default_privilege_scope: M/HS/U/VS/VU with H-extension and AIA (IMSIC + APLIC)
pmp_granularity: 4KB
official_spike_has_tlb_model: false
official_spike_has_cache_model: false
official_spike_has_pma_csr: false
linknan_difftest_ref_has_pma_csr: true
default_spike_gate: ordinary_h_extension_with_aia_arch_only
default_case_elf_dir: case_elf_asm
linknan_mmio_requires_responder: true
primary_aia_gate: LinkNan RTL regression
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

### 覆盖范围

按行为面分组（每条都是本 profile 内的有效验证目标）：

1. **翻译路径**：VS-stage / G-stage 单独和组合翻译；`hgatp.MODE` / `vsatp.MODE` 切换（`Bare` / `Sv39x4` / `Sv48x4`，Nanhu 未启用 Sv57x4）；两级 PTE A/D bit **由软件 set**（不支持 Svadu）的检查与 PF 触发；guest physical address (GPA) 宽度（比 SXLEN 多 2 bit）。
2. **H 专属指令**：`HLV.B/H/W/D/BU/HU/WU` / `HSV.B/H/W/D` / `HLVX.HU/WU`（以执行权限读）；涉及 `hstatus.HU` 在 U 态下使用 HLV 指令的访问门禁。
3. **fence**：`hfence.gvma`（可选 GVMID / GPA 操作数）、`hfence.vvma`（VS-stage，带 VMID 隔离）、与 `sfence.vma` 在不同特权下的语义差异。
4. **trap 委托与路由**：`medeleg` / `mideleg` 把异常/中断委托到 HS；`hedeleg` / `hideleg` 把 HS 收到的进一步委托到 VS；trap 进入 V 模式时 `hstatus.SPV` / `hstatus.SPVP` / `mstatus.MPV` / `mstatus.GVA` 设置；**虚拟指令异常**（cause 22）；guest-page-fault 异常码（20 / 21 / 23）；`mtval2` / `htval` / `htinst` / `mtinst` 写入。
5. **模式切换 + CSR 影子**：`MRET` / `SRET` 从 V 上下文返回的语义；`vsstatus` ↔ `sstatus` / `vsie` ↔ `sie` / `vsip` ↔ `sip` / `vstvec` ↔ `stvec` / `vsepc` ↔ `sepc` / `vscause` ↔ `scause` / `vstval` ↔ `stval` / `vsscratch` ↔ `sscratch` / `vsatp` ↔ `satp` 在 V=0 / V=1 下的投影规则；计数器虚拟化（`hcounteren` / `scounteren` 交互）；WFI 在 VS 下的 `hstatus.VTW` 行为。
6. **VS 中断侧**：`vstip` / `vssip` / `vseip`（传统三大 V 中断）；`hvip` 注入路径；`hgeip` / `hgeie`（guest external interrupt 的传统侧，不含 IMSIC）；**Sstc**：`vstimecmp` / `stimecmp`（本 profile 在范围内）；`htimedelta` 时间偏移读取（VS 看到的 `time` 寄存器值）。
7. **AMO / LR-SC 在 2-stage 下**：reservation 在 G-stage 翻译失败时的行为；AMO 触发 G-stage 写权限缺失时异常归属（guest store/AMO page-fault, cause 23 vs guest load page-fault, cause 21）。
8. **PBMT 与 H 翻译交互**（`Svpbmt` 在范围内）：`vsatp` / `hgatp` 翻出的 PTE PBMT 字段如何决定最终内存属性；两级翻译 PBMT 冲突时的优先级。

涉及的 H 相关 CSR 全集：`hstatus` / `hgatp` / `hedeleg` / `hideleg` / `hcounteren` / `htval` / `htinst` / `hgeip` / `hgeie` / `hvip` / `htimedelta` / `vsstatus` / `vsie` / `vsip` / `vstvec` / `vsscratch` / `vsepc` / `vscause` / `vstval` / `vsatp` / `vstimecmp`。

### 默认 ISA / 特权 / 扩展假设

- 当前默认开启 H 扩展（与 `nhv5_1_ap` 的 no-H 默认相反）；HS helper 走真实 H 语义而非 S 别名。
- Nanhu 实际实现的扩展全集（RV64IMAFDCBHV + Zicbom / Zicboz / Sstc / Svpbmt / Smaia / Ssaia / Smstateen / Sscofpmf / Sdtrig 等）继承自 Nanhu RTL，本 profile 不重复罗列；只在跟 H + AIA 路径有交互时显式提到。
- **不支持 Svadu**（硬件 A/D 写回，`menvcfg.ADUE = RO=0`）：A/D 由软件 set；G-stage / VS-stage 任一缺失即 PF（详见 §6.1）。
- 默认 G-stage / VS-stage MODE：`Bare` / `Sv39x4` / `Sv48x4`（Nanhu 未启用 Sv57，相关 case 不构造）。
- ASID 16 bit，VMID 14 bit。
- Sdtrig 在本 profile 沿用 `nhv5_1_ap` 的 Nanhu 裁剪：仅 2 层 chain、仅 address / execute-PC trigger、无 data trigger；超出部分测试点本身不应设计。
- 当前 NHV5.1AP / LinkNan simv 不支持运行时动态更新 `misa` 扩展位（与 H 无关的平台级约束，沿用 `nhv5_1_ap`）；写 `misa` 后不要假设 `C` 等扩展位可以被临时清除/打开并立即改变执行语义。依赖动态清 `misa.C` 将当前核从 IALIGN=16 切到 IALIGN=32 的 case 不进入默认 selfcheck/default gate；若要测 JAL/JALR/branch 半字对齐目标 IAM，必须使用已确认支持 IALIGN=32 的构建配置，或把当前配置下的失败归为平台约束/用例假设不成立。

### 范围外项目（碰到归 `compile-only` 或转其它 profile）

- **Svadu** / 硬件 A/D 写回路径 → Nanhu 未实现，相关 case 直接 blocked / 不写
- **Svnapot**（连续 napot 翻译）→ 不在 H 路径里测，相关 case 标 `D-MANUAL-NONGATE` 或 `compile-only`
- **Sv57 / Sv57x4** → Nanhu 未启用，相关 case 不构造
- NMI、double trap → 同 `nhv5_1_ap`，不进 default gate
- 自定义 / 私有 H 相关 CSR（若有）→ 按 official Spike model gap 处理，是否在范围由 test_point 决定
- WFI 真实等待路径 → 同 `nhv5_1_ap`，只测语义不测实际等待

注：AIA 在本 profile 范围内（IMSIC / APLIC 都覆盖），与 `nhv5_2_AIA` 重叠由项目设计接受，不合并；如果某 case 重心在 AIA-only 路径而非 H-extension 交互，按测试点意图选择更合适的 profile。

### HS helper 语义

仓库中 `enter_hs_mode()` / `enter_vs_mode()` 等 helper 在本 profile 下**就是 H 扩展真实语义**（不再是 `nhv5_1_ap` 那种"S 别名"）；`hgatp` / `vsatp` 写入是真实 G-stage / VS-stage 翻译。

### AIA 在本 profile 下的处理

AIA（IMSIC + APLIC）在本 profile 范围内；CSR 架构面（`mtopi` / `stopi` / `vstopi` 候选选择、`mvien` / `mvip` 过滤、`hvictl` / `hviprio1` / `hviprio2` 字段语义、IMSIC 间接访问、`mtopei` / `stopei` / `vstopei` claim）和平台路径（IMSIC 内存映射 MSI、APLIC routing / 委派、IOMMU + MRIF）的 gate 边界详见 §5。与 `nhv5_2_AIA` 在 AIA 维度上的覆盖重叠属于项目设计；如果某 case 不涉及 H-extension 交互而是纯 AIA 路径，按测试点意图选择更合适的 profile。

## 3. PMP 粒度约定

- 当前项目默认按 4KB page 粒度构造 PMP 相关 case。
- 不默认依赖 sub-4KB PMP 隔离精度；除非用户明确要求且平台/源码证据支持。
- PMP 边界类测试优先使用 4KB page boundary、page offset、跨页/页内权限组合来表达。
- 不要写出"只有 4KB 内小区域被隔离、同页其它区域仍可访问"的隐含假设。
- **H 扩展专属**：PMP 检查发生在 G-stage 翻译之后（对最终 host PA 做检查），不是 VS-stage 之后。PMP-related case 应当：
  1. PMP 区间用最终 PA（host PA），不要用 GVA / GPA 直接构造 PMP entry
  2. 当 G-stage 翻译可能失败时，期望异常应优先期望 guest-page-fault，不要同时构造 PMP fault（优先级见 §6）

## 4. PMA / PBMT / MMIO / cacheability

必须区分：

- `PMA=IO`：物理地址区域语义。
- `PBMT=IO`：PTE 属性语义。
- `PBMT=NC`：页表属性指定 non-cacheable 语义，不等价于 PMA IO。

硬规则：

- case 注释和测试点回填必须写清 Device/NC 属性来源。
- PMA/PBMT 与物理地址区间组合只能使用下表中标为"允许"的组合；未标允许的组合不要构造为有效正向测试。
- 不要为了让 Spike 通过，把 PMA/PBMT/IO 目标搬到普通 DRAM/cacheable 区域。
- PMA/PBMT/MMIO/cacheability 相关场景默认先判为 `spike_gate_applicable=false`，除非有明确证据说明该场景只依赖 Spike 可建模的普通架构行为。
- legal PMA/peripheral PA 不等于 testbench 有响应路径；没有 responder 时应标 `blocked` / `manual`，不要伪造 pass。
- MMIO/Device 访问除了满足下表允许组合外，还必须确认当前 LinkNan testbench 对目标 PA 有模拟 IO responder；部分允许区间当前没有模拟 IO 返回路径，访问会无响应并导致卡死。
- UART/IntrGen 这类 register-like responder 不能替代 memory-like MMIO scratch；若 case 需要 byte/half/word lane merge、整行 readback 或任意地址可读写，必须确认 responder 语义足够。
- 当前 PMA `Atomic` 位不作为 AMO/LR/SC 是否允许的直接生效判据；本项目实现中实际生效的是 cacheability：PMA cache 位开启代表 atomic 能力开启，PMA cache 位关闭代表 atomic 能力关闭。只清 PMA `Atomic` 位但保持 cache 位开启，不应期望 AMO/LR/SC 立即变成访问异常；`amo_access_fault_21` 这类仅切换 `Atomic` 位的失败应按用例期望错误处理。
- `MENVCFG.CBIE=Flush` 时，当前实现会把 `CBO.INVAL` 走成 flush 语义而不是普通"只失效不回写"的清线语义；具体是否触发该特殊路径还取决于当前特权级和 `CBIE` 生效层级。写 `cbo_inval` 相关 selfcheck 时，不能默认它一定只是清掉 cacheline，更不能默认它会把另一个 alias 的 NC 写入立即传播成 cacheable/backing 视图的一致值。
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
  },
  {
    "id": "linknan_aplic_mmio",
    "window": "0x38050000-0x38057fff",
    "pma": "IO",
    "pbmt": "None",
    "memattr_device": true,
    "allowed": true,
    "responder_required": true,
    "responder_status": "confirmed",
    "spike_gate_applicable": false,
    "default_decision": "manual_linknan_rtl_gate_candidate"
  },
  {
    "id": "linknan_intr_gen_mmio",
    "window": "0x40070000-0x4007ffff",
    "pma": "IO",
    "pbmt": "None",
    "memattr_device": true,
    "allowed": true,
    "responder_required": true,
    "responder_status": "confirmed",
    "spike_gate_applicable": false,
    "default_decision": "manual_linknan_rtl_gate_candidate"
  },
  {
    "id": "linknan_imsic_global_window",
    "window": "0xE000000000-0xE000010000",
    "pma": "IO",
    "pbmt": "None",
    "memattr_device": true,
    "allowed": true,
    "responder_required": true,
    "responder_status": "confirmed",
    "spike_gate_applicable": false,
    "default_decision": "manual_capability_gated_by_default"
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

LinkNan responder/source evidence（LinkNan testbench 共享，与 `nhv5_1_ap` 一致）：

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
  },
  {
    "id": "linknan_intr_gen",
    "target": "LinkNan AXI4IntrGenerator / INTR_GEN_ADDR 0x40070000",
    "responder_type": "register-like",
    "memory_like_scratch": false,
    "spike_gate_applicable": false,
    "default_decision": "manual_linknan_rtl_gate_candidate",
    "notes": "平台私有外设；QEMU/official Spike 无对应模型。"
  },
  {
    "id": "linknan_aplic",
    "target": "LinkNan APLIC 0x38050000 M-domain, 0x38054000 S-domain",
    "responder_type": "register-like",
    "memory_like_scratch": false,
    "spike_gate_applicable": false,
    "default_decision": "manual_linknan_rtl_gate_candidate",
    "notes": "当前设计仅 MSI delivery，source 0 保留。"
  },
  {
    "id": "linknan_imsic",
    "target": "LinkNan IMSIC global base 0xE000000000, M file offset 0x8000, S/VS offset 0x0",
    "responder_type": "testbench_dependent",
    "memory_like_scratch": false,
    "spike_gate_applicable": false,
    "default_decision": "manual_capability_gated_by_default",
    "notes": "RTL 已集成，hyptest LinkNan 平台头记录 LINKNAN_IMSIC_M_BASE_ADDR=0xE000008000、LINKNAN_IMSIC_S_BASE_ADDR=0xE000000000；只有定义 LINKNAN_ENABLE_IMSIC_MMIO_TESTS 时才暴露 IMSIC_M_BASE_ADDR/S_BASE_ADDR。"
  },
  {
    "id": "qemu_virt_aia",
    "target": "QEMU virt,aia=aplic-imsic APLIC/IMSIC",
    "responder_type": "testbench_dependent",
    "memory_like_scratch": false,
    "spike_gate_applicable": false,
    "default_decision": "manual_optional_reference",
    "notes": "可用于通用 AIA 行为观察，但不是 LinkNan gate。"
  }
]
```

新增或修改 MMIO case 前必须写清：

- 目标 PA window。
- Device/NC 来源是 PMA 还是 PBMT。
- 当前 testbench 是否存在 responder。
- responder 是否支持本 case 需要的读写宽度、lane merge、readback 或整行可见性。

### H 扩展补充

- **检查点**：所有 PMA / PBMT / MMIO / cacheability 检查发生在最终 host PA（HPA）上，即 GVA → GPA（VS-stage）→ HPA（G-stage）翻译完成之后。`vsatp.MODE=Bare` 时 GVA 直接是 GPA；`hgatp.MODE=Bare` 时 GPA 直接是 HPA。
- **两级 PBMT 合成（spec 18.5.1）**：当 VS-stage PBMT 与 G-stage PBMT 都非 `None` 时，**G-stage PBMT 优先**。case 写作时若两级 PBMT 都设非 `None`，期望按 G-stage 字段判最终内存属性；若 VS-stage 单独设 PBMT、G-stage 是 `None`，则按 VS-stage 字段。
- **HLVX**：`HLVX.HU/WU` 以执行权限读，PMA / PBMT 检查仍按最终 host PA 的属性，不会因为是"以执行权限"就变成 cacheable。
- **HLV / HSV 异常归属**：HLV/HSV 跨页失败时，第二半页的 PMA / PBMT 检查独立判断，guest-page-fault 与 access-fault 优先级见 §6。

### LinkNan AIA 平台事实

LinkNan 集成下的 AIA 硬件参数来自 `LinkNan/src/main/scala/linknan/soc/LinkNanParams.scala`、`devicetree/Predefined.scala` 与 hyptest `platform/linknan/inc/platform.h`。本子节作为本 profile 下 AIA 平台路径 case 的硬地址参考；与 `nhv5_2_AIA` profile 的事实表重叠，但保留以避免 H × AIA case 跨 profile 查阅。

| 项 | 当前值 |
| --- | --- |
| 外部中断输入 | `nrExtIntr = 256`，`ext_intr` 宽度 256 |
| 有效 APLIC source | `1..255`，source 0 保留 |
| APLIC base | `0x3805_0000` |
| APLIC M/S domain size | `0x4000`，总 window `0x3805_0000..0x3805_7fff` |
| APLIC delivery | 当前设计只支持 MSI delivery，`domaincfg.DM` 固定为 1 |
| APLIC EIID width | `log2Ceil(nrExtIntr) + 1 = 9` |
| APLIC guest files | `geilen = 1` |
| IMSIC global base | `finalImsicBase = 0xE0_0000_0000` |
| IMSIC S/VS global base | `finalSgBase = 0xE0_0000_0000` |
| IMSIC M global base | `finalMBase = 0xE0_0000_8000` |
| IMSIC local S/VS base | `0x0000` |
| IMSIC local M base | `0x8000` |
| IMSIC hart stride | `0x1_0000` |
| IMSIC EIID count | `512` |
| hyptest guest hint | `IMSIC_S_GUEST_COUNT = 1U` |
| LinkNan intr_gen | `0x4007_0000..0x4007_ffff` |

intr_gen 编号规则：

```text
raise_ext_intr(1) -> ext_intr(0) -> APLIC source 0, reserved
raise_ext_intr(source + 1) -> ext_intr(source) -> APLIC source N
```

因此有效 APLIC 外部线 case 必须使用 `raise_ext_intr(source + 1)`，且 source 从 1 开始。

`IMSIC_M_BASE_ADDR` / `IMSIC_S_BASE_ADDR` 默认**不**作为 hyptest 平台头公开宏；需要泛化 IMSIC MMIO case 时显式定义 `LINKNAN_ENABLE_IMSIC_MMIO_TESTS` 才暴露这两个宏作为 hyptest 可执行能力。LinkNan 专用 `intr_gen → APLIC → IMSIC → core trap` 闭环探针（如 P6I/P6J/P6K 类）可直接使用 `LINKNAN_IMSIC_M_BASE_ADDR` / `LINKNAN_IMSIC_S_BASE_ADDR` 硬件地址作为 LinkNan RTL-only / manual 闭环 oracle，不依赖该 capability flag。

## 5. Official Spike 模型边界

**继承 `nhv5_1_ap` §5 全部 gap**（无 TLB 模型、无 cache 模型、无 PMA CSR、CBO 内部 line 状态不建模、replay queue / sbuffer / uncache buffer / MSHR / ROB head / response-context 不建模、PMA / PBMT / MMIO routing 不建模、LR/SC reservation timeout / alias DCache hit 不建模、custom CSR / instruction / NMI / double trap 不在范围、运行时动态更新 misa / IALIGN=32 动态切换不支持、Debug trigger chain 闭合 AMO BP 不建模、Nanhu Debug trigger 实现约束 chain ≤2 层 + 仅 address/execute-PC trigger + 无 data trigger），下面只补 H + AIA 的增量。

前提：official Spike 必须在编译时启用 H、Smaia、Ssaia、Sstc、Svpbmt；任一开关缺失时不构成 model gap，按 `D-BLOCK-COMPILE` 或 `D-BLOCK-EVIDENCE` 处理（参见 §9）。
本 profile 中 `official_spike_has_pma_csr=false` 只约束 official/community
Spike gate；当前 LinkNan difftest reference (`HYPTEST_DIFFTEST_REF_SO`) 支持
PMA CSR/行为对齐，PMA mismatch 仍按 LinkNan REF-DUT first-divergence 分析。

### 5.1 H 架构面（可作 default Spike gate 候选）

满足"目标 PA 在普通 cacheable DRAM、不依赖 TLB / cache / 平台 responder"前提时，下列语义可作为 default gate 候选：

- `medeleg` / `mideleg` / `hedeleg` / `hideleg` 委托语义；trap 进入 V 模式时 `mstatus.MPV` / `mstatus.GVA` / `hstatus.SPV` / `hstatus.SPVP` / `hstatus.GVA` 设置（priv §22.6.2 表 52 / 53 / 54）。
- cause 20 / 21 / 22 / 23 触发分类、基础 `mtval` / `mtval2` / `htval` 写入；priv §22.6.1 cause 22 触发条件首条（`hstatus.VTVM=1` + V=1 时对 `satp` / `sfence.vma` 的访问完整列表 [需 case 时严谨复读]）。
- VS 级 CSR 投影：`vsstatus` ↔ `sstatus` / `vsie` ↔ `sie` / `vsip` ↔ `sip` / `vstvec` ↔ `stvec` / `vsepc` ↔ `sepc` / `vscause` ↔ `scause` / `vstval` ↔ `stval` / `vsscratch` ↔ `sscratch` / `vsatp` ↔ `satp` 在 V=0 / V=1 下的读写规则。
- `MRET` / `SRET` 从 V 上下文返回（priv §22.6.4）。
- `HLV.B/H/W/D/BU/HU/WU` / `HSV.B/H/W/D` / `HLVX.HU/WU` 的 ISA decode 与最终 HPA 在普通 DRAM 范围内的访问；`hstatus.HU` 在 U 态对 HLV/HSV 的门禁。
- Sv39x4 / Sv48x4 两级 walk + PTE A/D 位检查（Nanhu 未启用 Sv57x4；不支持 Svadu，A=0 / 写时 D=0 → PF；详见 §6.1）；`hgatp.MODE` / `vsatp.MODE` 切换 + `Bare` 退化。
- `hcounteren` / `scounteren` 计数器虚拟化交互。
- Sstc：`vstimecmp` / `stimecmp` 触发 `vstip`、`htimedelta` 偏移影响 V=1 下读 `time`。

### 5.2 H 部分可 gate / 部分不可 gate

| 语义 | 可 gate 子集 | 不 gate 子集 |
| --- | --- | --- |
| `HFENCE.GVMA` / `HFENCE.VVMA` | 指令编码、特权与 `hstatus.VTVM` 控制下的非法 / 虚指令异常 | stale translation 清除效果（继承 nhv5_1_ap §5 无 TLB） |
| `mtinst` / `htinst` transformation（priv §22.6.3 表 55 / 56 / 57） | 标准 transform 路径（load / store / AMO / HLV / HLVX / HSV 的 Addr.Offset 替代 rs1） | 伪指令值 `0x00002000` / `0x00002020` / `0x00003000` / `0x00003020`（VS-stage implicit access）首次 case 必须 sanity check；custom value 路径不 gate |
| VS / G-stage PTE PBMT 字段读取与两级合成（spec 18.5.1，G-stage 优先） | 字段优先级架构面 | 最终内存属性效果（继承 §4） |
| `HLVX.HU/WU` 取指权限读 | 权限检查与异常分类 | 最终 host PA 的 PBMT / PMA 内存属性 |
| AMO 在 G-stage 写权限缺失时的 cause 21 vs cause 23 分类 | 异常分类架构面 | 触发顺序与平台流水线相关，不可 gate |

### 5.3 H 增量明确不 gate（继承 §4 / §5 / 平台 gap）

- `HLV` / `HSV` 跨页第二半页落入 Device PA 时的异常分类（依赖 host 端 PMA / PBMT routing）。
- Page-walk implicit access 落到 Device PA / MMIO 时的行为。
- PMP after G-stage 在 sub-4KB 边界 / 跨页场景（沿用 §3 4KB 粒度约定）。
- LR / SC 在 G-stage 翻译失败、reservation 重试与同 PA 不同 VA alias 组合（叠加 nhv5_1_ap §5.1）。

### 5.4 AIA 在本 profile 下的 gate 边界

| 语义 | 默认 `spike_gate_applicable` | 说明 |
| --- | --- | --- |
| Smaia / Ssaia CSR 架构面：`mtopi` / `stopi` / `vstopi` 候选选择规则、`mvien` / `mvip` 过滤（AIA spec 表 11，bits 12:0 中只有 1 / 9 可写）、`hvictl` 字段、`hviprio1` / `hviprio2` 仅 IID 1 / 5 / 13 / 14–23 可配置、`mvien` 仅对 IID 1 / 9 / 13–63 可写 | true 候选 | 写 case 前在 Spike 上单点 sanity check；候选规则 5 种互斥配对 `[需 case 时严谨复读]` |
| IMSIC CSR 间接访问：`eidelivery`（0 / 1 / 0x40000000）/ `eithreshold` / `eip` / `eie` via `*iselect` / `*ireg`；`vsireg` / `sireg` 在 V=1 下的 virtual instruction 触发条件 | true 候选 | 触发条件 `[需 case 时严谨复读]` |
| `mtopei` / `stopei` / `vstopei` claim（写 = 完成）；`vstopei` 经 `hstatus.VGEIN` 选 guest IF 路径 | true 候选 | VGEIN 越界返回值 `[需 case 时严谨复读]` |
| `hgeip` / `hgeie` 字段语义（与 IMSIC guest IF 解耦的纯 CSR 行为） | true 候选 | guest IF 实际 set bit 路径不 gate |
| WFI 在 AIA 下"任意特权 `*topi != 0` 即唤醒"重定义 | 沿用 nhv5_1_ap：测语义不测真实等待 | — |
| IMSIC 内存映射 MSI 路径（`seteipnum_le` / `seteipnum_be`） | false | 平台 MSI 路径，依赖 testbench responder；走 RTL-only / LinkNan |
| APLIC：`domaincfg` / `sourcecfg`（Inactive / Detached / Edge0/1 / Level0/1）/ `target`（direct vs MSI）/ IDC 结构（`idelivery` / `iforce` / `ithreshold` / `topi` / `claimi`）/ MSI forwarding 公式 / 域委派 | false | 平台组件，level mode deassert 跟踪 RTL-only |
| `hstatus.VGEIN` 选 guest IF + `hgeip` set bit 实际驱动路径 | false | 平台 + IMSIC guest IF 强耦合 |
| IOMMU + MSI 转换（address mask / pattern、`extract` 公式）+ MSI 页表（基本转换 M=3、MRIF 模式 M=1）+ MRIF 结构 / 通知 MSI / 虚拟 hart 迁移 4 步 / 6 步 | false | Spike 无 IOMMU 模型；全部 RTL-only / LinkNan |

LinkNan AIA capability gate 补充：

- 泛化 IMSIC M-file / S-file MMIO case（依赖 `IMSIC_M_BASE_ADDR` / `IMSIC_S_BASE_ADDR`）默认保持 **capability-gated / manual**；只有显式定义 `LINKNAN_ENABLE_IMSIC_MMIO_TESTS` 且 LinkNan difftest 参考模型对 IMSIC 间接 CSR/MMIO 状态完成对齐后，才作为 LinkNan RTL gate candidate 收紧。
- LinkNan 专用 `intr_gen → APLIC → IMSIC → core trap/claim` 闭环探针（如 M / HS / VS 三档 guest file 验证）可直接使用 `LINKNAN_IMSIC_M_BASE_ADDR` / `LINKNAN_IMSIC_S_BASE_ADDR` 硬件地址，保持 manual / RTL-only。当前若该类闭环出现 APLIC pending / enable / target 已成立但 IMSIC `topei` / `pending` 为 0、对应 MEIP / SEIP / VSEIP 未进入的现象，应聚焦 APLIC MSI output → outbound / remap → IMSIC write front-end / `msiio` → IMSIC file pending 链路定位，按 LinkNan RTL bug 候选处理，不直接归 official Spike model gap。
- `mstateen0.IMSIC` 与 IMSIC 访问门禁相关 case 在 LinkNan difftest Spike 上若出现 REF 报 illegal 但 DUT 未陷入的差异，属于独立的 difftest 对齐问题，不与 IMSIC MSI 投递链路问题混为同一根因；先交 `hyptest-failure-triage` 保留 `linknan-difftest` 证据并定位 REF-DUT first-divergence，再按 `D-MANUAL-SPIKE-GAP`（需写清 runner 为 `HYPTEST_DIFFTEST_REF_SO`）或 `D-MANUAL-RTL-ONLY` 分别归因。

### 5.5 H + AIA 不可 gate keyword 速查

继承 nhv5_1_ap §5 全部 keyword 块（脚本 `query_spec_profile.py --nongate-summary` 不做跨 profile 合并，因此本 profile 把 nhv5_1_ap 的相关 keyword 也内嵌一份），附加本 profile 增量：

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
    "note": "PMA CSR not implemented in official/community Spike (`HYPTEST_SPIKE_BIN`); this does not describe LinkNan difftest reference (`HYPTEST_DIFFTEST_REF_SO`)."
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
    "category": "Debug trigger Nanhu implementation limits",
    "keywords": ["chain_depth_limit", "data_trigger", "more_than_two_triggers"],
    "module_hints": ["trigger", "atomicsunit"],
    "classification": "nanhu_not_impl",
    "note": "Nanhu only supports 2-level chain, address-trigger and execute-PC trigger; data trigger NOT implemented. Case designs targeting 3+ level chain or data trigger are out of scope. Reason code: D-MANUAL-NANHU-NOT-IMPL."
  },
  {
    "category": "H two-stage routing on platform",
    "keywords": ["g_stage_routing", "two_stage_routing", "hlv_cross_page_device", "hsv_cross_page_device", "page_walk_to_device"],
    "module_hints": ["mmu", "ptw", "memblock", "dcache"],
    "note": "Two-stage final-PA routing depends on platform PMA/PBMT/MMIO; same as nhv5_1_ap §4."
  },
  {
    "category": "H fence effective drain",
    "keywords": ["hfence_gvma_effect", "hfence_vvma_effect", "stale_g_stage_translation", "stale_vs_stage_translation"],
    "module_hints": ["mmu", "tlb", "ptw"],
    "note": "Encoding/exception side gateable; actual TLB drain not gateable (no TLB model)."
  },
  {
    "category": "H mtinst/htinst pseudo encodings",
    "keywords": ["mtinst_pseudo", "htinst_pseudo", "vs_stage_implicit_access_inst", "0x2000", "0x2020", "0x3000", "0x3020"],
    "module_hints": ["csr", "trap", "ptw"],
    "note": "Standard transform gateable; pseudo-instruction encodings require Spike sanity check before first use."
  },
  {
    "category": "H two-stage PBMT composition effect",
    "keywords": ["two_stage_pbmt", "g_stage_pbmt_priority", "vs_stage_pbmt_effective"],
    "module_hints": ["pbmt", "mmu", "memblock"],
    "note": "Field priority gateable; final memory attribute effect not gateable."
  },
  {
    "category": "AIA platform MSI / APLIC routing",
    "keywords": ["seteipnum_le", "seteipnum_be", "aplic_routing", "aplic_sourcecfg_level", "aplic_target_msi", "aplic_domain_delegate", "idc_claimi", "idc_topi"],
    "module_hints": ["imsic", "aplic", "msi", "memblock"],
    "note": "Platform components; route to RTL-only/LinkNan."
  },
  {
    "category": "AIA guest interrupt file path",
    "keywords": ["vgein_guest_if", "hgeip_set_path", "guest_if_msi"],
    "module_hints": ["imsic", "guest_if"],
    "note": "VGEIN selection field gateable; actual guest-IF MSI delivery not gateable."
  },
  {
    "category": "AIA IOMMU + MRIF",
    "keywords": ["iommu_msi_translate", "msi_pte_basic", "msi_pte_mrif", "mrif_storage", "mrif_notice_msi", "iommu_address_mask"],
    "module_hints": ["iommu", "mrif"],
    "note": "Spike has no IOMMU model; all RTL-only."
  }
]
```

### 5.6 Spike 结果使用口径（H + AIA 增量）

- 普通 cacheable DRAM 上、纯 ISA 可见的 H + AIA CSR 架构面 case，可以用 Spike 做 default gate（前提 Spike 启用 H / Smaia / Ssaia / Sstc / Svpbmt）。
- Spike fail 时先排查：(a) Spike 本身是否启用对应扩展；(b) 是否落在 §5.2 / §5.3 / §5.4 的不 gate 区间；(c) 是否落在 nhv5_1_ap §5 已有 gap。
- Spike pass 不证明：两级 PBMT 的实际内存属性、APLIC level mode 跟踪、IMSIC 平台 MSI 路径、IOMMU 转换、HFENCE 真实 TLB drain、PMP after G-stage 跨页隔离。
- AIA 不一致优先怀疑 Spike IMSIC / APLIC 配置（hart 数、IID 数、`A + h*2^C` 排布、IOMMU 是否启用），不要立刻判 RTL bug。

## 6. 非对齐与异常优先级

继承 `nhv5_1_ap` §6 全部口径（first encountered fault、Device 区域非对齐 AF、`PBMT=NC` 标量非对齐 AM、cacheable 非对齐不抛异常、向量 / 原子非对齐 AF、跨页 / 跨 16B split tval 取错误地址、整条 store 不部分写入），下面只补 H + AIA 增量。

### 6.1 H 增量

- 翻译阶段优先级：VS-stage fault（cause 12 / 13 / 15 instruction / load / store-or-AMO page-fault）先于 G-stage fault；VS-stage 通过后 G-stage 失败按 cause 20 / 21 / 23 分类。
- **A/D 位（不支持 Svadu，软件管理）**：取指 / load / AMO read 阶段命中 PTE A=0 → 对应 PF（cause 12 / 13 / 15 或 G-stage 时 cause 20 / 21 / 23）；store / AMO write 阶段命中 PTE D=0 → store/AMO PF（cause 15 或 G-stage 时 cause 23）。**load 不检查 D**；G-stage 与 VS-stage 各自独立检查 A/D，任一缺失即 PF。case 写作时 prepare 段必须**显式 set A/D**（除非测试点意图就是测 A/D 缺失 → PF）；不能假设硬件会自动 set。
- `mtval` / `htval` 写入：cause 20 / 21 / 22 / 23 时 `htval` 写入 GPA[63:2]；cause 22（virtual instruction）时 `mtval` / `stval` 取触发指令编码或 0（按 priv §22.6.1）。
- `mtinst` / `htinst` 写入：按 priv §22.6.3 表 55 / 56 / 57，cause 20 / 21 / 23 由 VS-stage implicit access 触发时使用伪指令值 `0x00002000` / `0x00002020` / `0x00003000` / `0x00003020`；其它情形按标准 transform 或 0；自定义实现可写 0 而非具体值，**写 case 时不要断言 `htinst` 必然为某具体非零值**，除非测试点明确要求严格 transform 且 sanity check 已确认。
- HLV / HSV 跨页：低半页正常、高半页 fault 时 `tval` 取 second-half 起始 GVA、`htval` 取对应 GPA；整条 HLV 不产生部分读，`HSV` 整条不产生部分写（继承 nhv5_1_ap §6 split fragment 规则）。
- AMO 在 G-stage 写权限缺失：同时存在读权限时优先报 cause 23（store/AMO guest-page-fault），不应同时构造 cause 21。
- 异常分类与 PMP after G-stage 优先级：当 G-stage 翻译失败可能与 PMP fault 同时构造时，优先期望 guest-page-fault（cause 20 / 21 / 23），不要同时设 PMP fault 期望（继承 §3）。
- cause 22（virtual instruction）触发条件首条 `hstatus.VTVM=1` + V=1 时对 `satp` / `sfence.vma` 等访问的完整触发列表 `[需 case 时严谨复读]`。

### 6.2 AIA 增量

- `hvictl.VTI=1` 时：VS 模式下访问 `sip` / `sie` 触发 cause 22；写入若可能把任一 `vsip[i]` 从 1→0（除 SEIP 外）也触发 cause 22。
- `vsireg` / `sireg` 在 V=1 下访问保留 / 高特权区间触发 cause 22；具体条件位段 `[需 case 时严谨复读]`。
- `mvien` 写入非可写 IID（bits 12:0 中除 1 / 9 之外、或非 1 / 9 / 13–63 范围）按硬件忽略；不应断言写后回读必然变化。
- IMSIC 间接访问 `*iselect` 落入保留区间时：M / S 触发 illegal instruction，VS 触发 virtual instruction（cause 22），具体保留区间 `[需 case 时严谨复读]`。

## 7. 分层默认口径

- `default`：编译稳定、运行稳定、规则一致，且 `spike_gate_applicable=true`。本 profile 下仅当场景落在 §5.1 / §5.2（gateable 子集）/ §5.4（true 候选行）时考虑作为 default。
- `manual`：规则已明确，但 Spike 不宜作为 gate，或运行结果可归因但不适合常规批跑（`D-MANUAL-NONGATE` / `D-MANUAL-RTL-ONLY` / `D-MANUAL-SPIKE-GAP` / `D-MANUAL-UNSTABLE`）。
- `compile-only`：只保留编译与场景表达，本轮不执行 Spike / LinkNan gate。
- `blocked`：规格 / 环境 / 证据不完整，或 testbench 缺少必要 responder，或 Spike 未启用 H / Smaia / Ssaia / Sstc / Svpbmt 等本 profile 必需扩展。

本 profile 下 `spike_gate_applicable` 判定原则：

1. 默认 false。
2. 只有当场景明确落在 §5.1（H 架构面）或 §5.4（AIA CSR 架构面 true 候选行）时才提为 true 候选。
3. 任一以下条件命中时强制 false：(a) 目标 PA 不在普通 cacheable DRAM；(b) 依赖 TLB / cache 一致性；(c) 依赖 PMA / PBMT / MMIO routing 实际效果；(d) 依赖 APLIC 委派 / IMSIC 平台 MSI / IOMMU；(e) 依赖 HFENCE 真实 TLB drain；(f) PMP sub-4KB 假设；(g) HLV / HSV 跨页第二半页落入 Device。

本 profile 常见 `manual` / `compile-only` 候选（H + AIA 增量，继承 nhv5_1_ap §7 其它项）：

- HFENCE.GVMA / HFENCE.VVMA 真实 TLB drain 效果。
- `mtinst` / `htinst` 伪指令值首次 case 验证（首次必须 manual + sanity check，sanity 后可视情况升 default）。
- 两级 PBMT 合成的实际内存属性效果。
- PMP after G-stage 跨页 / sub-4KB 边界。
- HLV / HSV 跨页第二半页落入 Device PA 的异常分类。
- AIA：APLIC 任何 routing / 委派、IMSIC 内存映射 MSI 路径、IOMMU + MSI 页表 + MRIF、`hstatus.VGEIN` + `hgeip` set bit 实际驱动路径。
- LR / SC 在 G-stage 翻译失败 / reservation 重试与同 PA 不同 VA alias 组合（继承 nhv5_1_ap §5.1）。

## 8. Spike 不一致时的 NHV5.1AP+H 处理流程

继承 `nhv5_1_ap` §8 5 步骤；本 profile 在 §8 步骤 2（"判断不一致是否落在 Spike 模型边界"）下增加排查项：

1. **扩展开关**：先确认 Spike 编译启用 H / Smaia / Ssaia / Sstc / Svpbmt；任一缺失 → `D-BLOCK-COMPILE` 或 `D-BLOCK-EVIDENCE`，不算模型 gap。
2. **AIA 配置**：检查 Spike IMSIC / APLIC 配置（hart 数、IID 数上限 ≤ 2047、`A + h*2^C` 排布参数、IOMMU 是否启用）；配置不一致 → 调整配置或归 `D-BLOCK-EVIDENCE`。
3. **H 模型边界**：按 §5.2 / §5.3 判定，命中即转 `manual` / `compile-only` / `blocked`。
4. **AIA 模型边界**：按 §5.4 判定，false 行命中即转 `D-MANUAL-RTL-ONLY` 或 `compile-only`。
5. **`mtinst` / `htinst` 伪指令值**：首次不一致不直接判 bug；先按 priv §22.6.3 表 56 / 57 sanity check 实现选择（标准 transform vs custom 0 vs 伪指令值）。

不要因为单次 Spike 结果反向改写 §5 的 gate 边界或 §6 的异常优先级口径。

## 9. 本 profile 常见 reason_code 映射

通用 reason_code 定义仍以 `references/reason_code_catalog.md` 为准。本文只补 NHV5.1AP+H 常见场景映射；继承 nhv5_1_ap §9 全部 H 无关映射。

H 增量：

- HFENCE.GVMA / HFENCE.VVMA 真实 TLB drain、stale VS / G-stage translation：`D-MANUAL-NONGATE`，走 RTL-only / LinkNan。
- 两级 PBMT 合成的实际内存属性（不仅是字段优先级）：`D-MANUAL-NONGATE`。
- PMP after G-stage 跨页 / sub-4KB 边界：`D-MANUAL-NONGATE`。
- HLV / HSV 跨页第二半页落入 Device PA 的异常分类：`D-MANUAL-NONGATE`，必要时 `blocked`（无 responder）。
- `mtinst` / `htinst` 伪指令值首次验证：首次 `D-MANUAL-NONGATE` + sanity check 记录；sanity 后可视情况升 `default`。
- Page-walk implicit access 落到 Device PA：`D-MANUAL-NONGATE` 或 `blocked`。

AIA 增量：

- IMSIC 内存映射 MSI 路径（`seteipnum_le` / `seteipnum_be`）：`D-MANUAL-RTL-ONLY`。
- APLIC routing / 委派 / level mode deassert / IDC `claimi`：`D-MANUAL-RTL-ONLY`。
- IOMMU + MSI 页表 + MRIF + 通知 MSI + 虚拟 hart 迁移：`D-MANUAL-RTL-ONLY`。
- `hstatus.VGEIN` + IMSIC guest IF 实际 MSI 投递：`D-MANUAL-RTL-ONLY`。
- AIA CSR 架构面 case 但 Spike 未启用 Smaia / Ssaia：`D-BLOCK-COMPILE` 或 `D-BLOCK-EVIDENCE`。
- AIA CSR 候选规则 / 触发条件 sanity check 通过但 Spike 与 spec 不一致（实测 spec gap）：`D-MANUAL-SPIKE-GAP`。

LinkNan AIA 平台增量：

- LinkNan `intr_gen` 注入 / APLIC source 路由 / APLIC → IMSIC MSI 投递链路 / IMSIC `topei` / guest-file HGEIP 等 RTL-only 闭环：`D-MANUAL-RTL-ONLY` 或 `D-MANUAL-NONGATE`。
- 依赖 `LINKNAN_ENABLE_IMSIC_MMIO_TESTS` 才暴露 `IMSIC_M_BASE_ADDR` / `IMSIC_S_BASE_ADDR` 的泛化 IMSIC MMIO case（capability-gated）：默认 `D-MANUAL-NONGATE`；capability flag + difftest 参考模型对齐后再收紧为 LinkNan RTL gate candidate。
- `mstateen0.IMSIC` 等 stateen 与 AIA CSR 交互的 LinkNan difftest 独立 mismatch（REF 报 illegal、DUT 未陷入）：先保留 `linknan-difftest` first-divergence 证据；若暂用 `D-MANUAL-SPIKE-GAP`，摘要必须写明这是 `HYPTEST_DIFFTEST_REF_SO` 对齐问题而非 official Spike gate gap，并与 MSI 投递链路问题分别归因。
- 注：当前 reason_code catalog **没有**专门的 `LINKNAN_RTL_GOLDEN` 类型；不要自造 reason_code。需要表达 LinkNan 证据时，在最终摘要和测试点短状态里写明 LinkNan RTL PASS / FAIL，分层 reason_code 仍按通用 catalog 选项（`D-MANUAL-RTL-ONLY` / `D-MANUAL-NONGATE` / `D-BLOCK-EVIDENCE`）选择。

环境与 Spike 配置：

- Spike 未启用 H 扩展导致 H 架构面 case 失败：`D-BLOCK-COMPILE` 或 `D-BLOCK-EVIDENCE`。
- LinkNan testbench 无 IMSIC / APLIC / IOMMU responder：`blocked` + `D-MANUAL-RTL-ONLY` 或 `D-COMPILE-ONLY-ENV`。
