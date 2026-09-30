# Change impact: which code changes break which tests, and how

Condensed from a study that made 46 changes, one at a time, to a C++17 CppUTest codebase (7 production files, 215 tests,
hand-written fakes, plus a `--wrap` + CppUMock stub binary and a small C module). Each change was made the way a developer
would: production code and its callers updated until it compiled, tests left untouched. Then the tests were built and run.
Every row was run, none is a guess. The IDs (B2, T9, W3, ...) are the ones `hazards.py` and `wrapcheck.py` print.

Use it to decide, for a diff, what will break, what will stay silent, and what the task must check or add.

## Summary

| Caught by | Scenarios |
|---|---|
| 🟥 compiler | 15: G2, G4, G5, G6, G7, V1, V3, V4, V5, T2, T4, K1, H1, H2, X2 |
| 🟧 linker | 4: H3, W2, W4, W5 |
| 🟨 tests | 13: B2, B3, B4, B6, B7, G9, T3, T9, W1, W3, W6, X1, X3 |
| 🟪 crash | 1: T6 |
| ⬜ nothing | 13: B1, B5, B8, B9, G1, G3, G8, V2, T1, T5, T7, T8, K2 |

Main findings:
1. **Structural changes fail loudly, and clangd predicts them.** Signatures, interfaces, fields, constructors and namespaces all break the build (G2, G4–G7, V1, V3–V5, T2, T4, K1, H1, H2). clangd flagged the broken test files beforehand in all but two cases:
   - G7: three members were made private, and the prediction asked about only one of them;
   - H2: clangd returns no references for a namespace name, so a text search is needed.
   Most fixes are mechanical: a script can patch them and leave only value choices to a model.
2. **Behaviour changes are caught only by tests that pin the exact value.** For B2–B4, B6, B7, G9, T3, T6 and T9:
   - direct references found 19 of the 39 failing TESTs (0 of 16 in T9);
   - adding production callers found all 39, but flagged 34–127 of the 215 TESTs per change.
   The precise list is "TESTs that execute the changed lines", which needs coverage per test (a traced run).
3. **Silent changes cluster:**
   - new branches (B5: the change is reached, but only branch coverage shows the untested side);
   - interaction changes (B8 order, B9 wrong argument; B7 extra call is silent with the hand-written fakes and caught only by the strict wrap stubs);
   - widened, narrowed or unused types and constants (G3, T5, T7, T8, K2);
   - overload resolution silently moving to a new overload (G9).
   Diff coverage plus "changed symbol with no test reference" catch most of them; strict mocks catch the interaction ones.
4. **Hard-coded values in tests hide from static analysis** (T9: 16 failures, 0 references to `kMemAlign` in tests). Same-typed positional initialisers compile after a reorder and then fail confusingly (T3).
5. **Your `--wrap` + CppUMock stubs:**
   - A signature change of a wrapped C++ function gives a clear link error (W2), and so do both wrap-list mistakes (W4: flag without a stub, W5: stub without a flag). The stub file is invisible to clangd, so a prep script must regenerate or check wrappers from the declarations.
   - Moving a wrapped function inline bypasses the wrap silently (W3).
   - Adopting strict stubs in an existing binary fails 74 of 215 tests until those groups ignore the wrapped calls (W1).
   - In C, an unguarded stub turns a signature change into garbage values at run time (X1, X3). Declaring `__real_`/`__wrap_` with `__typeof__(fn)` turns it into a compile error at the stub line (X2).


## Function body

