# NHV5.2 / LinkNan AIA 规格与平台模型边界

本文是 `/nfs/home/zhouzhirong/AIA-hypertest/riscv-hyp-tests-nhv5` 中 AIA/APLIC/IMSIC 用例的项目 profile。编写、修改、分层和判断 LinkNan AIA 自测 case 时，以本文作为项目专属规则入口。

具体 harness/API 用法看 `references/framework_usage_pitfalls.md`，编译运行看 `references/build_run_debug.md`。通用 workflow 仍然有效；本文只覆盖 NHV5.2 AIA 在 LinkNan 集成环境下的平台口径、模型边界和 gate 选择。

```hyptest-profile
profile: nhv5_2_AIA
project_or_core: LinkNan / Nanhu NHV5.2 AIA
default_privilege_scope: M/HS/VS with AIA/APLIC/IMSIC
pmp_granularity: 4KB
official_spike_has_tlb_model: false
official_spike_has_cache_model: false
official_spike_has_pma_csr: false
linknan_difftest_ref_has_pma_csr: true
default_spike_gate: ordinary_non_AIA_arch_only
default_case_elf_dir: case_elf_asm/linknan
linknan_mmio_requires_responder: true
primary_aia_gate: LinkNan RTL regression
```

## 1. 口径优先级

语义/规格冲突时按以下顺序裁决：

1. 当前 LinkNan AIA 设计文档：`/nfs/home/zhouzhirong/AIA-hypertest/DOCS/AIA Integration Manual.md`、`APLIC Module Design Document(DS).md`、`IMSIC Module Design Document(DS).md`。
2. 当前 LinkNan/Nanhu 源码参数与 RTL 行为。
3. 本 profile。
4. memory `events.jsonl` 中 `status=confirmed` 的已确认历史。
5. `references/spec_and_model_limits.md`。
6. `test_point/CRITICAL_ISSUES_LOG.md`，仅作历史线索。

流程、输出、分层格式仍按以下通用文档执行，但不得覆盖本文的 AIA gate 规则：

- `references/quality_gate.md`
- `references/tiering_decision.md`
- `references/reason_code_catalog.md`
- `references/submission_card.md`
- `references/writing_cases.md`
- `references/build_run_debug.md`

最重要的项目约定：

- AIA/APLIC/IMSIC case 默认不使用 official/community Spike 作为 golden。
- LinkNan AIA 自测的主 gate 是 LinkNan RTL/difftest 回归。
- LinkNan 仓库内定制 Spike 是 difftest 对齐模型，不等同于 official Spike AIA golden；CPU_NANHU 的 ISA string、stateen、hviprio、hgeie/GEILEN 等行为需要与 RTL 保持同步。
- 当前 LinkNan difftest reference (`HYPTEST_DIFFTEST_REF_SO`) 支持 PMA CSR/行为对齐；
  `official_spike_has_pma_csr=false` 只说明 official/community Spike gate 不适合
  PMA CSR/routing，不说明 LinkNan difftest REF 缺少 PMA。
- QEMU `virt,aia=aplic-imsic` 只作为可选参考模型，适合观察一部分通用 AIA 行为，不替代 LinkNan 平台专属路径。
- LinkNan `intr_gen -> APLIC -> IMSIC -> trap handler` 的完整外部线闭环只能由 LinkNan/RTL 环境确认。

## 2. 项目范围

