# RTL Bug Pattern Examples

本文只收集当前项目中有代表性的 RTL 怀疑点示例，供写 `test_point` 的“怀疑点 / 对应场景”段时参考。它不是通用 case 编写规范，也不是规格真值；规格/profile 仍以 `references/spec_and_model_limits.md` 和 `references/spec_profiles/<spec_profile>.md` 为准。

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
