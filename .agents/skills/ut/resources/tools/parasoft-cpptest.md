# Parasoft C/C++test — quick reference

Parasoft has several products and versions. Syntax below is typical but **VERIFY against the repo's
existing test suites and stubs, and copy their exact pattern**. Record verified facts in KB `Build notes`.
Ask the user which product is used:
- **C/C++test Professional** (Eclipse / Visual Studio based): own unit-test framework (`CPPTEST_*`
  macros), generated test suites and stubs, run through the IDE or `cpptestcli` with a workspace.
- **C/C++test Standard**: mainly static analysis; coverage via `cpptestcc`.
- **C/C++test CT**: coverage + results for tests written in GoogleTest/CppUTest/others (`cpptestcc`,
  `cpptestcov`). If tests are gtest/CppUTest, load that framework file too.

## Test suite file (Professional) — typical generated structure
```cpp
#include "cpptest.h"

CPPTEST_CONTEXT("src/sensor.c");
CPPTEST_TEST_SUITE_INCLUDED_TO("src/sensor.c");

class TestSuite_sensor_c_1a2b3c : public CppTest_TestSuite
{
public:
    CPPTEST_TEST_SUITE(TestSuite_sensor_c_1a2b3c);
    CPPTEST_TEST(test_sensor_read_1);
    CPPTEST_TEST_SUITE_END();

    void setUp();
    void tearDown();
    void test_sensor_read_1();
};
CPPTEST_TEST_SUITE_REGISTRATION(TestSuite_sensor_c_1a2b3c);

void TestSuite_sensor_c_1a2b3c::setUp() {}
void TestSuite_sensor_c_1a2b3c::tearDown() {}

/* CPPTEST_TEST_CASE_BEGIN test_sensor_read_1 */
/* CPPTEST_TEST_CASE_CONTEXT int sensor_read(unsigned char) */
void TestSuite_sensor_c_1a2b3c::test_sensor_read_1()
{
    /* Pre-condition initialization */
    unsigned char _reg = 0x10;
    /* Tested function call */
    int _return = ::sensor_read(_reg);
    /* Post-condition check */
    CPPTEST_ASSERT_INTEGER_EQUAL(42, _return);
}
/* CPPTEST_TEST_CASE_END test_sensor_read_1 */
```
Rules:
- Every new test needs BOTH: a `CPPTEST_TEST(name);` line in the class block AND the method definition.
- Keep the `CPPTEST_TEST_CASE_BEGIN/END` and `CONTEXT` comments: the IDE's test case editor uses them.
- `CPPTEST_TEST_SUITE_INCLUDED_TO` means the suite is compiled together with that source file, so
  `static` functions and variables of the source are visible in the test.

## Assertions (expected first, then actual)
| Macro | Use |
|-------|-----|
| `CPPTEST_ASSERT(cond)` | boolean |
| `CPPTEST_ASSERT_INTEGER_EQUAL(e, a)`, `CPPTEST_ASSERT_UINTEGER_EQUAL(e, a)` | integers |
| `CPPTEST_ASSERT_BOOL_EQUAL(e, a)` | bool |
| `CPPTEST_ASSERT_FLOAT_EQUAL(e, a, delta)` | floating point |
| `CPPTEST_ASSERT_CSTR_EQUAL(e, a)`, `CPPTEST_ASSERT_CSTR_N_EQUAL(e, a, n)` | C strings |
| `CPPTEST_ASSERT_MEM_BUFFER_EQUAL(e, a, size)` | buffers |
| `CPPTEST_ASSERT_EQUAL(e, a)` | types with `==` |
| `CPPTEST_FAIL("msg")`, `CPPTEST_REPORT(...)` | fail / report a value |
| `CPPTEST_POST_CONDITION_*("name", value)` | records a value for regression (generated tests) — prefer real asserts |

## Stubs
Two styles; the repo uses one — copy it.
1. **User stub functions** (stub files, often in a `stubs/` folder):
```c
/** User stub definition for function: int spi_read(unsigned char) */
EXTERN_C_LINKAGE int spi_read (unsigned char reg) ;
EXTERN_C_LINKAGE int CppTest_Stub_spi_read (unsigned char reg)
{
    return 0;
}
```
   The tool redirects calls of `spi_read` to `CppTest_Stub_spi_read` in test builds.
   Per-test behaviour: `if (CppTest_IsCurrentTestCase("TestSuite_sensor_c_1a2b3c::test_sensor_read_1")) {...}`.
2. **Stub callbacks** (newer versions), registered per test:
```cpp
void CppTest_StubCallback_spi_read(CppTest_StubCallInfo* stubCallInfo, int* __return, unsigned char reg)
{
    *__return = -5;
}
// inside the test, before the call:
CPPTEST_REGISTER_STUB_CALLBACK("spi_read", &CppTest_StubCallback_spi_read);
CPPTEST_EXPECT_NCALLS("spi_read", 1);          // optional call-count check
```
Missing stub symptom: `undefined reference` or the real function runs. Stubs for a whole project are
often configured in the project's test configuration (auto-generated stubs): ask the user.

## Running (VERIFY with `cpptestcli -help` and the user's CI job)
Professional, typical:
```sh
cpptestcli -data <workspace> -resource <project or path> -config "builtin://Run Unit Tests" -report <out dir>
cpptestcli -listconfigs            # lists available test configurations (if supported)
```
Configs often used: "Run Unit Tests", "Run Unit Tests with Coverage", team/user configs such as
`user://My Config`. The user or CI job knows the real name. Reports: `<out dir>/report.xml` and `report.html`.
Result counts: search report.xml for failed tests; failures show file, line and assert.

## Coverage with cpptestcc (Standard / CT; VERIFY flags with `cpptestcc -help`)
```sh
cpptestcc -compiler <compiler id e.g. gcc_10-64> -line-coverage -decision-coverage -workspace <dir> -- gcc -c src/sensor.c -o sensor.o
# link the cpptestcc runtime library from <install>/runtime/lib (see docs), run the tests
# -> results in cpptest_results.clog (location configurable)
cpptestcov compute -map=<dir> -clog=cpptest_results.clog     # typical CT flow
cpptestcov report text -coverage=LC|DC|MCDC  <dir>           # text report, easy to grep
```
Other metrics flags: `-statement-coverage`, `-simple-condition-coverage`, `-mcdc-coverage`, `-function-coverage`.
Delete old `.clog` files before a fresh run. In Professional, coverage comes from the
"with Coverage" test configuration and is shown in the report and IDE.


Build or run fails → load `resources/tools/errors/parasoft-cpptest.md` (error messages and fixes).
