#include "hal.h"
#include "CppUTest/TestHarness.h"
#include "CppUTestExt/MockSupport.h"
TEST_GROUP(Sensor) { void teardown() override { mock().checkExpectations(); mock().clear(); } };
TEST(Sensor, Mocked)  { mock("hal_read").expectOneCall("hal_read").withIntParameter("reg", 3).andReturnValue(8); LONGS_EQUAL(4, sensor_get(3)); }
TEST(Sensor, Spy)     { mock("hal_read").expectOneCall("hal_read").withIntParameter("reg", 3); LONGS_EQUAL(15, sensor_get(3)); }
TEST(Sensor, Real)    { mock("hal_read").ignoreOtherCalls(); LONGS_EQUAL(15, sensor_get(3)); }
