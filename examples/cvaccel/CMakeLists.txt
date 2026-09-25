cmake_minimum_required(VERSION 3.16)
project(cvaccel CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

add_compile_options(-Wall -Wextra)

option(BUILD_UNIT_TESTS "Build CppUTest unit tests" OFF)
option(COVERAGE "gcov instrumentation" OFF)

find_package(Threads REQUIRED)

# libcvaccel: the base app / service implementation.
file(GLOB CVACCEL_SOURCES CONFIGURE_DEPENDS src/*.cpp)
add_library(cvaccel STATIC ${CVACCEL_SOURCES})
target_include_directories(cvaccel PUBLIC include)

if(COVERAGE)
    target_compile_options(cvaccel PRIVATE --coverage -O0)
    target_link_options(cvaccel PUBLIC --coverage)
endif()

# libcvsim: the simulated hardware block, device and transport.
file(GLOB CVSIM_SOURCES CONFIGURE_DEPENDS sim/*.cpp)
add_library(cvsim STATIC ${CVSIM_SOURCES})
target_include_directories(cvsim PUBLIC sim client/include)
target_link_libraries(cvsim PUBLIC cvaccel)

# libcvclient: the static library client applications link against.
add_library(cvclient STATIC client/src/cvclient.cpp)
target_include_directories(cvclient PUBLIC client/include)
target_link_libraries(cvclient PUBLIC cvaccel)

# demo_app: integration demo exercising the whole simulated stack.
add_executable(demo_app apps/demo_app.cpp)
target_link_libraries(demo_app PRIVATE cvclient cvsim cvaccel Threads::Threads)

if(BUILD_UNIT_TESTS)
    enable_testing()
  add_subdirectory(tests)
endif()
