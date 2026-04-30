# HYPTEST 编译、运行与调试指南

本文给出在 https://github.com/wuyl10/riscv-hyp-tests-nhv5.git 的 `nhv5.1` 分支目录中最实用、可直接执行的命令序列。

## 1. 环境准备

在仓库根目录执行：

```bash
pwd
# 期望: 当前目录是 riscv-hyp-tests-nhv5 的 nhv5.1 分支工作目录

git remote -v
git branch --show-current
# 期望: remote 包含 https://github.com/wuyl10/riscv-hyp-tests-nhv5.git
# 期望: 当前分支为 nhv5.1

which riscv64-unknown-elf-gcc
which make
```

若 `riscv64-unknown-elf-gcc` 不在 PATH，先修复工具链环境。

## 2. 全量编译

最基础编译命令（Makefile 实参）：

```bash
make PLAT=spike CROSS_COMPILE=riscv64-unknown-elf-
```

调试断言更友好的日志等级：

```bash
make PLAT=spike LOG_LEVEL=LOG_DETAIL CROSS_COMPILE=riscv64-unknown-elf-
```

产物位置：

- `build/spike/rvh_test.elf`
- `build/spike/rvh_test.bin`
- `build/spike/rvh_test.asm`

## 3. 单 case / 小批量编译（推荐）

脚本：`compile_elf.py`

### 3.1 按名字编译

```bash
python3 compile_elf.py --plat spike --name ai_arch_lb_sign_extension
```

### 3.2 按行号范围编译（从 test_register.c 抽取）

```bash
python3 compile_elf.py --plat spike 504 556
```

### 3.3 编译所有可见注册项

```bash
python3 compile_elf.py --plat spike all
```

### 3.4 包含已注释注册项（常用于 manual/compile-only）

```bash
python3 compile_elf.py --plat spike --include-commented --match '^ai_micro_'
```

编译输出目录：

- `case_elf_asm/spike/*.ELF`
- `case_elf_asm/spike/*.asm`

## 4. 运行

## 4.1 运行单 ELF

建议优先复用 `get_result.py` 默认命令模板，避免 ISA 参数漂移。

推荐单 case 运行命令（与默认 runner 保持一致）：

```bash
python3 get_result.py --platform spike --case ai_arch_lb_sign_extension
```

若需查看实际 runner 命令，优先用 dry-run：

```bash
python3 get_result.py --platform spike --case ai_arch_lb_sign_extension --dry-run
```

说明：

- 不在本文长期维护手写 Spike ISA 参数，避免与 `get_result.py` runner 模板漂移。
- 若必须手动执行，先用 `get_result.py --dry-run` 拿到当前命令，再按需复制修改。
- 若本地手动命令与脚本 runner 模板不一致，以 `get_result.py` 为准。
- runner 参数不等价于项目规格；规格与 Spike gate 口径以 `references/spec_profiles/<spec_profile>.md` 为准。
- 若失败需要 stuck/timeout、difftest mismatch、FSDB、50000 cycles no commit 或 suspected RTL bug 判断，切到 `hyptest-failure-triage` 做失败闭环。

## 4.2 批量跑（推荐）

脚本：`get_result.py`

按默认安全行段（脚本内置范围）批跑：

```bash
python3 get_result.py --platform spike
```

按指定行段跑：

```bash
python3 get_result.py --platform spike --range 504-556 --range 772-798
```

只跑指定 case：

```bash
python3 get_result.py --platform spike --case ai_arch_lb_sign_extension
```

按 ELF 目录全跑：

```bash
python3 get_result.py --platform spike --elf-dir case_elf_asm/spike --all-elves
```

先看将要执行的 case（不真正运行）：

```bash
python3 get_result.py --platform spike --range 504-556 --dry-run
```

## 5. 结果与日志

默认日志目录：

- `result_log/spike/`
- `result_log/linknan/`

`get_result.py` 汇总信息常看字段：

- `passed_cases`
- `failed_cases`
- `missing_elf_cases`
- `timeout_cases`
- `untested_exception_cases`

失败日志会保存从 `risc-v NH-V5 tests` 起的完整输出，适合定位。

## 6. 调试套路

### 6.1 先区分三类失败

