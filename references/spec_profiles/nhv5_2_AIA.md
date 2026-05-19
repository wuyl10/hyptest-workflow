# NHV5.2 AIA 规格与平台模型边界

本文是 NHV5.2 AIA/APLIC/IMSIC 用例的项目 profile。写 `/nfs/home/wuyuanlong/workspace/riscv-hyp-tests-nhv5.2` 中 AIA 相关 case、判断 QEMU/Spike/LinkNan 结果、决定 default/manual/compile-only/blocked 时，以本文作为项目专属规则入口。

具体 harness/API 用法看 `references/framework_usage_pitfalls.md`，编译运行看 `references/build_run_debug.md`。通用 workflow 仍然有效；本文只覆盖 NHV5.2 AIA 的平台口径和 gate 选择。

```hyptest-profile
profile: nhv5_2_AIA
project_or_core: NHV5.2 AIA
default_privilege_scope: M/HS/VS with AIA/APLIC/IMSIC
pmp_granularity: 4KB
official_spike_has_tlb_model: false
official_spike_has_cache_model: false
official_spike_has_pma_csr: false
default_spike_gate: ordinary_non_AIA_arch_only
default_case_elf_dir: case_elf_asm
linknan_mmio_requires_responder: true
```

## 1. 口径优先级

语义/规格冲突时按以下顺序裁决：

1. 本文（NHV5.2 AIA 项目真值）。
2. memory `events.jsonl` 中 `status=confirmed` 的已确认历史。
3. `references/spec_and_model_limits.md`。
4. `test_point/CRITICAL_ISSUES_LOG.md`（历史问题库，主要用于线索，不直接覆盖当前门禁）。

流程、输出、分层格式仍按以下通用文档执行，但不得覆盖本文的 AIA gate 规则：

- `references/quality_gate.md`
- `references/tiering_decision.md`
- `references/reason_code_catalog.md`
- `references/submission_card.md`
- `references/writing_cases.md`
- `references/build_run_debug.md`

最重要的项目约定：

- AIA/APLIC/IMSIC case 默认不使用 official Spike 作为 golden。
- 当前可自动运行的 AIA golden 是 QEMU `virt,aia=aplic-imsic`。
- LinkNan `intr_gen -> APLIC -> IMSIC -> trap handler` 的完整外部线闭环最终仍需要 LinkNan/RTL 环境复核。

## 2. 项目范围

- 本 profile 覆盖 NHV5.2 AIA 相关测试点，包括 APLIC、IMSIC、AIA CSR、M/HS/VS interrupt routing、APLIC direct delivery、APLIC MSI delivery、IMSIC interrupt file、guest file capability、handler 注册路径和 QEMU/LinkNan 平台映射。
- 普通非 AIA 架构 case 不因为使用本 profile 自动变成 QEMU-golden；若 case 完全不涉及 AIA/MMIO/平台中断控制器，仍可按普通 Spike gate 口径判断。
- AIA 用例默认目标仓库为 `/nfs/home/wuyuanlong/workspace/riscv-hyp-tests-nhv5.2`。
- AIA 用例建议放在 `ai_test_cases/AIA/`，注册统一放 `test_register.c`。
- 当前 QEMU 常用命令口径为 `qemu-system-riscv64 -machine virt,aia=aplic-imsic,aclint=on -cpu rv64,v=true,h=true -smp 1 -m 256M -nographic -monitor none -serial mon:stdio -bios none -kernel <elf>`。
- 当前单 hart QEMU 配置不能完整覆盖 SMP MSI routing、多个 guest interrupt file、真实异步 WFI 唤醒和 LinkNan 私有 `intr_gen` 外部线行为；这些场景可以写 case，但结论要写成 capability/manual 或 LinkNan/RTL 复核。

## 3. PMP 粒度约定

