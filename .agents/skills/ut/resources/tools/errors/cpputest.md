# CppUTest + CppUMock — quick reference: errors and fixes
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
