# CppUTest + CppUMock — quick reference

Always copy the includes, main and build setup from an existing test in the repo first.

## Minimal test file (C code under test)
```cpp
extern "C" {
#include "sensor.h"          // C headers of the code under test go inside extern "C"
}
#include "CppUTest/TestHarness.h"          // CppUTest headers LAST (they redefine new/malloc)
#include "CppUTestExt/MockSupport.h"

TEST_GROUP(Sensor)
{
    void setup() override    { sensor_init(); }
    void teardown() override { mock().checkExpectations(); mock().clear(); }
};

TEST(Sensor, Read_BusError_ReturnsMinusOne)
{
    mock().expectOneCall("spi_read").withParameter("reg", 0x10).andReturnValue(-5);
    LONGS_EQUAL(-1, sensor_read(0x10));
}
```
Runner (usually already exists, one per test binary):
```cpp
#include "CppUTest/CommandLineTestRunner.h"
int main(int ac, char** av) { return CommandLineTestRunner::RunAllTests(ac, av); }
```
`override` needs C++11. Older repos write `void setup()` without it — imitate the repo.

## Assertions (expected first, then actual)
| Macro | Use |
|-------|-----|
| `CHECK(c)`, `CHECK_TRUE(c)`, `CHECK_FALSE(c)` | booleans |
| `LONGS_EQUAL(e, a)` | signed integers, enums |
| `UNSIGNED_LONGS_EQUAL(e, a)` | unsigned integers |
| `BYTES_EQUAL(e, a)` | 8-bit values |
| `BITS_EQUAL(e, a, mask)` | compare only masked bits (registers) |
| `POINTERS_EQUAL(e, a)` | pointers, `NULL` |
| `STRCMP_EQUAL(e, a)`, `STRNCMP_EQUAL(e, a, n)` | C strings |
| `MEMCMP_EQUAL(e, a, size)` | buffers, structs |
| `DOUBLES_EQUAL(e, a, tolerance)` | floating point |
| `CHECK_EQUAL(e, a)` | C++ types with `==` (and StringFrom) |
| `FAIL("text")`, `CHECK_TEXT(c, "text")`, `LONGS_EQUAL_TEXT(e, a, "text")` | messages |
Other: `IGNORE_TEST(Group, Name)` disables a test (do not use unless asked).

## CppUMock
Test side (expectations):
```cpp
mock().expectOneCall("uart_send")
      .withParameter("len", 3)
      .withMemoryBufferParameter("data", expected, 3)   // compares buffer contents
      .andReturnValue(0);
mock().expectNCalls(2, "delay_ms").withParameter("ms", 10);
mock().expectNoCall("reset");
mock().expectOneCall("adc_get").withOutputParameterReturning("value", &val, sizeof(val)).andReturnValue(0);
mock().expectOneCall("log").ignoreOtherParameters();     // do not check params
mock().ignoreOtherCalls();                                // only if the repo does this
mock().strictOrder();                                      // calls must come in expectation order
```
Mock side (the fake function, in the mocks folder):
```cpp
extern "C" int uart_send(const uint8_t* data, size_t len)
{
    return mock().actualCall("uart_send")
                 .withMemoryBufferParameter("data", data, len)
                 .withParameter("len", (int)len)        // cast: types must match the expectation
                 .returnIntValueOrDefault(0);
}
extern "C" int adc_get(uint16_t* value)
{
    return mock().actualCall("adc_get").withOutputParameter("value", value).returnIntValueOrDefault(0);
}
extern "C" void delay_ms(uint32_t ms) { mock().actualCall("delay_ms").withParameter("ms", (int)ms); }
```
Return helpers: `returnIntValueOrDefault`, `returnUnsignedIntValueOrDefault`, `returnLongIntValueOrDefault`,
`returnBoolValueOrDefault`, `returnPointerValueOrDefault`, `returnConstPointerValueOrDefault`,
`returnDoubleValueOrDefault`, `returnStringValueOrDefault`. For pointers expect with
`.andReturnValue((void*)ptr)`.
Parameter names in `expect` and `actual` must be identical strings. Pointers: `withPointerParameter`.
Custom struct parameters: `withParameterOfType("Type", "name", &obj)` + a comparator installed with
`mock().installComparator("Type", comparator)` — only if the repo already uses it.
Shared data: `mock().setData("name", 5);` / `mock().getData("name").getIntValue()`.

## Other substitution techniques
- Function pointer: `UT_PTR_SET(fp_variable, stub_function);` — restored automatically after the test.
- Link-time substitution: the test build links `mocks/foo_mock.c` instead of `src/foo.c`.

## Running
```sh
./AllTests -v                  # verbose, one line per test
./AllTests -g Sensor           # groups containing "Sensor"   (-sg exact group)
./AllTests -n Read             # tests whose name contains "Read" (-sn exact name)
./AllTests -sg Sensor -sn Read_BusError_ReturnsMinusOne
./AllTests -r3                 # repeat 3 times (find state leaks)
./AllTests -ojunit             # JUnit XML files
./AllTests -lg / -ln           # list groups / test names
```
Summary line: `OK (12 tests, 12 ran, 30 checks, 0 ignored, 0 filtered out, 3 ms)` or
`Errors (2 failures, 12 tests, 12 ran, ...)`. A failure looks like:
```
tests/sensor_test.cpp:42: error: Failure in TEST(Sensor, Read_Ok)
	LONGS_EQUAL(1, 2) failed
	expected <1 (0x1)>
	but was  <2 (0x2)>
```
Find all failures: `grep -n 'error: Failure in' <run log>`.

## Build notes
- Libraries: `CppUTest` and, for mocks, `CppUTestExt` (order: `-lCppUTestExt -lCppUTest`).
- Makefile projects often use CppUTest's `MakefileWorker.mk` with `CPPUTEST_HOME`, `SRC_DIRS`,
  `TEST_SRC_DIRS`, `MOCKS_SRC_DIRS`, `INCLUDE_DIRS`, `CPPUTEST_USE_EXTENSIONS=Y`, `CPPUTEST_USE_GCOV=Y`.
- New test files in a `TEST_SRC_DIRS` folder are picked up automatically; with CMake add them to the target.

## Errors and fixes
| Message | Fix |
|---------|-----|
| `Memory leak(s) found` in a test using mocks | `mock().clear()` in `teardown()` (mocks allocate) |
| Leak from code under test | free it in the test, or `EXPECT_N_LEAKS(n)` if the leak is intended — ask. `malloc` leaks are only seen when the build force-includes `CppUTest/MemoryLeakDetectorMallocMacros.h` (MakefileWorker does); `new` leaks are always seen |
| compile errors in `<vector>`, `<string>`, `new` macros | include STL / system headers BEFORE CppUTest headers |
| `Mock Failure: Unexpected call to function: X` | add `expectOneCall("X")` or check the path taken |
| `Mock Failure: Expected call WAS NOT fulfilled.` (lists `expected 1 call, called 0 times`) | code did not call it: check inputs, branch, parameter values |
| `Mock Failure: Unexpected parameter value` / `...type` | fix the value; older CppUTest also needs identical types on both sides: cast both to `(int)` or `(unsigned int)` |
| mock returns 0 although you expected a value | `.andReturnValue(v)` missing on the expectation (the `...OrDefault` helpers hide this) |
| `undefined reference` to a C function from test | missing `extern "C"` around the C include |
| `multiple definition` | real source and mock both linked: remove one from the test build |