- 当前 AIA case 不以 PMP 粒度作为主要测试目标。
- 若 AIA case 需要页表/PMP 辅助进入 S/VS 或保护 MMIO 区间，默认沿用 4KB page 粒度。
- 不要把 PMP 边界语义和 AIA interrupt routing 语义混在同一个 case 里作为单一 oracle。
- APLIC/IMSIC MMIO 区间访问应以平台 header 中的 base/size 宏为准，不硬编码到普通 DRAM。

## 4. PMA / PBMT / MMIO / cacheability

AIA 的核心观测对象是 MMIO/CSR/interrupt side effect，不是普通 cacheable DRAM。写 case 时必须区分：

- APLIC MMIO：domaincfg/sourcecfg/target/setip/setie/genmsi/IDC 等寄存器行为。
- IMSIC MMIO：MSI 写入 aperture，例如 `seteipnum_le` 行为。
- AIA CSR：`miselect/mireg/mtopei`、`siselect/sireg/stopei`、`vsiselect/vsireg/vstopei`、`hgeip/hgeie`、`hvien/hvip/hvictl` 等。
- LinkNan `intr_gen`：平台私有外部线注入器，不等于 RISC-V 标准 AIA 组件。

硬规则：

- APLIC/IMSIC MMIO case 的 `spike_gate_applicable=false`。
- AIA MMIO case 在 QEMU `virt,aia=aplic-imsic` 下可作为当前基础 golden；但 QEMU 未配置的 guest file/SMP/平台私有外设只能作为 capability/manual。
- LinkNan `intr_gen` 相关 case 在 QEMU 下只能做编译或平台条件检查；完整行为必须 LinkNan/RTL 复核。
- 不要为了让 Spike 通过，把 APLIC/IMSIC MMIO 改写成 DRAM scratch。

机器可读组合表：

```hyptest-pma-pbmt-matrix
[
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
    "default_decision": "default_candidate_with_qemu_aia_gate"
  },
  {
    "id": "qemu_virt_imsic_m_mmio",
    "window": "0x24000000-0x28000000",
    "pma": "IO",
    "pbmt": "None",
    "memattr_device": true,
    "allowed": true,
    "responder_required": true,
    "responder_status": "confirmed",
    "spike_gate_applicable": false,
    "default_decision": "default_candidate_with_qemu_aia_gate"
  },
  {
    "id": "qemu_virt_imsic_s_mmio",
    "window": "0x28000000-0x2c000000",
    "pma": "IO",
    "pbmt": "None",
    "memattr_device": true,
    "allowed": true,
    "responder_required": true,
    "responder_status": "confirmed",
    "spike_gate_applicable": false,
    "default_decision": "default_candidate_with_qemu_aia_gate"
  },
  {
    "id": "linknan_aplic_mmio",
    "window": "0x38050000-0x38054000",
    "pma": "IO",
    "pbmt": "None",
    "memattr_device": true,
    "allowed": true,
    "responder_required": true,
    "responder_status": "must_confirm",
    "spike_gate_applicable": false,
    "default_decision": "manual_until_linknan_or_rtl_gate"
  },
  {
    "id": "linknan_intr_gen_mmio",
    "window": "0x40070000-0x40071000",
    "pma": "IO",
    "pbmt": "None",
    "memattr_device": true,
    "allowed": true,
    "responder_required": true,
    "responder_status": "must_confirm",
    "spike_gate_applicable": false,
    "default_decision": "manual_until_linknan_or_rtl_gate"
  },
  {
    "id": "ordinary_dram_arch",
    "window": "0x80000000-0x2000000000",
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
    "id": "qemu_virt_aplic",
    "target": "QEMU virt APLIC base 0x0c000000, aia=aplic-imsic",
    "responder_type": "register-like",
    "memory_like_scratch": false,
    "spike_gate_applicable": false,
    "default_decision": "default_candidate_with_qemu_aia_gate",
    "notes": "QEMU APLIC 可以作为 APLIC 基础寄存器、pending、direct/MSI delivery 的当前 golden。"
  },
  {
    "id": "qemu_virt_imsic",
    "target": "QEMU virt IMSIC M/S files base 0x24000000/0x28000000",
    "responder_type": "register-like",
    "memory_like_scratch": false,
    "spike_gate_applicable": false,
    "default_decision": "default_candidate_with_qemu_aia_gate",
    "notes": "QEMU IMSIC 可以作为 M/S interrupt file、topei、eie/eip、delivery/threshold 的当前 golden。"
  },
  {
    "id": "qemu_virt_imsic_guest_file",
    "target": "QEMU virt IMSIC guest files",
    "responder_type": "testbench_dependent",
    "memory_like_scratch": false,
    "spike_gate_applicable": false,
    "default_decision": "manual_until_qemu_guest_files_configured",
    "notes": "需要 QEMU machine 参数显式提供 guest files；未配置时只能做 capability-gated 检查。"
  },
  {
    "id": "linknan_intr_gen",
    "target": "LinkNan AXI4IntrGenerator / INTR_GEN_ADDR 0x40070000",
    "responder_type": "register-like",
    "memory_like_scratch": false,
    "spike_gate_applicable": false,
    "default_decision": "manual_until_linknan_or_rtl_gate",
    "notes": "QEMU 没有 LinkNan intr_gen；完整外部线触发必须在 LinkNan/RTL 环境复核。"
  }
]
```