- 本 profile 覆盖 NHV5.2 AIA 相关测试点，包括 APLIC、IMSIC、AIA CSR、M/HS/VS interrupt routing、APLIC MSI delivery、IMSIC interrupt file、guest file capability、handler 注册路径和 LinkNan 平台映射。
- 普通非 AIA 架构 case 不因为使用本 profile 自动变成 LinkNan-only；若 case 完全不涉及 AIA/MMIO/平台中断控制器，仍可按普通 Spike gate 口径判断。
- AIA 用例默认目标仓库为 `/nfs/home/zhouzhirong/AIA-hypertest/riscv-hyp-tests-nhv5`。
- AIA 用例建议放在 `ai_test_cases/AIA/`，注册统一放 `test_register.c`，可按 workflow 以 commented/manual 形式生成独立 ELF。
- 当前 LinkNan 平台头默认暴露 APLIC 和 `intr_gen`，并记录 IMSIC global MSI window 的硬件地址；`IMSIC_M_BASE_ADDR/S_BASE_ADDR` 需要显式定义 `LINKNAN_ENABLE_IMSIC_MMIO_TESTS` 后才作为泛化 IMSIC MMIO case 的 hyptest 可执行能力暴露。依赖 IMSIC MMIO aperture 的 M-file/S-file 用例默认保持 capability-gated/manual，用于避免当前 LinkNan difftest Spike 对 IMSIC 间接 CSR/MMIO 状态尚未完全对齐时污染默认 gate。P6I/P6J/P6K 可直接使用 `LINKNAN_IMSIC_M_BASE_ADDR/S_BASE_ADDR` 作为 LinkNan RTL-only/manual 闭环探针。APLIC direct delivery、多 hart routing、真实 WFI 异步唤醒、完整 guest-file HGEIP 聚合仍需 capability-gated 或 manual 判读。
- 当前 QEMU 常用参考命令口径为 `qemu-system-riscv64 -machine virt,aia=aplic-imsic,aclint=on -cpu rv64,v=true,h=true -smp 1 -m 256M -nographic -monitor none -serial mon:stdio -bios none -kernel <elf>`。
- 单 hart QEMU 配置不能完整覆盖 LinkNan `intr_gen`、LinkNan IMSIC remap、多 hart MSI routing、真实异步 WFI 唤醒和当前 Nanhu/Spike difftest 特性。

## 3. PMP 粒度约定与 LinkNan AIA 平台事实

PMP 构造粒度沿用当前 profile metadata 的 `pmp_granularity: 4KB`。AIA profile 的核心目标是 APLIC/IMSIC/AIA CSR/MMIO/interrupt routing；普通 PMP 边界 corner 不在本文新增专属口径内，除非测试点明确要求与 AIA MMIO window 组合。

当前 LinkNan 参数来自 `LinkNan/src/main/scala/linknan/soc/LinkNanParams.scala`、`devicetree/Predefined.scala` 和 hyptest `platform/linknan/inc/platform.h`。

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

`intr_gen` 编号规则：

```text
raise_ext_intr(1) -> ext_intr(0) -> APLIC source 0, reserved
raise_ext_intr(source + 1) -> ext_intr(source) -> APLIC source N
```

因此有效 APLIC 外部线用例必须使用 `raise_ext_intr(source + 1)`，并从 source 1 开始。

## 4. PMA / PBMT / MMIO / cacheability

AIA 的核心观测对象是 MMIO/CSR/interrupt side effect，不是普通 cacheable DRAM。写 case 时必须区分：

- APLIC MMIO：`domaincfg/sourcecfg/target/setip/setie/genmsi` 等寄存器行为。
- IMSIC MMIO：MSI 写入 aperture，例如 `seteipnum_le`。
- AIA CSR：`miselect/mireg/mtopei`、`siselect/sireg/stopei`、`vsiselect/vsireg/vstopei`、`hgeip/hgeie`、`hvien/hvip/hvictl` 等。
- LinkNan `intr_gen`：平台私有外部线注入器，不等于 RISC-V 标准 AIA 组件。

硬规则：

- APLIC/IMSIC MMIO case 的 `spike_gate_applicable=false`。
- AIA MMIO case 不得为了让 Spike 通过改写成 DRAM scratch。
- QEMU AIA 结果只能作为通用行为参考；LinkNan 地址、remap、`intr_gen` 和 difftest 对齐以 LinkNan RTL 为准。
- 当前 LinkNan hyptest 平台记录 IMSIC M/S global window 地址，但默认不定义 `IMSIC_M_BASE_ADDR/S_BASE_ADDR`；泛化 M/S-file IMSIC MMIO case 只有在显式打开 `LINKNAN_ENABLE_IMSIC_MMIO_TESTS` 并同步 difftest 参考模型后，才适合作为 LinkNan RTL gate candidate。P6I/P6J/P6K 这类 LinkNan 专用闭环探针可使用 `LINKNAN_IMSIC_*` 硬件地址并保持 manual/RTL-only。guest-file HGEIP、多 hart、WFI 等仍要按平台能力单独判读。