| # | Change | Caught by | What to do |
|---|---|---|---|
| B1 | **Refactor with identical behaviour**: RequestQueue::sizeTotal sums size(c) per core instead of iterating the deques | ⬜ nothing | Nothing to do. The prep script should report "impacted, still passing" and stop. |
| B2 | **Off-by-one in a tested boundary**: RequestQueue::enqueue: `q.size() >= kMaxQueuePerCore` becomes `>` (queue accepts one too many) | 🟨 tests | Run the impacted tests. A failing test that runs the changed line is a work item: "is the new behaviour intended? then update the expected value, else it is a bug". A weak model must not decide that alone. |
| B3 | **Off-by-one in a boundary nobody tests exactly**: MemoryPool::allocate: `gapEnd - cursor < reserved` becomes `<=` (an exactly fitting gap is refused) | 🟨 tests | Same as B2. Two of the failures are in service_test (the service tests exercise MemoryPool directly), found only through references. |
| B4 | **Different error code returned**: MemoryPool::release returns NOT_OWNER instead of INVALID_ARG for an unknown handle | 🟨 tests | Same as B2. Error-code changes break every test that pins the code, including tests of callers (service FreeMem). |
| B5 | **New branch (new validation)**: RequestQueue::enqueue rejects requests with bytes > kMaxJobBytes (new early return) | ⬜ nothing | Silent. The new branch is reached, but its reject side is never taken (branch coverage of the diff: 1 of 2). Only diff coverage produces the work item "add a test with bytes > kMaxJobBytes". |
| B6 | **Side effect removed**: Dispatcher::onCompletion no longer decrements the session's openRequests | 🟨 tests | Caught by the 2 tests that assert openRequests. Nothing flags a deleted side effect that no test asserts; diff coverage has no lines to measure for a deletion. |
| B7 | **Extra call to a collaborator**: Dispatcher::start calls pool_.physAddr() twice (a redundant "is it mapped" check) | 🟨 tests | Hand-written fakes that only count some calls stay silent. The strict CppUMock wrap caught it ("Unexpected additional (2nd) call"). Interaction changes are only visible to strict mocks. |
| B8 | **Call order changed**: Dispatcher::onCompletion records the perf record after the wake-up ioctl instead of before | ⬜ nothing | Silent in both binaries: neither the fakes nor CppUMock check order by default (CppUMock can: mock().strictOrder()). |
| B9 | **Wrong argument passed to a collaborator**: Dispatcher passes sizeof(info) - 1 as the payload size of every wake-up ioctl | ⬜ nothing | Silent: the fakes ignore the payload size. A stub that records every parameter (withParameter in the wrapper) plus one expectation would catch it. |

## Signature

| # | Change | Caught by | What to do |
|---|---|---|---|
| G1 | **Parameter added, with a default value**: RequestQueue::size(CoreType, bool includeRunning = false) | ⬜ nothing | Silent and harmless. The new parameter value (true) has no test: diff coverage shows the new code path, if any. |
| G2 | **Parameter added, no default (production callers updated)**: MemoryPool::release(MemHandle, SessionId, bool force); service.cpp passes false | 🟥 compiler | Compile errors in exactly the files clangd predicted. Mechanical fix: the prep script can patch every call (add the new argument) and hand a model only the choice of value. |
| G3 | **Type alias widened**: using SessionId = uint16_t becomes uint32_t | ⬜ nothing | Silent. A wider alias rarely breaks tests; the risk is in serialisation and packed structs, which these tests do not cover. |
| G4 | **Return type bool becomes an enum class**: RequestQueue::dequeue returns Status instead of bool; the dispatcher checks != Status::OK | 🟥 compiler | Compile errors only where a test negates the result (!dequeue). Mechanical fix (`!= Status::OK`). |
| G5 | **Function renamed (production callers updated)**: RequestQueue::sizeTotal becomes totalSize | 🟥 compiler | Compile errors; a rename is fully mechanical (clangd rename applies it to the tests). |
| G6 | **Function removed (only tests used it)**: MemoryPool::largestFree deleted | 🟥 compiler | Compile error in the only user, a test. Needs a human: delete the test, or keep the function? |
| G7 | **Test-only public helpers made private**: PerfMonitor::timestampsOk/bytesOk/coreBytesOk ("exposed for testing") moved to private: | 🟥 compiler | Compile errors: tests used "exposed for testing" members. This is a test-seam decision (access), not a code fix; follow the project's recorded seam. |
| G8 | **Overload added that makes calls ambiguous**: MemoryPool gains bytesInUse(uint32_t tag) next to bytesInUse(SessionId) | ⬜ nothing | Silent: no call passes a type that makes the overloads ambiguous. Ambiguity only appears with literals of a third type. |
| G9 | **Overload added that tests silently switch to**: MemoryPool gains release(MemHandle, int legacyOwner) (a shim without the owner check); tests pass int literals | 🟨 tests | Silent at build; 1 test fails. Tests passing the int literal 1 now bind to the new overload (exact match beats the uint16_t conversion). Nothing warns. |

## Interface

| # | Change | Caught by | What to do |
|---|---|---|---|
| V1 | **Pure virtual method added**: IAccelBlock gains `virtual void reset() = 0;` | 🟥 compiler | Every fake becomes abstract: 99 errors in 3 test files. clangd "implementation" on the interface finds all the fakes (and the sim). Mechanical: add the method to each fake. |
| V2 | **Virtual method with a default body added**: IAccelBlock gains `virtual void reset() {}` | ⬜ nothing | Nothing breaks. The fakes do not override the new method, which may matter to a test later. |
| V3 | **const dropped from a pure virtual**: IDevice::nowNs() const becomes nowNs() | 🟥 compiler | The fakes' `override` stops matching: errors in every fake. Mechanical: follow the new signature. |
| V4 | **Parameter with default added to a pure virtual**: IAccelBlock::isBusy(CoreType, bool strict = false) | 🟥 compiler | Same as V3 (a default argument does not keep overrides valid). |
| V5 | **Return type of a pure virtual changed**: IDevice::nowNs returns int64_t instead of TimeNs (uint64_t) | 🟥 compiler | "conflicting return type" in every fake. Mechanical. |