## 5. Official Spike 模型边界

official/community Spike 在本 profile 下的口径：

- 普通非 AIA、非平台 MMIO、非 cache/TLB/PMA/PBMT 的架构行为仍可作为 Spike gate 候选。
- AIA/APLIC/IMSIC、AIA MMIO、AIA CSR side effect、external interrupt controller routing、guest file、APLIC direct delivery、APLIC MSI delivery 均默认 `spike_gate_applicable=false`。
- Spike 不作为 AIA golden；Spike pass 不能证明 AIA case default，Spike fail 也不能证明 DUT bug。
- 对 AIA case，优先使用 QEMU `virt,aia=aplic-imsic` 编译运行作为当前 golden。若 workflow 工具暂不支持 `--platform qemu`，允许手动调用仓库的 `compile_elf.py --plat qemu` 和 `get_result.py --platform qemu`。
- LinkNan/RTL 专属行为，例如 `intr_gen` 外部线、平台地址映射、RTL interrupt timing、真实 WFI 唤醒，QEMU 结果只能作为参考，不替代 LinkNan/RTL 复核。

机器可读 nongate 关键词：

```hyptest-nongate-keywords
[
  {
    "category": "AIA_APLIC_IMSIC_spike_nongate",
    "classification": "spike_model_gap",
    "keywords": ["AIA", "APLIC", "IMSIC", "mtopei", "stopei", "vstopei", "miselect", "mireg", "siselect", "sireg", "hgeip", "hgeie", "hvien", "hvip", "hvictl"],
    "module_hints": ["AIA", "APLIC", "IMSIC", "interrupt"],
    "qemu_gate_applicable": true,
    "note": "AIA 基础功能以 QEMU virt,aia=aplic-imsic 作为当前 golden，不以 official Spike 为 gate。"
  },
  {
    "category": "LinkNan_intr_gen_platform_specific",
    "classification": "platform_or_rtl_only",
    "keywords": ["intr_gen", "AXI4IntrGenerator", "INTR_GEN_ADDR", "ext_intr"],
    "module_hints": ["AIA", "interrupt", "LinkNan"],
    "qemu_gate_applicable": false,
    "note": "LinkNan intr_gen 是平台私有外设，QEMU 只能做编译或条件检查，完整闭环需要 LinkNan/RTL。"
  },
  {
    "category": "AIA_guest_file_or_multihart_capability",
    "classification": "qemu_config_dependent",
    "keywords": ["guest file", "VGEIN", "HGEIP", "HGEIE", "multihart", "SMP", "MSI routing", "WFI wakeup"],
    "module_hints": ["AIA", "IMSIC", "hypervisor"],
    "qemu_gate_applicable": false,
    "note": "需要匹配 QEMU guest-file/SMP 参数或 LinkNan/RTL 环境；默认写成 capability-gated/manual。"
  }
]
```