机器可读组合表：

```hyptest-pma-pbmt-matrix
[
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
  },
  {
    "id": "qemu_virt_aplic_mmio",
    "window": "0x0c000000-0x0d000000",
    "pma": "IO",
    "pbmt": "None",
    "memattr_device": true,
    "allowed": true,
    "responder_required": true,
    "responder_status": "confirmed",
    "spike_gate_applicable": false,
    "default_decision": "manual_optional_reference_not_linknan_gate"
  },
  {
    "id": "qemu_virt_imsic_m_s_mmio",
    "window": "0x24000000-0x2c000000",
    "pma": "IO",
    "pbmt": "None",
    "memattr_device": true,
    "allowed": true,
    "responder_required": true,
    "responder_status": "confirmed",
    "spike_gate_applicable": false,
    "default_decision": "manual_optional_reference_not_linknan_gate"
  },
  {
    "id": "ordinary_dram_arch",
    "window": "0x80000000-0x90000000",
    "pma": "MEM",
    "pbmt": "None",
    "memattr_device": false,
    "allowed": true,
    "responder_required": false,
    "responder_status": "dram_memory",
    "spike_gate_applicable": true,
    "default_decision": "default_candidate_if_no_AIA_or_other_model_limit"
  }
]
```

MMIO responder 表：

