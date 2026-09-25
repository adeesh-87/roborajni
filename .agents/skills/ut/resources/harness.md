# Minimal test harness for a codebase with no unit tests (pilot, greenfield)

Recommend: C code → CppUTest (mocking built in) or Unity+CMock when the team already uses Ceedling;
C++ code → GoogleTest + gMock. Build with the build system the repo already uses (CMake preferred).
Layout: `tests/CMakeLists.txt` (or Makefile), `tests/<module>_test.cpp` per source file, `tests/mocks/` for hand-written mocks.
Ask the user where the framework comes from: system package, vendored source, or `FetchContent` (needs network).

## CMake + CppUTest (C code under test, C++ test files)
```cmake
# tests/CMakeLists.txt  (added with add_subdirectory(tests) under an option, e.g. if(BUILD_UNIT_TESTS))
find_library(CPPUTEST_LIB CppUTest)      # or add_subdirectory of a vendored CppUTest
find_library(CPPUTEST_EXT CppUTestExt)
add_executable(unit_tests main.cpp sensor_test.cpp mocks/hal_mock.cpp ${CMAKE_SOURCE_DIR}/src/sensor.c)
target_include_directories(unit_tests PRIVATE ${CMAKE_SOURCE_DIR}/src ${CMAKE_SOURCE_DIR}/include)
target_link_libraries(unit_tests ${CPPUTEST_EXT} ${CPPUTEST_LIB})
add_test(NAME unit_tests COMMAND unit_tests -v)
```
`main.cpp`: `#include "CppUTest/CommandLineTestRunner.h"` / `int main(int ac, char** av) { return CommandLineTestRunner::RunAllTests(ac, av); }`
Run one group: `./unit_tests -sg Sensor`. Test file skeleton and mocks: `tools/cpputest.md`.

## CMake + GoogleTest/gMock
```cmake
find_package(GTest REQUIRED)             # or FetchContent_Declare(googletest ...) if allowed
add_executable(unit_tests logger_test.cpp ${CMAKE_SOURCE_DIR}/src/logger.cpp)
target_include_directories(unit_tests PRIVATE ${CMAKE_SOURCE_DIR}/src)
target_link_libraries(unit_tests GTest::gtest_main GTest::gmock)
include(GoogleTest); gtest_discover_tests(unit_tests)
```
Run one suite: `./unit_tests --gtest_filter='LoggerTest.*'`. Skeleton: `tools/gtest-gmock.md`.
C sources called from C++ tests need `extern "C" { #include "sensor.h" }`.

## Unity + CMock via Ceedling (C only)
`ceedling new tests_project` creates `project.yml`; point `:paths: :source:` at the code, `:test:` at `test/`;
mocks are generated from headers included as `#include "mock_spi.h"`. Run: `ceedling test:all`. Skeleton: `tools/unity-cmock.md`.

## Make (no CMake)
One rule that compiles the test files, the mocks and the sources under test with `-I` paths and links the
framework libraries (`-lCppUTestExt -lCppUTest` or `-lgmock -lgtest -lpthread`), then runs the binary. Copy the
compile flags of the production build (`-D` defines, `-std=`); drop target-only flags (`-mcpu`, linker scripts).

Verify the harness with one empty test before writing the pilot tests; record the commands in KB `Commands`.
