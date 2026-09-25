# Test exemplar: <test file path>   (approved: no | approved on <date> by the user)
Copy this shape for every new test. Verbatim from the repo, cut to ≤ 80 lines; comments in the right column say what each part is.

```cpp
<verbatim test file, e.g.:>
extern "C" {                          // C headers of the code under test inside extern "C"
#include "sensor.h"
}
#include "CppUTest/TestHarness.h"     // framework headers last
#include "CppUTestExt/MockSupport.h"

TEST_GROUP(Sensor)                    // one group per source file
{
    void setup() override    { sensor_init(); }                              // state reset
    void teardown() override { mock().checkExpectations(); mock().clear(); } // mock verification
};

TEST(Sensor, Read_BusError_ReturnsMinusOne)                                  // <Function>_<Condition>_<Expected>
{
    mock().expectOneCall("spi_read").withParameter("reg", 0x10).andReturnValue(-5);   // arrange: mock returns the error
    LONGS_EQUAL(-1, sensor_read(0x10));                                      // act + assert, expected first
}
```

## Skeleton for a new test file (fill the <...>)
```cpp
<same includes>
TEST_GROUP(<Module>) { <same setup/teardown> };
TEST(<Module>, <Function>_<Condition>_<Expected>)
{
    <mock expectations>
    <ASSERT_MACRO>(<expected>, <call>);
}
```
Register it: see exemplars/register.md.