```hyptest-mmio-responder-matrix
[
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

## 5. Official Spike 模型边界（Spike / QEMU / LinkNan Gate 边界）

official/community Spike：

- 普通非 AIA、非平台 MMIO、非 cache/TLB/PMA/PBMT 的架构行为仍可作为 Spike gate 候选。
- AIA/APLIC/IMSIC、AIA MMIO、AIA CSR side effect、external interrupt controller routing、guest file、APLIC MSI delivery 均默认 `spike_gate_applicable=false`。
- Spike pass 不能证明 AIA case default；Spike fail 也不能直接证明 DUT bug。

LinkNan difftest Spike：

- 这是 LinkNan RTL 回归中的对齐模型，不是独立 golden。
- CPU_NANHU 需要带 `_smaia` 等 ISA 能力。
- CPU_NANHU 的 `mstateen0/hstateen0`、CSRIND/AIA/IMSIC、`hviprio1` mask、`hgeie`/GEILEN 等需要和 Nanhu RTL 对齐。
- 在显式打开 `LINKNAN_ENABLE_IMSIC_MMIO_TESTS` 后，若 `mireg/sireg/mtopei/stopei` 等访问在 REF 侧报 illegal 或状态与 DUT 不一致，应优先同步 LinkNan Spike/difftest 的 IMSIC CSR/MMIO 模型。
- 若 RTL 与 difftest Spike 在 AIA CSR 上不一致，先按 LinkNan/Nanhu 当前实现和设计文档定位，不按 official Spike 直接下结论。

QEMU：

- QEMU `virt,aia=aplic-imsic` 可作为通用 AIA 基础行为参考。
- QEMU 不覆盖 LinkNan `intr_gen`、LinkNan IMSIC remap、Nanhu NewCSR 微结构、LinkNan difftest Spike 对齐问题。
- QEMU guest file/SMP/WFI 行为依赖命令行配置；未配置时相关 case 必须 capability-gated。

机器可读 nongate 关键词：

```hyptest-nongate-keywords
[
  {
    "category": "AIA_APLIC_IMSIC_spike_nongate",
    "classification": "spike_model_gap",
    "keywords": ["AIA", "APLIC", "IMSIC", "mtopei", "stopei", "vstopei", "miselect", "mireg", "siselect", "sireg", "hgeip", "hgeie", "hvien", "hvip", "hvictl"],
    "module_hints": ["AIA", "APLIC", "IMSIC", "interrupt"],
    "qemu_gate_applicable": "reference_only",
    "linknan_rtl_gate_applicable": true,
    "note": "AIA 基础功能以 LinkNan RTL 回归为主 gate，QEMU 只作参考。"
  },
  {
    "category": "LinkNan_intr_gen_platform_specific",
    "classification": "platform_or_rtl_only",
    "keywords": ["intr_gen", "AXI4IntrGenerator", "INTR_GEN_ADDR", "ext_intr"],
    "module_hints": ["AIA", "interrupt", "LinkNan"],
    "qemu_gate_applicable": false,
    "linknan_rtl_gate_applicable": true,
    "note": "LinkNan intr_gen 是平台私有外设。"
  },
  {
    "category": "AIA_guest_file_or_multihart_capability",
    "classification": "platform_config_dependent",
    "keywords": ["guest file", "VGEIN", "HGEIP", "HGEIE", "multihart", "SMP", "MSI routing", "WFI wakeup"],
    "module_hints": ["AIA", "IMSIC", "hypervisor"],
    "qemu_gate_applicable": "depends_on_qemu_args",
    "linknan_rtl_gate_applicable": "depends_on_platform_header_and_testbench",
    "note": "需要匹配 guest-file/SMP/testbench 能力；默认写成 capability-gated/manual。"
  }
]
```

## 6. 非对齐与异常优先级

AIA profile 不新增通用非对齐优先级口径；普通 scalar/vector/atomic misaligned、PF/AF/tval 优先级仍按当前通用 profile 与 `references/spec_and_model_limits.md`。若访问目标是 APLIC/IMSIC/intr_gen MMIO，则必须优先按本文 §4 的 responder、Device/MMIO、平台能力和 LinkNan difftest/RTL oracle 判读，不得用 ordinary DRAM 非对齐结果替代。

## 7. 分层默认口径（用例写法和分层默认口径）

- `default`：非 AIA 普通架构 case，且 Spike gate 适用并通过；或 AIA case 已经在 LinkNan RTL 回归中稳定通过，且不依赖未暴露平台能力。
- `manual`：AIA case 当前阶段默认落点。包括 Spike 不适用但 LinkNan/QEMU 可观测的 AIA 基础功能、平台配置依赖能力、LinkNan/RTL 复核项。
- `compile-only`：case 只验证代码路径/平台宏存在，当前 QEMU/LinkNan 都不能可靠运行。
- `blocked`：缺少平台地址定义、responder、必要 helper、RTL 构建或有效 oracle。

本 profile 的 `spike_gate_applicable` 判定原则：

- case 触及 APLIC/IMSIC/AIA CSR side effect/external interrupt controller routing，则 `spike_gate_applicable=false`。
- case 只触及普通 ISA/privilege 架构行为且无其它模型边界，则可为 `spike_gate_applicable=true`。
- AIA case 即使 QEMU PASS，也不要在 Spike-first workflow 中因为 Spike 不适用而误判为 `blocked`；应写成 manual/LinkNan RTL evidence 或 QEMU reference evidence。

## 8. LinkNan 当前 65 例口径

历史 56 个 AIA case 已在 LinkNan 回归中跑通。该基线结果：

```text
log: /nfs/home/zhouzhirong/AIA-hypertest/LinkNan/regress_logs/linknan_batch_result_20260521_195940.log
summary: pass=56 fail=0 timeout=0
total_cases: 56
```

新增 LinkNan M/HS/VS 闭环探针后，当前 65 个 AIA ELF 的最近一次全量回归结果：

```text
log: /nfs/home/zhouzhirong/AIA-hypertest/LinkNan/regress_logs/linknan_batch_result_20260523_005953.log
summary: pass=61 fail=4 timeout=0 missing_elf=0
total_cases: 65
```

这些 case 的解释边界：

- APLIC CFG、source mode、pending/enable、delegation、`intr_gen -> APLIC pending` 是当前 LinkNan 平台上的实测覆盖。
- APLIC direct delivery case 只能证明当前平台按“不支持 direct delivery”路径 capability skip，不能当作 direct delivery 已实现证据。
- 泛化 IMSIC MMIO、APLIC->IMSIC->M-handler、CPU direct MSI to IMSIC case 默认保持 capability/manual；显式打开 `LINKNAN_ENABLE_IMSIC_MMIO_TESTS` 并完成 difftest 参考模型对齐后，才收紧为 LinkNan RTL gate candidate。它们仍不适合用 official Spike 当 golden。
- P6I/P6J/P6K 是 LinkNan 专用 `intr_gen -> APLIC -> IMSIC -> core trap/claim` 闭环探针，分别覆盖 M、HS/S、VS guest file。当前三条均 selfcheck fail：APLIC pending/enable/target 已成立，但 IMSIC `topei/pending` 为 0，对应 MEIP/SEIP/VSEIP 未进入。当前分诊为 suspected RTL bug，聚焦 APLIC MSI output -> outbound/remap -> IMSIC write front-end/`msiio` -> IMSIC file pending 链路。
- `IMSIC_S_GUEST_COUNT=1U` 表示 LinkNan 规格有 guest file；CSR/WARL/stateen/redirection smoke 不能声称 HGEIP 完整闭环已 gate。P6K 是当前 guest-file 闭环 gate 探针，但在 RTL 修复前保持 FAIL evidence。
- `aia_p5b_aia_vs_csr_redirection_capability` 需要 `mstateen0/hstateen0` 打开 IMSIC，并设置 `hstatus.VGEIN=1`，这是 LinkNan `geilen=1` 下的有效 CSR redirection smoke。
- `aia_p4g_aia_stateen_access_control` 当前为独立 difftest mismatch：LinkNan difftest Spike 在 `mstateen0.IMSIC=0` 时对 HS `stopei` 访问报 illegal，DUT 没有同步陷入。该问题不应和 P6I/P6J/P6K 的 MSI 投递链路问题混为一个根因。

## 9. Spike 不一致时

当 Spike 结果和 AIA 预期不一致：

1. 先确认 case 是否属于 AIA/APLIC/IMSIC/MMIO/外部中断控制器范围。
2. 若是 official/community Spike，直接按本文 §5 判为模型边界，不把 Spike fail 当 DUT bug。
3. 若是 LinkNan difftest Spike，检查 CPU_NANHU ISA string、stateen mask、hviprio mask、hgeie/GEILEN、IMSIC CSR 访问权限是否和 RTL/设计文档一致。
4. 对通用 AIA 行为可以改跑 QEMU `virt,aia=aplic-imsic` 作参考，但最终仍以 LinkNan RTL 回归和设计文档为准。
5. 若 LinkNan RTL FAIL，先检查平台宏、case oracle、helper cleanup、`intr_gen` 编号和是否误把 capability skip 当强 oracle。

## 10. 常见 reason_code 映射

- AIA/APLIC/IMSIC 在 official Spike 下不可 gate：`D-MANUAL-NONGATE`。
- QEMU 未配置 guest file、SMP、真实 WFI wakeup 等能力：`D-MANUAL-NONGATE`，并在 case/test_point 文本中注明配置依赖。
- LinkNan `intr_gen` 或 RTL-only 外部线闭环：`D-MANUAL-RTL-ONLY` 或 `D-MANUAL-NONGATE`，按当前 reason_code catalog 可用项选择。
- 缺少平台宏、helper、RTL responder 或日志证据导致无法运行：优先 `D-BLOCK-EVIDENCE`，补齐环境后再降为 manual/default。
- 当前 reason_code catalog 没有专门的 `LINKNAN_RTL_GOLDEN` 类型；不要自造 reason_code。需要表达 LinkNan 证据时，在最终摘要和测试点短状态里写明 LinkNan RTL PASS。
