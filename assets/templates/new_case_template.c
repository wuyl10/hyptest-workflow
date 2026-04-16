#include <rvh_test.h>
#include <stdbool.h>

/*
 * Read references/writing_cases.md first.
 * Inspect 2~5 similar existing ai_test_cases before filling this skeleton.
 * This file is only a minimal shape reminder, not a source of truth.
 */

bool ai_xxx_case_name()
{
    TEST_START();

    goto_priv(PRIV_M);
    // 1) 准备数据/页表/PMP/PBMT环境

    // 2) 若本步骤要检查 excpt.*，先初始化异常状态
    // TEST_SETUP_EXCEPT();

    // 3) 执行目标指令/路径

    // 4) 断言
    TEST_ASSERT("行为描述", condition);

    TEST_END("ai_xxx_case_name");
}
