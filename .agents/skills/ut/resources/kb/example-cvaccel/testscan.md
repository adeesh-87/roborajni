# Test code scan
Generated 2026-09-25 08:02 over 9 test source files: /tmp/claude-0/-home-user-roborajni/b4020067-36df-5cb5-a6cf-14371abb2f61/scratchpad/cvrepo/tests /tmp/claude-0/-home-user-roborajni/b4020067-36df-5cb5-a6cf-14371abb2f61/scratchpad/cvrepo/tests/mocks

## Framework (files using it)
| Framework | Files |
|---|---|
| CppUTest (CppUTest/TestHarness.h or TEST_GROUP) | 8 |
| GoogleTest (TEST/TEST_F/TEST_P) | 0 |
| gMock (MOCK_METHOD/EXPECT_CALL) | 0 |
| Unity (unity.h, RUN_TEST) | 0 |
| CMock (_ExpectAndReturn etc.) | 0 |
| CppUMock (mock().) | 0 |
| FFF (FAKE_*_FUNC) | 0 |
| Parasoft (CPPTEST_) | 0 |
| Catch2/doctest (TEST_CASE) | 0 |

## Test-case names (how tests are named)
Sample of real names, then the pattern classes:
Total test cases found: 215
  TEST(Dispatcher, CancelSession_L133_SessionFound_WakesUsingSessionClientFd)
  TEST(PerfMonitor, Record_CoreIndexOutOfRange_SkipsPerCoreAccumulation)
  TEST(CvAccelService, PostConfig_L103ConfigOneWordSet_CopiesWordToRequest)
  TEST(Dispatcher, Start_SubmitFails_RequestNotMovedToRunning)
  TEST(SessionManager, Find_IdEqualsKMaxSessions_PassesRangeCheck)
  TEST(Dispatcher, Pump_L38_CoreFreeWithManyRequests_StartsAllQueuedRequests)
  TEST(Dispatcher, CancelSession_L145_OpenRequestsZero_NoUnderflow)
  TEST(SessionManager, Open_ThreeActiveSessions_ReturnsOkWithFourthId)

Name pattern classes (2nd macro argument or function name):
    214  Snake_With_Underscores (e.g. Func_Condition_Expected)
      1  CamelCase

## Assertions (top 12)
    269  LONGS_EQUAL
    182  UNSIGNED_LONGS_EQUAL
    131  CHECK
     27  CHECK_TRUE
     11  POINTERS_EQUAL
      9  CHECK_FALSE
      3  STRCMP_EQUAL
      3  MEMCMP_EQUAL

## Mock / stub API (top 12)

## Fixtures and setup
| Item | Count |
|---|---|
| CppUTest TEST_GROUP | 9 |
| CppUTest setup()/teardown() | 0 / 0 |
| gtest fixture classes (: public ::testing::Test) | 0 |
| gtest SetUp()/TearDown() | 0 / 0 |
| Unity setUp()/tearDown() | 0 / 0 |
| mock().checkExpectations() / mock().clear() | 0 / 0 |
| extern "C" blocks around includes | 0 |
| #include "*.c" (testing statics by including the source) | 0 |
| IGNORE_TEST / DISABLED_ / TEST_IGNORE | 0 |

## File naming
      8  <name>_test.<ext>
      1  other: main.cpp

## Includes most used (top 10)
      8  "CppUTest/TestHarness.h"
      2  "cvaccel/perf_monitor.hpp"
      2  "cvaccel/memory_pool.hpp"
      1  "cvclient/cvclient.hpp"
      1  "cvaccel/session_manager.hpp"
      1  "cvaccel/service.hpp"
      1  "cvaccel/request_queue.hpp"
      1  "cvaccel/dispatcher.hpp"
      1  "CppUTest/CommandLineTestRunner.h"

## Exemplar candidates (typical, small, with mocks)
Score = uses mocks (+3), 30-200 lines (+2), has fixture (+1), >=3 test cases (+1). Read the top one first.
  score 4  /tmp/claude-0/-home-user-roborajni/b4020067-36df-5cb5-a6cf-14371abb2f61/scratchpad/cvrepo/tests/session_manager_test.cpp  (138 lines, 12 tests, 0 mock uses)
  score 2  /tmp/claude-0/-home-user-roborajni/b4020067-36df-5cb5-a6cf-14371abb2f61/scratchpad/cvrepo/tests/service_test.cpp  (2004 lines, 92 tests, 0 mock uses)
  score 2  /tmp/claude-0/-home-user-roborajni/b4020067-36df-5cb5-a6cf-14371abb2f61/scratchpad/cvrepo/tests/request_queue_test.cpp  (301 lines, 24 tests, 0 mock uses)
  score 2  /tmp/claude-0/-home-user-roborajni/b4020067-36df-5cb5-a6cf-14371abb2f61/scratchpad/cvrepo/tests/perf_monitor_test.cpp  (247 lines, 18 tests, 0 mock uses)
  score 2  /tmp/claude-0/-home-user-roborajni/b4020067-36df-5cb5-a6cf-14371abb2f61/scratchpad/cvrepo/tests/memory_pool_test.cpp  (334 lines, 31 tests, 0 mock uses)
  score 2  /tmp/claude-0/-home-user-roborajni/b4020067-36df-5cb5-a6cf-14371abb2f61/scratchpad/cvrepo/tests/dispatcher_test.cpp  (810 lines, 36 tests, 0 mock uses)

## Mock / stub files
(CMock generated mocks are not listed: they are generated from headers at build time)
