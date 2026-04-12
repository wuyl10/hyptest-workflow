#include <rvh_test.h>
#include <stdint.h>

/*
 * 推荐: 按 ai_arch_* 或 ai_micro_* 命名。
 * 每个函数仅保留一个 TEST_END(...)
 */

static inline uint64_t ai_template_load64(uintptr_t addr)
{
    return *(volatile uint64_t *)addr;
}

static inline void ai_template_store64(uintptr_t addr, uint64_t value)
{
    *(volatile uint64_t *)addr = value;
}

static inline bool ai_template_expect_cause(uint64_t cause)
{
    return excpt.triggered && excpt.cause == cause;
}

static inline bool ai_template_expect_cause_tval(uint64_t cause, uintptr_t tval)
{
    return excpt.triggered && excpt.cause == cause && excpt.tval == tval;
}

bool ai_template_normal_path_case()
{
    TEST_START();

    volatile uint64_t buf[2] = {0};
    uintptr_t addr = (uintptr_t)&buf[0];
    uintptr_t adjacent = (uintptr_t)&buf[1];
    uint64_t adjacent_before = 0xA5A5A5A5A5A5A5A5ULL;

    ai_template_store64(adjacent, adjacent_before);

    goto_priv(PRIV_M);
    TEST_SETUP_EXCEPT();
    ai_template_store64(addr, 0x1122334455667788ULL);

    TEST_SETUP_EXCEPT();
    uint64_t val = ai_template_load64(addr);

    TEST_ASSERT("normal path should not trigger exception and value should match",
        excpt.triggered == false &&
        val == 0x1122334455667788ULL
    );

    TEST_ASSERT("adjacent word should remain unchanged",
        ai_template_load64(adjacent) == adjacent_before
    );

    TEST_END("ai_template_normal_path_case");
}

bool ai_template_exception_path_case()
{
    TEST_START();

    uintptr_t fault_addr = 0;
    uintptr_t expect_tval = fault_addr;

    /*
     * no-H 默认策略下:
     * - 不依赖 H 特有指令/CSR
     * - 如需使用 HS helper，按项目约定把它当作 S 语义路径别名
     */
    goto_priv(PRIV_HS);

    /*
     * 这里替换为你的 fault 环境构造代码，例如:
     * - 调整页表权限制造 PF
     * - 调整 PMP 制造 AF
     * - 调整 PBMT 制造 misalign/AF 路径
     */

    TEST_SETUP_EXCEPT();
    (void)ai_template_load64(fault_addr);

    TEST_ASSERT("expected exception should be observed",
        excpt.triggered == true
    );

    /* 可选: 进一步校验 cause/tval */
    TEST_ASSERT("exception cause should match expectation",
        ai_template_expect_cause(CAUSE_LPF) || ai_template_expect_cause(CAUSE_LAF)
    );

    TEST_ASSERT("exception tval should match expectation when required",
        ai_template_expect_cause_tval(CAUSE_LPF, expect_tval) ||
        ai_template_expect_cause_tval(CAUSE_LAF, expect_tval)
    );

    /*
     * 若该 case 含 recover 路径，可在此追加：
     * 1) 修复环境（页表/PMP/PBMT）
     * 2) 再执行一次同形访问
     * 3) 断言 recover 成功 + 邻接数据未污染
     */

    TEST_END("ai_template_exception_path_case");
}
