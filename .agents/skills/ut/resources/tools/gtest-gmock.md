# GoogleTest + gMock (+ FFF) — quick reference

Always copy includes, fixtures and build setup from an existing test in the repo first.

## Minimal test file (C code under test)
```cpp
#include <gtest/gtest.h>
#include <gmock/gmock.h>
extern "C" {
#include "sensor.h"
}
using ::testing::_;
using ::testing::Return;
using ::testing::StrictMock;

class SensorTest : public ::testing::Test {
protected:
    void SetUp() override { sensor_init(); }
    void TearDown() override {}
};

TEST_F(SensorTest, Read_ValidRegister_ReturnsValue) {
    EXPECT_EQ(42, sensor_read(0x10));
}
TEST(SensorNoFixture, Init_Twice_IsHarmless) { EXPECT_EQ(0, sensor_init()); }
```
Main: usually link `GTest::gtest_main` (no main needed). Otherwise:
```cpp
int main(int argc, char** argv) { ::testing::InitGoogleTest(&argc, argv); return RUN_ALL_TESTS(); }
```

## Assertions
`EXPECT_*` continues after failure, `ASSERT_*` stops the test (use ASSERT for pointers you then dereference).
| Macro | Use |
|-------|-----|
| `EXPECT_EQ(a, b)`, `NE`, `LT`, `LE`, `GT`, `GE` | integers, enums, pointers (`nullptr`) — keep the repo's order (expected, actual) |
| `EXPECT_TRUE(c)`, `EXPECT_FALSE(c)` | booleans |
| `EXPECT_STREQ(e, a)`, `EXPECT_STRNE`, `EXPECT_STRCASEEQ` | C strings |
| `EXPECT_FLOAT_EQ`, `EXPECT_DOUBLE_EQ`, `EXPECT_NEAR(e, a, tol)` | floating point |
| `EXPECT_EQ(0, memcmp(e, a, n))` | buffers |
| `EXPECT_THAT(v, ElementsAre(1, 2, 3))`, `ElementsAreArray(arr, n)` | arrays, containers |
| `EXPECT_THROW(stmt, Ex)`, `EXPECT_NO_THROW`, `EXPECT_ANY_THROW` | C++ exceptions |
| `EXPECT_DEATH(stmt, "regex")` | abort/assert paths (slow; only if repo uses it) |
| `<< "message"` after any macro | extra message |
Parameterised: `class T : public ::testing::TestWithParam<int> {}; TEST_P(T, Name) { GetParam(); }`
`INSTANTIATE_TEST_SUITE_P(Values, T, ::testing::Values(1, 2, 3));` (older gtest: `INSTANTIATE_TEST_CASE_P`).

## gMock for C++ interfaces
```cpp
class MockBus : public IBus {
public:
    MOCK_METHOD(int, read, (uint8_t reg, uint8_t* out), (override));
    MOCK_METHOD(void, write, (uint8_t reg, uint8_t val), (override));
};
StrictMock<MockBus> bus;                     // any unexpected call fails
EXPECT_CALL(bus, read(0x10, _))
    .WillOnce(DoAll(SetArgPointee<1>(42), Return(0)));
EXPECT_CALL(bus, write(0x11, _)).Times(2);
ON_CALL(bus, read(_, _)).WillByDefault(Return(-1));   // default without expectation
```
Old syntax in older repos: `MOCK_METHOD2(read, int(uint8_t, uint8_t*));` — imitate the repo.
Order: `::testing::InSequence seq;` before the EXPECT_CALLs.
Matchers: `_`, `Eq(x)`, `Ne`, `Gt`, `Lt`, `IsNull()`, `NotNull()`, `Pointee(x)`, `StrEq("s")`,
`HasSubstr`, `Field(&S::f, x)`, `AllOf(...)`, `AnyOf(...)`.
Buffer argument (pointer + length): `.With(Args<1, 2>(ElementsAreArray(expected)))`.
Copy data to an out-buffer: `SetArrayArgument<1>(src, src + n)`. Custom action: `Invoke(fn)`.
`NiceMock<>` ignores unexpected calls, `StrictMock<>` fails on them — use what the repo uses.

## gMock for C functions (free functions)
gMock cannot mock free functions directly. Pattern: a mock class + C forwarding functions.
```cpp
class HalMock { public: MOCK_METHOD(int, spi_read, (uint8_t reg)); };
static HalMock* g_hal = nullptr;
extern "C" int spi_read(uint8_t reg) { return g_hal->spi_read(reg); }   // links instead of real spi_read

class SensorTest : public ::testing::Test {
protected:
    StrictMock<HalMock> hal;
    void SetUp() override { g_hal = &hal; }
    void TearDown() override { g_hal = nullptr; }
};
```

## FFF (Fake Function Framework) — common with gtest for C
```cpp
#include "fff.h"
DEFINE_FFF_GLOBALS;                                   // once per test binary
extern "C" {                                          // REQUIRED in .cpp files: C code must link to the fakes
FAKE_VALUE_FUNC(int, spi_read, uint8_t);              // int spi_read(uint8_t)
FAKE_VOID_FUNC(delay_ms, uint32_t);
}
// in SetUp(): RESET_FAKE(spi_read); RESET_FAKE(delay_ms); FFF_RESET_HISTORY();
spi_read_fake.return_val = 42;
int seq[] = {1, 2, 3}; SET_RETURN_SEQ(spi_read, seq, 3);
EXPECT_EQ(1u, spi_read_fake.call_count);
EXPECT_EQ(0x10, spi_read_fake.arg0_val);
spi_read_fake.custom_fake = my_impl;                  // own behaviour
```
Header for shared fakes: `DECLARE_FAKE_VALUE_FUNC(...)` in .h, `DEFINE_FAKE_VALUE_FUNC(...)` in one .c/.cpp.

## Running
```sh
./tests --gtest_filter='SensorTest.*'                 # one suite
./tests --gtest_filter='SensorTest.Read_*:-*Slow*'    # pattern, minus exclusions
./tests --gtest_list_tests
./tests --gtest_repeat=5 --gtest_shuffle              # find order dependence
./tests --gtest_output=xml:report.xml
ctest --test-dir build --output-on-failure -R Sensor  # via CTest
```
Summary: `[  PASSED  ] 11 tests.` and `[  FAILED  ] 1 test, listed below:` then `[  FAILED  ] Suite.Name`.
A failure looks like:
```
tests/sensor_test.cpp:42: Failure
Expected equality of these values:
  1
  2
[  FAILED  ] SensorTest.Read_Ok (0 ms)
```
Find all failures: `grep -nE ': Failure$|^\[  FAILED  \]' <run log>`.
`DISABLED_` prefix on a test name disables it (do not use unless asked).

## CMake
```cmake
add_executable(sensor_tests test_sensor.cpp ../src/sensor.c mocks/hal_mock.cpp)
target_link_libraries(sensor_tests PRIVATE GTest::gtest_main GTest::gmock)
include(GoogleTest)
gtest_discover_tests(sensor_tests)
```


Build or run fails → load `resources/tools/errors/gtest-gmock.md` (error messages and fixes).
