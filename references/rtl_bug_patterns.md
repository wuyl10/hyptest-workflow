# RTL Bug Pattern Examples

本文只是**历史示例集**，不是权威清单，也不是找 bug 时的第一入口：

- bug hunt 主线是按 `SKILL.md` 的 `Bug Hunt Evidence` 段读 profile §5 + target_module 的 RTL 源码 + 现有 test_point 覆盖情况。
- 本文里的路径和场景属于某个时间点的快照，可能已经被 RTL 重构、文件重命名或 bug 修过；不要把这里的路径当成通用规则。
- 规格/profile 仍以 `references/spec_and_model_limits.md` 和 `references/spec_profiles/<spec_profile>.md` 为准。

## 扫 RTL 源码时常见的 anti-pattern

读 target_module 的 RTL 时，优先留意以下几类结构——命中其中一类通常就是值得写 test_point 的怀疑点候选：

- `WireDefault(false.B)` 或其它默认值后，条件分支不完整（某些 case 未显式赋值）
- `Valid` 输出但无对应 `ready` 握手；或 `ready/valid` 配对但 retire/cancel 路径不对称
- `Reg(Vec)` 之类资源池被多路共用，但缺乏显式 retire/dealloc 或清零路径
- 粘性 CSR（`trigger` / `pmp` / `mstatus` / `mcause` 等）在异常/特权态切换路径上未清
- 特权态（U/HS/M/VS）切换或 trap entry 时，模块内部状态未统一重置
- 跨页 / 跨 16B 等 split 路径有"快速完成"分支，但 fault / refault / replay 分支复用同一模板寄存器

引用前先 `ls` / `grep` 确认该 `<file>.scala:<line>` 在当前 RTL 中仍然存在、语义未变；若已重构以当前源码为准。

## 示例 1：Store Misalign / Fake-Crosspage Template Reuse

怀疑点示例：

- `src/main/scala/xiangshan/mem/lsqueue/StoreQueue.scala:807-820` 把 same-page scalar cross-16B store 固定送进 fake-crosspage 路径，可能导致模板退场不干净。
- `src/main/scala/xiangshan/mem/lsqueue/StoreMisalignBuffer.scala:257-258` 可能让 retry 结束后的 owner/template 状态被下一条 width-switch store 继续复用。

可构造场景示例：

- `sd(1B+7B)` repeated `SAF` -> repair -> upper-half aligned `sd(8B)` success x4 -> refault `SAF` -> repair -> retried `sd(1B+7B)` success -> immediate `sw(1B+3B)` success
- 最终要求 `sw` trap-free，只覆盖 bytes7-10，不破坏其余 boundary image。