## 6. 非对齐与异常优先级

- 本 profile 不改变普通 RISC-V 非对齐、PF/AF/illegal instruction、virtual instruction 等异常优先级口径。
- AIA CSR 访问权限负测试必须先 `TEST_SETUP_EXCEPT()`，再检查 `excpt.triggered/cause/tval`。
- 若 QEMU 对某个 AIA CSR 返回 illegal instruction，先判断是否为 QEMU CPU/machine 参数未启用或模型缺失；不要直接推断为 DUT bug。
- APLIC/IMSIC MMIO 访问异常、卡死或无响应，优先按平台 responder/gate 配置问题处理。
- AIA interrupt trap case 中，普通异常仍走 hyptest 原有 `excpt` 记录；注册过的 interrupt cause 可通过 `m_trap_handler_register()` 进入专用 handler。

## 7. 分层默认口径

- `default`：非 AIA 普通架构 case，且 Spike gate 适用并通过；或未来 workflow 明确支持 QEMU-golden 后，AIA case 在 QEMU AIA gate 中稳定通过并且不依赖 LinkNan/RTL-only 行为。
- `manual`：AIA case 当前阶段默认落点。包括 Spike 不适用但 QEMU 可观测的 AIA 基础功能、QEMU 配置依赖能力、LinkNan/RTL 复核项。
- `compile-only`：case 只验证代码路径/平台宏存在，当前 QEMU/LinkNan 都不能可靠运行。
- `blocked`：缺少 QEMU AIA binary、缺少平台地址定义、缺少 responder、缺少必要 helper 或无法构造有效 oracle。

本 profile 的 `spike_gate_applicable` 判定原则：

- case 触及 APLIC/IMSIC/AIA CSR side effect/external interrupt controller routing，则 `spike_gate_applicable=false`。
- case 只触及普通 ISA/privilege 架构行为且无其它模型边界，则可为 `spike_gate_applicable=true`。
- AIA case 即使 QEMU PASS，也不要在旧 Spike-first workflow 中因为 Spike 不适用而误判为 `blocked`；应写成 manual/QEMU-golden evidence。

## 8. Spike 不一致时

当 Spike 结果和 AIA 预期不一致：

1. 先确认 case 是否属于 AIA/APLIC/IMSIC/MMIO/外部中断控制器范围。
2. 若是，直接按本文 §5 判为 Spike 模型边界，不把 Spike fail 当 DUT bug。
3. 对 AIA case 改跑 QEMU `virt,aia=aplic-imsic`，或记录为 QEMU/LinkNan/RTL 复核项。
4. 若 QEMU PASS，当前可作为 AIA 基础行为证据，但在 workflow 未支持 QEMU 一等 gate 前，注册状态仍可保持 commented/manual。
5. 若 QEMU fail，先检查 QEMU 版本、machine 参数、ELF 平台、case oracle 和 helper，再考虑是否是 QEMU 模型限制或真实设计问题。

## 9. 本 profile 常见 reason_code 映射

- AIA/APLIC/IMSIC 在 official Spike 下不可 gate：`D-MANUAL-NONGATE`。
- QEMU 未配置 guest file、SMP、真实 WFI wakeup 等能力：`D-MANUAL-NONGATE`，并在 case/test_point 文本中注明 QEMU 配置依赖。
- LinkNan `intr_gen` 或 RTL-only 外部线闭环：`D-MANUAL-RTL-ONLY` 或 `D-MANUAL-NONGATE`，按当前 reason_code catalog 可用项选择。
- 缺少 QEMU binary、平台宏、helper 或 responder 导致无法运行：优先 `D-BLOCK-EVIDENCE`，补齐环境后再降为 manual/default。
- 当前 reason_code catalog 没有专门的 `QEMU_GOLDEN` 类型；不要自造 reason_code。需要表达 QEMU 证据时，在最终摘要和测试点短状态里写明 QEMU PASS 作为 AIA 当前 golden。
