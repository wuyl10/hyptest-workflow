### P0A. earlier width-switch entry

测试点：

- retry 成功后切到同地址不同模板 `sw(1B+3B)`，验证 width-switched store 不复用旧模板。

构建场景：

- `sd(1B+7B)` repeated `SAF` -> repair -> retry success -> immediate same-address width-switched `sw(1B+3B)` success

已实现 case：

- `ai_micro_placeholder_width_switch`

### P0B. latest same-template entry

测试点：

- refault repair 后再次发起同地址同模板 success store，应该继续 trap-free，且只保留最新 overlay。

构建场景：

- `sd(1B+7B)` repeated `SAF` -> repair -> upper-half aligned `sd(8B)` success x4 -> refault `SAF` -> repair -> retried original-template `sd(1B+7B)` success -> immediate same-template `sd(1B+7B)` success

已实现 case：

- `ai_micro_placeholder_same_template`
