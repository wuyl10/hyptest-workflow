# HYPTEST 框架与工具坑点

本文只放 harness/API、注册、编译运行工具相关规则，不作为规格真值。规格语义、PMP/PMA/PBMT/Spike 模型边界先看 `references/spec_and_model_limits.md` 和 `references/spec_profiles/<spec_profile>.md`。

## 1. 框架 API 常见误用

### 1.1 `TEST_SETUP_EXCEPT()`

错误用法：

- 在不检查 `excpt.*` 的路径机械性到处加 `TEST_SETUP_EXCEPT()`。
- 把 `TEST_SETUP_EXCEPT()` 当成“隐藏异常”或“让异常不发生”的手段。

正确用法：

- 只要本步骤要断言 `excpt.triggered/cause/tval`，无论预期 `true` 还是 `false`，都先调用 `TEST_SETUP_EXCEPT()` 初始化异常状态。
- 如果该步骤不读取 `excpt.*`，不必强行调用。
- `reset_state()` 不等价于异常状态初始化；检查 `excpt.*` 前仍应显式调用 `TEST_SETUP_EXCEPT()`。

### 1.2 `TEST_END(...)`

- 一个 case 函数只能保留一个 `TEST_END(...)`。
- 多个 `TEST_END(...)` 会触发重复标签/重复收尾等问题。
- 若中途失败需要提前退出，直接 `return false;`，不要再写第二个 `TEST_END(...)`。

### 1.3 `reset_state()`

- `reset_state()` 主要用于 CSR/状态重置。
- 它不是“自动清除一切异常痕迹”的通用工具。
- fault/recovery 多段 case 中，每段检查 `excpt.*` 前仍要重新 `TEST_SETUP_EXCEPT()`。

## 2. 注册与执行管理

- 注册统一放在 `test_register.c`。
- 不在 case 源文件末尾注册。
- 新 case 是否进入 default 要单独评审，不自动放行。
- `test_register.c` 的视觉顺序不应被当成唯一真值；实际执行顺序以日志与最小复现实验为准。
- 调试顺序问题时，先最小化到 1~3 个相关 case，再看真实打印/执行顺序。

## 3. 文件放置与编译收集

当前 Makefile 会自动收集：

- `ai_test_cases/*.c`
- `manual_test_cases/**/*.c`
- `manual_test_cases/**/*.S`

放置规则：

- AI/批量生成 case 默认放 `ai_test_cases/*.c`。
- 人工维护 case 按模块放 `manual_test_cases/<module>/`。
- 新 case 文件后缀应为 `.c`，汇编 helper 后缀为 `.S`。
- 新建文件后仍需做单 case 编译确认它被编译系统收集。

## 4. 大文件不要继续硬塞

- 若现有目标文件已经明显过长，或用户明确指出不应继续追加，应优先新建主题明确的 case 文件。
- 历史大文件后续新增不默认继续堆叠。
- 新文件拆分目标是降低 merge conflict、方便检索和审阅。

## 5. 编译运行脚本坑点

### 5.1 `compile_elf.py`

- 关键编译步骤建议串行执行。
- 历史经验：并发改写/恢复 `test_register.c` 会引入不稳定。
- 每轮编译后如有异常，检查 `test_register.c` 是否已恢复。

常用命令：

```bash
python3 compile_elf.py --plat spike --name <case_name>
python3 compile_elf.py --plat linknan --include-commented --name <case_name>
```

### 5.2 `get_result.py`

- 运行 LinkNan 前确认环境变量已设置：`LINKNAN_HOME`、`DIFFTEST_REF_SO`。
- 运行 Spike 前确认 `SPIKE_BIN` 已设置。
- 非 `compile-only` case 必须有单 case 运行证据。
- wall-clock timeout 不是 stuck 结论；需要内部 watchdog/no-commit 或波形/日志证据。

### 5.3 `LOG_LEVEL`

需要细粒度断言打印时使用：

```bash
LOG_LEVEL=LOG_DETAIL
```

## 6. 提交前工具检查单

- 单 case 编译通过。
- 非 compile-only：单 case 运行结果可解释。
- compile-only：Gate D=`N/A` 原因明确。
- `test_register.c` 注册状态符合目标分层。
- `test_point` 只回填正文和 `已实现 case`，不追加审计式后半段块。
- 若复用已有 case，提供固定两行 `复用依据`：`顺序一致性`、`断言一致性`。
- 日志路径可追踪，失败有定位说明。
