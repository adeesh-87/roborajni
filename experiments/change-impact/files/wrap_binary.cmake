
# second binary: the shared --wrap + CppUMock stubs (C++ functions wrapped by mangled name)
set(UT_WRAPPED _ZN7cvaccel11PerfMonitor6recordERKNS_10PerfRecordE _ZNK7cvaccel10MemoryPool8physAddrEj)
add_executable(unit_tests_wrap ${CMAKE_CURRENT_SOURCE_DIR}/wrap/dispatcher_wrap_test.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/stubs/cvaccel_wrap_stubs.cpp ${CMAKE_CURRENT_SOURCE_DIR}/main.cpp ${UT_CODE_UNDER_TEST})
target_include_directories(unit_tests_wrap PRIVATE ${CMAKE_SOURCE_DIR}/client/include ${CMAKE_SOURCE_DIR}/include)
target_link_libraries(unit_tests_wrap PRIVATE ${CPPUTEST_EXT} ${CPPUTEST_LIB} Threads::Threads)
foreach(fn ${UT_WRAPPED})
  target_link_options(unit_tests_wrap PRIVATE "LINKER:--wrap=${fn}")
endforeach()