## Type

| # | Change | Caught by | What to do |
|---|---|---|---|
| T1 | **Field added at the end of a struct (with initializer)**: Request gains `uint32_t flags = 0;` | ⬜ nothing | Nothing (the new field has an initializer). |
| T2 | **Field inserted in the middle of a struct built with {...}**: hw::JobResult gains `CoreType core;` between jobId and status | 🟥 compiler | Positional `{999, Status::OK, 0}` initialisers stop compiling where the types differ. Mechanical, but the value for the new field is a choice. |
| T3 | **Fields of the same type reordered**: hw::JobResult becomes { hwCycles, status, jobId } (both ends are uint32_t) | 🟨 tests | Compiles (same types), then 6 tests fail with misleading messages (unknown job, wrong counts). Positional initialisation of same-typed fields is a trap: prefer designated initialisers in tests. |
| T4 | **Field renamed (production updated)**: SessionInfo::openRequests becomes pendingRequests | 🟥 compiler | Compile errors with a "did you mean pendingRequests" hint. Mechanical rename. |
| T5 | **Field narrowed**: CompletionInfo::latencyNs TimeNs (64 bit) becomes uint32_t | ⬜ nothing | Silent: no test reads latencyNs at all (clangd: 0 test references). The prep script can flag "changed field, no test references it". |

## Enum

| # | Change | Caught by | What to do |
|---|---|---|---|
| T6 | **Enumerator inserted in the middle (values shift), count updated**: CoreType gains CROP = 1 (CONVOLVE..MATCH shift by one), kCoreCount 5 -> 6 | 🟪 crash | 3 test failures, then a crash: `kCoreNames` is a std::array sized kCoreCount with 5 initializers, so the 6th name is nullptr and report() dereferences it. Tests using `static_cast<CoreType>(5)` as "invalid core" silently became valid-core tests. |
| T7 | **Enumerator added at the end**: Priority gains CRITICAL = 4 | ⬜ nothing | Nothing: no switch over Priority without default, no table sized by it. |

## Constant

| # | Change | Caught by | What to do |
|---|---|---|---|
| T8 | **Constant changed; tests use the constant**: kMaxQueuePerCore 32 -> 16 | ⬜ nothing | All pass, but 112 fewer checks ran: the tests loop up to the constant and adapted. Comments saying "32" are now stale. |
| T9 | **Constant changed; tests hard-code its value**: kMemAlign 64 -> 128 | 🟨 tests | 16 failures: the tests hard-code 64 and 128 instead of kMemAlign. clangd predicted no test (no reference to the constant); only transitive callers of allocate() or a test run finds them. |

## Construction

| # | Change | Caught by | What to do |
|---|---|---|---|
| K1 | **Constructor parameter added (production updated)**: Dispatcher(..., unsigned maxInFlight); CvAccelService passes 64 | 🟥 compiler | Every fixture that builds a Dispatcher fails to compile (clangd predicted exactly those files). Mechanical: pass the new argument. |
| K2 | **Default constructor argument changed**: MemoryPool(size_t poolBytes = kPoolBytes ...) default becomes 4096 (production passes it explicitly) | ⬜ nothing | Silent: every test passes an explicit size or allocates little. |

## Header

| # | Change | Caught by | What to do |
|---|---|---|---|
| H1 | **Header stops including what tests relied on**: dispatcher.hpp forward-declares SessionManager and PerfMonitor instead of including their headers | 🟥 compiler | 78 errors in the one test that got SessionManager/PerfMonitor through dispatcher.hpp. References do not show this; the include graph does. Mechanical: add the includes. |
| H2 | **Namespace renamed (production updated)**: cvaccel::hw becomes cvaccel::hwif | 🟥 compiler | 177 errors. Mechanical rename. clangd references on a namespace name returned nothing: a text search is needed here. |

## Build

