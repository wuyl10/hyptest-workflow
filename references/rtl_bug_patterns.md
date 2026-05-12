# RTL Bug Pattern Examples

本文只是**历史示例集**，不是权威清单，也不是找 bug 时的第一入口：

- 真 bug 邻域以 `scripts/query_rtl_bug_history.py` 从 LinkNan/Nanhu git log 查出的 fix commit 为准（bug hunt 场景 skill 会自动调用，见 `SKILL.md` 的 `Bug Hunt Evidence` 段）。
- 本文里的路径和场景属于某个时间点的快照，可能已经被 RTL 重构、文件重命名或 bug 修过；不要把这里的路径当成通用规则。
- 规格/profile 仍以 `references/spec_and_model_limits.md` 和 `references/spec_profiles/<spec_profile>.md` 为准。

当写 `test_point` 的"怀疑点 / 对应场景"段需要一个可参考结构时，可以看下面的示例；有条件时优先用 `query_rtl_bug_history.py` 拿**实时** commit hash + file:line，而不是引用本文里的固定路径。

## Store Misalign / Fake-Crosspage Template Reuse

怀疑点示例：

- `src/main/scala/xiangshan/mem/lsqueue/StoreQueue.scala:807-820` 把 same-page scalar cross-16B store 固定送进 fake-crosspage 路径，可能导致模板退场不干净。
- `src/main/scala/xiangshan/mem/lsqueue/StoreMisalignBuffer.scala:257-258` 可能让 retry 结束后的 owner/template 状态被下一条 width-switch store 继续复用。

可构造场景示例：

- `sd(1B+7B)` repeated `SAF` -> repair -> upper-half aligned `sd(8B)` success x4 -> refault `SAF` -> repair -> retried `sd(1B+7B)` success -> immediate `sw(1B+3B)` success
- 最终要求 `sw` trap-free，只覆盖 bytes7-10，不破坏其余 boundary image。

使用提醒：

- 只在任务明确需要从 RTL/源码定位可疑点时引用这类路径。
- 不要把这里的具体路径当成所有 profile 的通用事实。
- 若当前 profile 不是 LinkNan/NHV5.1AP，先确认源码路径和实现结构仍成立。
- 引用前先跑 `query_rtl_bug_history.py` 确认对应文件是否已有后续 commit 改动；若已重构，以实时 commit 为准。
