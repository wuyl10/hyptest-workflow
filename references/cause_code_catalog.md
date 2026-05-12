# CAUSE 代码速查表

本文是 hyptest case 里 `excpt.cause` 断言要写的**常量名**速查表。宏定义在 `inc/csrs.h`；这里只做"场景 → 常量"的快速映射，避免写 `CAUSE_LAF` vs `CAUSE_SAF` vs `CAUSE_LPF` 这类混淆。

profile 特定的非对齐处理（如 NHV5.1AP 的 "Device 区域非对齐 = AF 口径"）以 `references/spec_profiles/<spec_profile>.md` 为准，本表只列通用语义。

## 1. Exception 常量全表（值来自 csrs.h）

| 宏 | 值 | 含义 |
| --- | --- | --- |
| `CAUSE_IAM` | 0 | Instruction Address Misaligned |
| `CAUSE_IAF` | 1 | Instruction Access Fault |
| `CAUSE_ILI` | 2 | Illegal Instruction |
| `CAUSE_BKP` | 3 | Breakpoint |
| `CAUSE_LAM` | 4 | Load Address Misaligned |
| `CAUSE_LAF` | 5 | Load Access Fault |
| `CAUSE_SAM` | 6 | Store/AMO Address Misaligned |
| `CAUSE_SAF` | 7 | Store/AMO Access Fault |
| `CAUSE_ECU` | 8 | Environment Call from U-mode |
| `CAUSE_ECS` | 9 | Environment Call from S-mode |
| `CAUSE_ECV` | 10 | Environment Call from VS-mode |
| `CAUSE_ECM` | 11 | Environment Call from M-mode |
| `CAUSE_IPF` | 12 | Instruction Page Fault |
| `CAUSE_LPF` | 13 | Load Page Fault |
| `CAUSE_SPF` | 15 | Store/AMO Page Fault |
| `CAUSE_IGPF` | 20 | Instruction Guest-Page Fault |
| `CAUSE_LGPF` | 21 | Load Guest-Page Fault |
| `CAUSE_VRTI` | 22 | Virtual Instruction |
| `CAUSE_SGPF` | 23 | Store/AMO Guest-Page Fault |

## 2. 场景 → CAUSE 映射（写 case 前先按这张表选常量）

### Load 相关

| 场景 | cause | 备注 |
| --- | --- | --- |
| Load 到无有效 PTE 的 VA | `CAUSE_LPF` | 页表 V=0 / U 态访问 S 页 / 权限不足等翻译失败 |
| Load 到 PA 不可读（PMP/PMA 禁止 / Bad PA） | `CAUSE_LAF` | 翻译成功但 PA 物理不可访问 |
| Load 非对齐到普通 memory 区 | `CAUSE_LAM` | 若 CPU 支持，硬件可能自动拆分不报异常；看 profile |
| Load 非对齐到 Device 区（NHV5.1AP 口径） | `CAUSE_LAF` | 见 `spec_profiles/nhv5_1_ap.md` §6 |
| Load 到 G-stage 翻译失败（H 扩展） | `CAUSE_LGPF` | 仅 H 扩展场景 |
| Load 非对齐且同时 PF | 先 `LAM` 还是 `LPF` 取决于 first encountered fault | 看 profile |

### Store / AMO 相关

| 场景 | cause | 备注 |
| --- | --- | --- |
| Store 到无有效 PTE 的 VA | `CAUSE_SPF` | 翻译失败 |
| Store 到 PA 不可写（PMP/PMA/Bad PA） | `CAUSE_SAF` | 翻译成功但物理禁止 |
| Store 非对齐到普通 memory 区 | `CAUSE_SAM` | 同 LAM，看平台 |
| Store 非对齐到 Device 区（NHV5.1AP 口径） | `CAUSE_SAF` | 见 `spec_profiles/nhv5_1_ap.md` §6 |
| Store 到只读页（PTE.W=0） | `CAUSE_SPF` | 翻译阶段挡下来 |
| AMO 非对齐到任何区域 | `CAUSE_SAF` | profile 口径：原子非对齐走 AF |
| Vector store 非对齐到 Device/NC | `CAUSE_SAF` | profile 口径：向量 NC/IO 非对齐走 AF |

### Instruction 相关

| 场景 | cause | 备注 |
| --- | --- | --- |
| 取指到无 PTE | `CAUSE_IPF` | iTLB 翻译失败 |
| 取指到 PA 不可执行 | `CAUSE_IAF` | PTE.X=0 或 PMP 禁止 |
| PC 跳到非对齐地址（非 C 扩展） | `CAUSE_IAM` | C 扩展下 2B 对齐仍合法 |
| 非法指令编码 / 未实现 CSR | `CAUSE_ILI` | 包括错误的 CSR 读写权限 |
| 调试断点（ebreak） | `CAUSE_BKP` | |

### 环境调用 / 陷入

| 场景 | cause |
| --- | --- |
| U 态 ecall | `CAUSE_ECU` |
| S 态 ecall | `CAUSE_ECS` |
| VS 态 ecall（H 扩展） | `CAUSE_ECV` |
| M 态 ecall | `CAUSE_ECM` |
| 在 VS/VU 态执行虚拟化敏感指令 | `CAUSE_VRTI` |

### Guest 页故障（H 扩展）

| 场景 | cause |
| --- | --- |
| Guest 取指翻译失败 | `CAUSE_IGPF` |
| Guest load 翻译失败 | `CAUSE_LGPF` |
| Guest store 翻译失败 | `CAUSE_SGPF` |

## 3. 常见错误对照

写断言时容易弄错的几对：

- **`CAUSE_LAF` vs `CAUSE_LPF`**：都是 load 异常
  - `LPF` = 翻译阶段失败（PTE 不存在 / 权限不够）
  - `LAF` = 翻译后 PA 物理不可访问（PMP/PMA/Bad PA）
- **`CAUSE_SAF` vs `CAUSE_SPF`**：同理，store 版本
- **`CAUSE_LAM` vs `CAUSE_LAF`**（非对齐 load）：
  - memory 区 = `LAM`（或平台自动拆分不报）
  - Device 区（profile 特定）= `LAF`
- **`CAUSE_SAM` vs `CAUSE_SAF`**（非对齐 store）：
  - memory 区 = `SAM`
  - Device 区 / AMO / vector NC = `SAF`
- **`CAUSE_IAM` 在 C 扩展下几乎不触发**：压缩指令 2B 对齐已合法
- **`CAUSE_ECU/ECS/ECV/ECM`**：按**当前特权态**选，不是按陷入目标态

## 4. 优先级冲突

同一次访问可能同时满足多个异常条件时，按 RISC-V spec "first encountered fault"：

- 翻译失败（PF/GPF）先于 PMP/PMA 检查（AF）
- 地址对齐检查的先后看具体实现，profile 里如果有项目口径（例如 NHV5.1AP "翻译/权限先触发时按 first encountered fault"）以 profile 为准

同一段访存断言 `excpt.cause` 时，先参考 profile §6（异常优先级）再定常量。

## 5. 使用建议

- 写 case 前先明确"这条断言对应哪种访问 + 哪种失败原因"，再查表选常量
- 不确定时用 profile 的 PMA/PBMT 矩阵 + profile §6（异常优先级）交叉验证
- 写完 case 后如果 Spike 跑出来的实际 cause 和你断言的不一致，先看是不是选错常量，而不是立刻怀疑 RTL