| # | Change | Caught by | What to do |
|---|---|---|---|
| H3 | **Function moved to a new source file**: PerfMonitor::report moved from perf_monitor.cpp to new src/perf_report.cpp (the app build globs src/*.cpp; the test build lists files) | 🟧 linker | Link error only in the test binary: the app build globs src/*.cpp, the unit-test build lists its sources. The prep script should compare new source files with the test source list. |

## Wrap stubs

| # | Change | Caught by | What to do |
|---|---|---|---|
| W1 | **Strict wrap stubs linked into the existing test binary**: tests/CMakeLists.txt: unit_tests also links cvaccel_wrap_stubs.cpp with `--wrap` for record() and physAddr() | 🟨 tests | 74 of 215 existing tests fail with "Unexpected call": strict stubs change every test in the binary that reaches a wrapped function. Adopt them per binary, or give existing groups ignoreOtherCalls() in setup(). |
| W2 | **Wrapped C++ function gets a defaulted parameter (mangled name changes)**: MemoryPool::physAddr(MemHandle, bool strict = false) const | 🟧 linker | Link error naming the OLD signature (the stub and the --wrap list still use the old mangled name). clangd did not flag the stub file: mangled extern "C" names are invisible to it. Regenerate wrappers from declarations. |
| W3 | **Wrapped function moved inline into its header**: MemoryPool::physAddr defined in memory_pool.hpp (inline) instead of memory_pool.cpp | 🟨 tests | Silent bypass: the call is compiled inline in the caller's object, so `--wrap` never sees it. The mocked test gets the real value. Check that every wrapped function is defined out of line, in another object than its callers. |
| W4 | **Function added to the --wrap list, stub not written**: UT_WRAPPED gains MemoryPool::find (mangled); no `__wrap_` function exists | 🟧 linker | Clear link error (undefined `__wrap_...`). The prep script can check the wrap list against the stub file before building. |
| W5 | **Stub exists, --wrap flag dropped**: UT_WRAPPED loses physAddr (the stub still defines `__wrap_...physAddr`) | 🟧 linker | Clear link error (undefined `__real_...`), because `__real_` only exists with `--wrap`. Good: this mistake cannot pass silently. |
| W6 | **Production stops calling the wrapped function**: Dispatcher::start computes the physical address from pool_.find() instead of pool_.physAddr() | 🟨 tests | The test that mocked physAddr fails (its value is not used and its expectation is not met). Strict expectations catch removed calls. |

## Wrap stubs (C)

| # | Change | Caught by | What to do |
|---|---|---|---|
| X1 | **C function gets a new parameter; stub declares its own `__real_` prototype**: `hal_read(int reg)` becomes `hal_read(int reg, int bank)`; sensor.c updated; the stub is not | 🟨 tests | Compiles and links; 2 of 3 tests fail with garbage values: the stub still calls `__real_hal_read(reg)` without `bank`, so the real function reads an undefined register. Silent ABI mismatch. |
| X2 | **Same change; stub declares `__real_`/`__wrap_` with `__typeof__(hal_read)`**: as X1, but the stub file uses `extern "C" __typeof__(hal_read) __real_hal_read, __wrap_hal_read;` | 🟥 compiler | The same change with `__typeof__(hal_read)` declarations in the stub: a compile error in the stub, at the exact line. Use this guard in every C stub. |
| X3 | **C function return type changed; stub not updated (no guard)**: int hal_read(int) becomes double hal_read(int) (sensor.c updated, the stub is not) | 🟨 tests | Compiles and links; the mocked test fails (the wrapper returns an int where the caller reads a double register), the real-path tests pass by accident. |

## What a diff task must do, per change kind

| Change kind (from the git diff) | How it shows up | Detection before the build | Work item for the model |
|---|---|---|---|
| Signature, rename, removed or private member, ctor parameter, namespace | compile errors | clangd references (files exact in this study) | Mostly a script patch; the model chooses values only (G2, K1, T2) |
| Pure virtual added or changed | compile errors in every fake | clangd `implementation` on the interface | Script adds or updates the override in each fake |
| Body: boundary, error code, removed side effect | failing tests | TESTs that execute the changed lines (coverage per test), or references + callers (over-flags) | "Intended or bug?" per failing test; never auto-update an expected value |
| Body: new branch or validation | silent | branch coverage of the diff | "Add a test that takes <condition> at <file:line>" |
| Interaction: extra, missing or reordered call, argument | silent with fakes; strict mocks catch count and arguments | diff shows calls added or removed | Update expectations; stubs should record all parameters |
| Type width, constant, enum, default argument | often silent; crashes where a table is sized by a count (T6) | changed symbol has 0 or few test references; grep for literals equal to the old value (T9) | Review item listing tests that hard-code the old value |
| Header includes, new source file | compile errors (H1) or a test-only link error (H3) | include graph; new file vs the test source list | Script patch |
| Wrapped function: signature, inline, wrap list | link errors (W2, W4, W5) or a silent bypass (W3) | compare declarations, `nm` symbols and the wrap list; clangd does not see mangled stubs | Regenerate the wrapper; for C, `__typeof__` guards |