- 编译失败：语法、宏、CSR 常量、链接符号问题。
- 运行失败：`FAILED`、`untested exception`、`TIMEOUT`。
- 语义分歧：Spike 与项目规则不一致（转 manual/compile-only 评估）。

### 6.2 高频问题与处理

`ERROR: untested exception!`：

- 检查是否在预期异常点前设置了 `TEST_SETUP_EXCEPT()`。
- 检查是否在 case 各段切换后清理/重置了异常状态。
- 检查特权态是否正确（`goto_priv`）。

看不到断言明细：

- 编译时用 `LOG_LEVEL=LOG_DETAIL`。

case 卡死或顺序异常：

- 先按日志定位“最后打印/最后进入”的 case，再做 1~3 个 case 的最小复现实验确认真实顺序；不要只按 `test_register.c` 视觉顺序推断。

某些 case 在 Spike 不稳定：

- 对 PMA/PBMT/cache/uncache 相关场景，按规则改为 manual 或 compile-only。

## 7. 最小闭环命令集

新增一个 case 后，建议至少跑这 5 步：

```bash
# 1) 按名字单编
python3 compile_elf.py --plat spike --name <case_name>

# 2) 单 case 运行
python3 get_result.py --platform spike --case <case_name>

# 3) 看摘要日志
ls result_log/spike | tail

# 4) 如失败，打开对应 log 分析
# 关注 returncode、missing_required、found_forbidden、untested_occurrences

# 5) 根据结果决定是否进入 default 注册
```

## 7.1 环境自检

开始编译/运行前，建议先检查 repo anchors 和平台环境变量：

```bash
python3 scripts/check_env.py --repo-root <repo_root> --platform spike
python3 scripts/check_env.py --repo-root <repo_root> --platform linknan
```

`check_env.py` 只检查环境是否足够执行，不会 fallback 到个人路径。

需要提示 export 写法时：

```bash
python3 scripts/check_env.py --repo-root <repo_root> --platform spike --print-exports
```

## 8. default/manual/compile-only 决策

- default：编译稳定 + Spike 稳定 + 语义与规则一致。
- manual：场景合理，但 Spike 不是可靠 gate。
- compile-only：当前只保证可编译，用于覆盖 RTL 风险路径。

不要把“能编译”直接等价为“可默认回归”。

## 9. 常用组合命令（建议收藏）

单 case 最短路径：

```bash
python3 compile_elf.py --plat spike --name <case_name> && \
python3 get_result.py --platform spike --case <case_name>
```

先编译后 dry-run 预览批跑：

```bash
python3 compile_elf.py --plat spike 504 556 && \
python3 get_result.py --platform spike --range 504-556 --dry-run
```

只看最新批跑摘要：

```bash
ls -t result_log/spike/spike_batch_result_*.log | head -n 3
```

## 10. 失败类型 -> 处理动作映射

- `missing_elf_cases > 0`
  - 先检查是否编译了对应 case（命名/注册/过滤条件）。
- `found_forbidden` 包含 `untested exception`
  - 先核查 `TEST_SETUP_EXCEPT()` 与特权态切换，再核查预期 cause/tval。
- `found_forbidden` 仅有 `FAILED`
  - 优先看断言文案对应的条件，不要先改规则结论。
- `TIMEOUT`
  - 优先排查 WFI、循环退出条件、异常返回路径。

## 11. 日志解读速查

`get_result.py` 失败项关键字段：

- `missing_required`: 必须出现但未出现的标记（常见为 `PASSED`）
- `found_forbidden`: 出现了禁止标记（如 `FAILED`、`ERROR:`）
- `untested_occurrences`: 非预期异常计数
- `returncode`: Spike 进程返回码

解释建议：

- `returncode=0` 但有 `FAILED`：多数是断言失败，不是进程崩溃。
- `returncode=0` 且有 `ERROR: untested exception`：多数是框架捕获到非预期 trap。

## 12. 调试输出建议（不改变语义）

定位困难时可临时增加：

- 当前特权态
- `excpt.triggered/cause/tval/tval2/tinst`
- 关键目标地址与邻接地址值

调试结束后，保留必要断言，去掉冗余打印，避免日志噪声掩盖核心信息。
