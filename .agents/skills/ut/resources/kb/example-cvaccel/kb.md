# Knowledge base: example-cvaccel
> Generated sections from kb.json (the ut tool). Hand-written notes: notes.md, modules/<name>.md.
> Last updated: 2026-09-25 07:47

## Identity
| Key | Value |
|---|---|
| id | example-cvaccel |
| remote | none |
| roots | <repo>/examples/cvaccel |
| last_graph_build | 2026-09-25 07:47 (compile DB) |

## Profile
| Key | Value |
|---|---|
| code_paths | ['src', 'client/src'] |
| test_paths | ['tests'] |
| mock_paths | ['tests/mocks'] |
| framework | cpputest |
| framework_counts | {} |
| mock_style | CppUMock |
| build_system | cmake |
| build_cmd | cmake -S . -B build -DCMAKE_EXPORT_COMPILE_COMMANDS=ON -DBUILD_UNIT_TESTS=ON && cmake --build build -j |
| run_cmd | ctest --test-dir build --output-on-failure |
| clean_cmd | cmake --build build --target clean |
| compile_db | build/compile_commands.json |
| coverage_tool | Testwell CTC++ |
| env_setup | none |

## Commands (verified by running them)
| Purpose | Command | Verified on |
|---|---|---|
| build | `cmake -S . -B build -DCMAKE_EXPORT_COMPILE_COMMANDS=ON -DBUILD_UNIT_TESTS=ON && cmake --build build -j` | FAILED 2026-09-25 07:47 |
| run | `ctest --test-dir build --output-on-failure` | FAILED 2026-09-25 07:47 |
| clean | `cmake --build build --target clean` | FAILED 2026-09-25 07:47 |
| single_test | `build/tests/unit_tests -sg {group}` |  |
| compile_db | `build/compile_commands.json` | 2026-09-25 07:47 |
Paths written by build: build, build/tests
Summary line: 

## Conventions  (approved: 2026-09-25 07:03 (pilot: tests/cvclient_test.cpp))
- Framework: CppUTest (? files); mocks: CppUMock
- Test file names: 1  other: main.cpp; 1  <name>_test.<ext>
- Test names: 1  CamelCase
- Real examples: TEST(Smoke, HarnessBuilds)
- Asserts used (count name): 1  CHECK_TRUE
- CppUTest TEST_GROUP: 1
Exemplars: exemplars/test.md, exemplars/mock.md, exemplars/register.md

## Modules
| Module | File | Tests | Cards |
|---|---|---|---|
| cvclient.cpp | client/src/cvclient.cpp | none | modules/cvclient.cpp.cards.md |
| dispatcher.cpp | src/dispatcher.cpp | tests/dispatcher_test.cpp | modules/dispatcher.cpp.cards.md |
| memory_pool.cpp | src/memory_pool.cpp | tests/dispatcher_test.cpp, tests/memory_pool_test.cpp, tests/service_test.cpp | modules/memory_pool.cpp.cards.md |
| perf_monitor.cpp | src/perf_monitor.cpp | tests/cvclient_test.cpp, tests/dispatcher_test.cpp, tests/perf_monitor_test.cpp | modules/perf_monitor.cpp.cards.md |
| request_queue.cpp | src/request_queue.cpp | tests/dispatcher_test.cpp, tests/request_queue_test.cpp | modules/request_queue.cpp.cards.md |
| service.cpp | src/service.cpp | tests/service_test.cpp | modules/service.cpp.cards.md |
| session_manager.cpp | src/session_manager.cpp | tests/dispatcher_test.cpp, tests/session_manager_test.cpp | modules/session_manager.cpp.cards.md |

## Build notes and glossary (notes.md)
(none yet)
