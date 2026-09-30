# Change-impact study: one change at a time on the cvaccel toy codebase

Each row is one kind of change made the way a developer would make it: production code, including its call sites, is updated until it compiles, and the tests are left untouched. Then the unit tests are built and run, and the results are recorded. Every scenario was actually run; nothing below is a guess.

**Setup**:
- `examples/cvaccel`: C++17, 7 production files, 215 CppUTest tests with hand-written fakes of the `IAccelBlock` / `IDevice` interfaces.
- A second test binary, `unit_tests_wrap`, uses your shared-stub pattern: `--wrap` plus CppUMock with passthrough to `__real_`, on `PerfMonitor::record` and `MemoryPool::physAddr` by their mangled names.
- A tiny C module (`hal_read` / `sensor_get`) shows the same pattern for C functions (X1–X3).
- GCC 13, GNU ld, Ninja, gcov, clangd 22. The script is `study.py`; raw results are in `results/`.

**Columns**:
- **Caught by**: the first thing that noticed the change.
- **Change reached by tests**: changed production lines (and their branches) executed by any test (gcov).
- **clangd before the change**: what a prep script would have flagged from references and implementations of the changed symbol, taken before the edit, against what actually broke. "direct" means TEST blocks that reference the symbol; "incl. callers" adds TEST blocks that reach it through up to 2 levels of production callers.

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

| # | Change | Caught by | What happened | Change reached by tests | clangd before the change | What the prep script / agent must do |
|---|---|---|---|---|---|---|
| B1 | **Refactor with identical behaviour**<br>RequestQueue::sizeTotal sums size(c) per core instead of iterating the deques | ⬜ nothing | builds, all tests pass | 1/1 lines, 2/2 branches | nothing failed; 3 TESTs would have been flagged | Nothing to do. The prep script should report "impacted, still passing" and stop. |
| B2 | **Off-by-one in a tested boundary**<br>RequestQueue::enqueue: `q.size() >= kMaxQueuePerCore` becomes `>` (queue accepts one too many) | 🟨 tests | 3 failing test(s)<br>`TEST(RequestQueueEnqueue, Enqueue_L18QueueAtMaxSize_ReturnsQueueFull)`<br>`TEST(CvAccelService, Submit_L118StNotOk_ReturnsSt)`<br>`TEST(RequestQueue, Enqueue_QueueSizeAtMax_ReturnsQueueFull)` | 1/1 lines, 1/2 branches | TESTs: 2/3 direct, 3/3 incl. callers (flagged 63 + 64) | Run the impacted tests. A failing test that runs the changed line is a work item: "is the new behaviour intended? then update the expected value, else it is a bug". A weak model must not decide that alone. |
| B3 | **Off-by-one in a boundary nobody tests exactly**<br>MemoryPool::allocate: `gapEnd - cursor < reserved` becomes `<=` (an exactly fitting gap is refused) | 🟨 tests | 4 failing test(s)<br>`TEST(CvAccelService, MemoryPoolAllocate_GapAtStartFits_PlacesBeforeFirstBlock)`<br>`TEST(CvAccelService, MemoryPoolAllocate_GapBetweenBlocksFits_ReusesGap)`<br>`TEST(MemoryPool, Allocate_GapAtStartFits_PlacesBeforeFirstBlock)`<br>`TEST(MemoryPool, Allocate_GapBetweenBlocksFits_ReusesGap)` | 1/1 lines, 2/2 branches | TESTs: 4/4 direct, 4/4 incl. callers (flagged 45 + 61) | Same as B2. Two of the failures are in service_test (the service tests exercise MemoryPool directly), found only through references. |
| B4 | **Different error code returned**<br>MemoryPool::release returns NOT_OWNER instead of INVALID_ARG for an unknown handle | 🟨 tests | 3 failing test(s)<br>`TEST(CvAccelService, FreeMem_L80BlkFalse_ReturnsInvalidArg)`<br>`TEST(MemoryPool, Release_HandleNotFound_ReturnsInvalidArg)`<br>`TEST(MemoryPool, Release_EmptyPool_ReturnsInvalidArg)` | 1/1 lines | TESTs: 2/3 direct, 3/3 incl. callers (flagged 13 + 62) | Same as B2. Error-code changes break every test that pins the code, including tests of callers (service FreeMem). |
| B5 | **New branch (new validation)**<br>RequestQueue::enqueue rejects requests with bytes > kMaxJobBytes (new early return) | ⬜ nothing | builds, all tests pass | 1/1 lines, 1/2 branches | nothing failed; 127 TESTs would have been flagged | Silent. The new branch is reached, but its reject side is never taken (branch coverage of the diff: 1 of 2). Only diff coverage produces the work item "add a test with bytes > kMaxJobBytes". |
| B6 | **Side effect removed**<br>Dispatcher::onCompletion no longer decrements the session's openRequests | 🟨 tests | 2 failing test(s)<br>`TEST(CvAccelService, OnHwCompletion_TypicalCompletion_RecordsAndWakesClient)`<br>`TEST(Dispatcher, OnCompletion_L107_SessionFoundWithOpenRequests_DecrementsOpenRequests)` | - | TESTs: 1/2 direct, 2/2 incl. callers (flagged 10 + 62) | Caught by the 2 tests that assert openRequests. Nothing flags a deleted side effect that no test asserts; diff coverage has no lines to measure for a deletion. |
| B7 | **Extra call to a collaborator**<br>Dispatcher::start calls pool_.physAddr() twice (a redundant "is it mapped" check) | 🟨 tests | 1 failing test(s)<br>`TEST(DispatcherWrap, Start_UsesPhysAddrOfHandle_Mocked)` | 1/1 lines, 4/4 branches | TESTs: 0/1 direct, 1/1 incl. callers (flagged 0 + 34) | Hand-written fakes that only count some calls stay silent. The strict CppUMock wrap caught it ("Unexpected additional (2nd) call"). Interaction changes are only visible to strict mocks. |
| B8 | **Call order changed**<br>Dispatcher::onCompletion records the perf record after the wake-up ioctl instead of before | ⬜ nothing | builds, all tests pass | 2/2 lines, 1/1 branches | nothing failed; 72 TESTs would have been flagged | Silent in both binaries: neither the fakes nor CppUMock check order by default (CppUMock can: mock().strictOrder()). |
| B9 | **Wrong argument passed to a collaborator**<br>Dispatcher passes sizeof(info) - 1 as the payload size of every wake-up ioctl | ⬜ nothing | builds, all tests pass | 3/3 lines, 3/3 branches | nothing failed; 41 TESTs would have been flagged | Silent: the fakes ignore the payload size. A stub that records every parameter (withParameter in the wrapper) plus one expectation would catch it. |

## Signature

| # | Change | Caught by | What happened | Change reached by tests | clangd before the change | What the prep script / agent must do |
|---|---|---|---|---|---|---|
| G1 | **Parameter added, with a default value**<br>RequestQueue::size(CoreType, bool includeRunning = false) | ⬜ nothing | builds, all tests pass | 1/1 lines | nothing failed; 16 TESTs would have been flagged | Silent and harmless. The new parameter value (true) has no test: diff coverage shows the new code path, if any. |
| G2 | **Parameter added, no default (production callers updated)**<br>MemoryPool::release(MemHandle, SessionId, bool force); service.cpp passes false | 🟥 compiler | 13 compile error(s) in 2 file(s): `memory_pool_test.cpp` (10), `service_test.cpp` (3) | 0/2 lines | files: 2/2 predicted | Compile errors in exactly the files clangd predicted. Mechanical fix: the prep script can patch every call (add the new argument) and hand a model only the choice of value. |
| G3 | **Type alias widened**<br>using SessionId = uint16_t becomes uint32_t | ⬜ nothing | builds, all tests pass | - | nothing failed; 168 TESTs would have been flagged | Silent. A wider alias rarely breaks tests; the risk is in serialisation and packed structs, which these tests do not cover. |
| G4 | **Return type bool becomes an enum class**<br>RequestQueue::dequeue returns Status instead of bool; the dispatcher checks != Status::OK | 🟥 compiler | 2 compile error(s) in 1 file(s): `request_queue_test.cpp` (2) | 5/5 lines, 6/7 branches | files: 1/1 predicted (+1 extra) | Compile errors only where a test negates the result (!dequeue). Mechanical fix (`!= Status::OK`). |
| G5 | **Function renamed (production callers updated)**<br>RequestQueue::sizeTotal becomes totalSize | 🟥 compiler | 2 compile error(s) in 2 file(s): `request_queue_test.cpp` (1), `dispatcher_test.cpp` (1) | 0/2 lines, 0/1 branches | files: 2/2 predicted | Compile errors; a rename is fully mechanical (clangd rename applies it to the tests). |
| G6 | **Function removed (only tests used it)**<br>MemoryPool::largestFree deleted | 🟥 compiler | 1 compile error(s) in 1 file(s): `memory_pool_test.cpp` (1) | 0/1 lines | files: 1/1 predicted | Compile error in the only user, a test. Needs a human: delete the test, or keep the function? |
| G7 | **Test-only public helpers made private**<br>PerfMonitor::timestampsOk/bytesOk/coreBytesOk ("exposed for testing") moved to private: | 🟥 compiler | 4 compile error(s) in 2 file(s): `perf_monitor_test.cpp` (3), `service_test.cpp` (1) | - | files: 1/2 predicted | Compile errors: tests used "exposed for testing" members. This is a test-seam decision (access), not a code fix; follow the project's recorded seam. |
| G8 | **Overload added that makes calls ambiguous**<br>MemoryPool gains bytesInUse(uint32_t tag) next to bytesInUse(SessionId) | ⬜ nothing | builds, all tests pass | 0/1 lines | nothing failed; 0 TESTs would have been flagged | Silent: no call passes a type that makes the overloads ambiguous. Ambiguity only appears with literals of a third type. |
| G9 | **Overload added that tests silently switch to**<br>MemoryPool gains release(MemHandle, int legacyOwner) (a shim without the owner check); tests pass int literals | 🟨 tests | 1 failing test(s)<br>`TEST(MemoryPool, Release_OwnerMismatch_ReturnsNotOwner)` | 1/1 lines, 5/5 branches | TESTs: 1/1 direct, 1/1 incl. callers (flagged 13 + 62) | Silent at build; 1 test fails. Tests passing the int literal 1 now bind to the new overload (exact match beats the uint16_t conversion). Nothing warns. |

## Interface

| # | Change | Caught by | What happened | Change reached by tests | clangd before the change | What the prep script / agent must do |
|---|---|---|---|---|---|---|
| V1 | **Pure virtual method added**<br>IAccelBlock gains `virtual void reset() = 0;` | 🟥 compiler | 99 compile error(s) in 3 file(s): `service_test.cpp` (62), `dispatcher_test.cpp` (36), `dispatcher_wrap_test.cpp` (1) | - | files: 3/3 predicted | Every fake becomes abstract: 99 errors in 3 test files. clangd "implementation" on the interface finds all the fakes (and the sim). Mechanical: add the method to each fake. |
| V2 | **Virtual method with a default body added**<br>IAccelBlock gains `virtual void reset() {}` | ⬜ nothing | builds, all tests pass | - | nothing failed; 101 TESTs would have been flagged | Nothing breaks. The fakes do not override the new method, which may matter to a test later. |
| V3 | **const dropped from a pure virtual**<br>IDevice::nowNs() const becomes nowNs() | 🟥 compiler | 102 compile error(s) in 3 file(s): `service_test.cpp` (63), `dispatcher_test.cpp` (37), `dispatcher_wrap_test.cpp` (2) | - | files: 3/3 predicted | The fakes' `override` stops matching: errors in every fake. Mechanical: follow the new signature. |
| V4 | **Parameter with default added to a pure virtual**<br>IAccelBlock::isBusy(CoreType, bool strict = false) | 🟥 compiler | 102 compile error(s) in 3 file(s): `service_test.cpp` (63), `dispatcher_test.cpp` (37), `dispatcher_wrap_test.cpp` (2) | - | files: 3/3 predicted | Same as V3 (a default argument does not keep overrides valid). |
| V5 | **Return type of a pure virtual changed**<br>IDevice::nowNs returns int64_t instead of TimeNs (uint64_t) | 🟥 compiler | 3 compile error(s) in 3 file(s): `dispatcher_test.cpp` (1), `service_test.cpp` (1), `dispatcher_wrap_test.cpp` (1) | - | files: 3/3 predicted | "conflicting return type" in every fake. Mechanical. |

## Type

| # | Change | Caught by | What happened | Change reached by tests | clangd before the change | What the prep script / agent must do |
|---|---|---|---|---|---|---|
| T1 | **Field added at the end of a struct (with initializer)**<br>Request gains `uint32_t flags = 0;` | ⬜ nothing | builds, all tests pass | - | nothing failed; 132 TESTs would have been flagged | Nothing (the new field has an initializer). |
| T2 | **Field inserted in the middle of a struct built with {...}**<br>hw::JobResult gains `CoreType core;` between jobId and status | 🟥 compiler | 10 compile error(s) in 2 file(s): `dispatcher_test.cpp` (9), `dispatcher_wrap_test.cpp` (1) | - | files: 2/2 predicted (+1 extra) | Positional `{999, Status::OK, 0}` initialisers stop compiling where the types differ. Mechanical, but the value for the new field is a choice. |
| T3 | **Fields of the same type reordered**<br>hw::JobResult becomes { hwCycles, status, jobId } (both ends are uint32_t) | 🟨 tests | 6 failing test(s)<br>`TEST(Dispatcher, CancelSession_L150_RunningJobDifferentSession_ClientFdUnaffected)`<br>`TEST(Dispatcher, OnCompletion_L111_ClientFdSet_WakesClient)`<br>`TEST(Dispatcher, OnCompletion_L107_SessionNotFound_StillErasesRunningAndReturnsOk)`<br>`TEST(Dispatcher, OnCompletion_L107_SessionFoundWithOpenRequests_DecrementsOpenRequests)`<br>… +2 | - | TESTs: 6/6 direct, 6/6 incl. callers (flagged 11 + 61) | Compiles (same types), then 6 tests fail with misleading messages (unknown job, wrong counts). Positional initialisation of same-typed fields is a trap: prefer designated initialisers in tests. |
| T4 | **Field renamed (production updated)**<br>SessionInfo::openRequests becomes pendingRequests | 🟥 compiler | 10 compile error(s) in 3 file(s): `dispatcher_test.cpp` (7), `service_test.cpp` (2), `session_manager_test.cpp` (1) | 2/5 lines, 2/15 branches | files: 3/3 predicted | Compile errors with a "did you mean pendingRequests" hint. Mechanical rename. |
| T5 | **Field narrowed**<br>CompletionInfo::latencyNs TimeNs (64 bit) becomes uint32_t | ⬜ nothing | builds, all tests pass | - | nothing failed; 42 TESTs would have been flagged | Silent: no test reads latencyNs at all (clangd: 0 test references). The prep script can flag "changed field, no test references it". |

## Enum

| # | Change | Caught by | What happened | Change reached by tests | clangd before the change | What the prep script / agent must do |
|---|---|---|---|---|---|---|
| T6 | **Enumerator inserted in the middle (values shift), count updated**<br>CoreType gains CROP = 1 (CONVOLVE..MATCH shift by one), kCoreCount 5 -> 6 | 🟪 crash | 3 failing test(s), then a crash<br>`TEST(RequestQueueEnqueue, Enqueue_L16CoreIdxAtOrAboveCoreCount_ReturnsInvalidArg)`<br>`TEST(CvAccelService, PerfMonitorRecord_CoreIndexOutOfRange_SkipsPerCoreAccumulation)`<br>`TEST(RequestQueue, Enqueue_CoreIdxGreaterOrEqualCoreCount_ReturnsInvalidArg)` | - | TESTs: 3/3 direct, 3/3 incl. callers (flagged 74 + 26) | 3 test failures, then a crash: `kCoreNames` is a std::array sized kCoreCount with 5 initializers, so the 6th name is nullptr and report() dereferences it. Tests using `static_cast<CoreType>(5)` as "invalid core" silently became valid-core tests. |
| T7 | **Enumerator added at the end**<br>Priority gains CRITICAL = 4 | ⬜ nothing | builds, all tests pass | - | nothing failed; 128 TESTs would have been flagged | Nothing: no switch over Priority without default, no table sized by it. |

## Constant

| # | Change | Caught by | What happened | Change reached by tests | clangd before the change | What the prep script / agent must do |
|---|---|---|---|---|---|---|
| T8 | **Constant changed; tests use the constant**<br>kMaxQueuePerCore 32 -> 16 | ⬜ nothing | builds, all tests pass | - | nothing failed; 66 TESTs would have been flagged | All pass, but 112 fewer checks ran: the tests loop up to the constant and adapted. Comments saying "32" are now stale. |
| T9 | **Constant changed; tests hard-code its value**<br>kMemAlign 64 -> 128 | 🟨 tests | 16 failing test(s)<br>`TEST(CvAccelService, MemoryPoolAllocate_RemainingSpaceTooSmall_ReturnsNoMemory)`<br>`TEST(CvAccelService, MemoryPoolAllocate_NoFittingGapAmongBlocks_PlacesAfterLast)`<br>`TEST(CvAccelService, MemoryPoolAllocate_GapBetweenBlocksTooSmall_SkipsGap)`<br>`TEST(CvAccelService, MemoryPoolAllocate_GapBetweenBlocksFits_ReusesGap)`<br>… +12 | - | TESTs: 0/16 direct, 16/16 incl. callers (flagged 0 + 45) | 16 failures: the tests hard-code 64 and 128 instead of kMemAlign. clangd predicted no test (no reference to the constant); only transitive callers of allocate() or a test run finds them. |

## Construction

| # | Change | Caught by | What happened | Change reached by tests | clangd before the change | What the prep script / agent must do |
|---|---|---|---|---|---|---|
| K1 | **Constructor parameter added (production updated)**<br>Dispatcher(..., unsigned maxInFlight); CvAccelService passes 64 | 🟥 compiler | 39 compile error(s) in 2 file(s): `dispatcher_test.cpp` (36), `dispatcher_wrap_test.cpp` (3) | - | files: 2/2 predicted | Every fixture that builds a Dispatcher fails to compile (clangd predicted exactly those files). Mechanical: pass the new argument. |
| K2 | **Default constructor argument changed**<br>MemoryPool(size_t poolBytes = kPoolBytes ...) default becomes 4096 (production passes it explicitly) | ⬜ nothing | builds, all tests pass | - | nothing failed; 143 TESTs would have been flagged | Silent: every test passes an explicit size or allocates little. |

## Header

| # | Change | Caught by | What happened | Change reached by tests | clangd before the change | What the prep script / agent must do |
|---|---|---|---|---|---|---|
| H1 | **Header stops including what tests relied on**<br>dispatcher.hpp forward-declares SessionManager and PerfMonitor instead of including their headers | 🟥 compiler | 78 compile error(s) in 1 file(s): `dispatcher_test.cpp` (78) | - | files: 1/1 predicted (+1 extra) | 78 errors in the one test that got SessionManager/PerfMonitor through dispatcher.hpp. References do not show this; the include graph does. Mechanical: add the includes. |
| H2 | **Namespace renamed (production updated)**<br>cvaccel::hw becomes cvaccel::hwif | 🟥 compiler | 177 compile error(s) in 3 file(s): `service_test.cpp` (85), `dispatcher_test.cpp` (75), `dispatcher_wrap_test.cpp` (17) | - | files: 0/3 predicted | 177 errors. Mechanical rename. clangd references on a namespace name returned nothing: a text search is needed here. |

## Build

| # | Change | Caught by | What happened | Change reached by tests | clangd before the change | What the prep script / agent must do |
|---|---|---|---|---|---|---|
| H3 | **Function moved to a new source file**<br>PerfMonitor::report moved from perf_monitor.cpp to new src/perf_report.cpp (the app build globs src/*.cpp; the test build lists files) | 🟧 linker | link error<br>`undefined reference to `cvaccel::PerfMonitor::report[abi:cxx11]() const'` | 0/1 lines | files: none to predict (link step) | Link error only in the test binary: the app build globs src/*.cpp, the unit-test build lists its sources. The prep script should compare new source files with the test source list. |

## Wrap stubs

| # | Change | Caught by | What happened | Change reached by tests | clangd before the change | What the prep script / agent must do |
|---|---|---|---|---|---|---|
| W1 | **Strict wrap stubs linked into the existing test binary**<br>tests/CMakeLists.txt: unit_tests also links cvaccel_wrap_stubs.cpp with `--wrap` for record() and physAddr() | 🟨 tests | 74 failing test(s)<br>`TEST(CvAccelService, PerfMonitorRecord_IntegrityNotOk_ReturnsIntegrity)`<br>`TEST(CvAccelService, PerfMonitorRecord_IntegrityOk_ReturnsOk)`<br>`TEST(CvAccelService, PerfMonitorRecord_CoreIndexOutOfRange_SkipsPerCoreAccumulation)`<br>`TEST(CvAccelService, PerfMonitorRecord_CoreIndexWithinRange_AccumulatesPerCoreStats)`<br>… +70 | - | TESTs: 20/74 direct, 48/74 incl. callers (flagged 20 + 35) | 74 of 215 existing tests fail with "Unexpected call": strict stubs change every test in the binary that reaches a wrapped function. Adopt them per binary, or give existing groups ignoreOtherCalls() in setup(). |
| W2 | **Wrapped C++ function gets a defaulted parameter (mangled name changes)**<br>MemoryPool::physAddr(MemHandle, bool strict = false) const | 🟧 linker | link error<br>`undefined reference to `cvaccel::MemoryPool::physAddr(unsigned int) const'` | 1/1 lines | files: none to predict (link step) | Link error naming the OLD signature (the stub and the --wrap list still use the old mangled name). clangd did not flag the stub file: mangled extern "C" names are invisible to it. Regenerate wrappers from declarations. |
| W3 | **Wrapped function moved inline into its header**<br>MemoryPool::physAddr defined in memory_pool.hpp (inline) instead of memory_pool.cpp | 🟨 tests | 1 failing test(s)<br>`TEST(DispatcherWrap, Start_UsesPhysAddrOfHandle_Mocked)` | - | TESTs: 0/1 direct, 1/1 incl. callers (flagged 17 + 32) | Silent bypass: the call is compiled inline in the caller's object, so `--wrap` never sees it. The mocked test gets the real value. Check that every wrapped function is defined out of line, in another object than its callers. |
| W4 | **Function added to the --wrap list, stub not written**<br>UT_WRAPPED gains MemoryPool::find (mangled); no `__wrap_` function exists | 🟧 linker | link error<br>`undefined reference to `__wrap__ZNK7cvaccel10MemoryPool4findEj'` | - | files: none to predict (link step) | Clear link error (undefined `__wrap_...`). The prep script can check the wrap list against the stub file before building. |
| W5 | **Stub exists, --wrap flag dropped**<br>UT_WRAPPED loses physAddr (the stub still defines `__wrap_...physAddr`) | 🟧 linker | link error<br>`undefined reference to `__real__ZNK7cvaccel10MemoryPool8physAddrEj'` | - | files: none to predict (link step) | Clear link error (undefined `__real_...`), because `__real_` only exists with `--wrap`. Good: this mistake cannot pass silently. |
| W6 | **Production stops calling the wrapped function**<br>Dispatcher::start computes the physical address from pool_.find() instead of pool_.physAddr() | 🟨 tests | 1 failing test(s)<br>`TEST(DispatcherWrap, Start_UsesPhysAddrOfHandle_Mocked)` | 1/1 lines, 4/4 branches | TESTs: 0/1 direct, 1/1 incl. callers (flagged 0 + 34) | The test that mocked physAddr fails (its value is not used and its expectation is not met). Strict expectations catch removed calls. |

## Wrap stubs (C)

| # | Change | Caught by | What happened | Change reached by tests | clangd before the change | What the prep script / agent must do |
|---|---|---|---|---|---|---|
| X1 | **C function gets a new parameter; stub declares its own `__real_` prototype**<br>`hal_read(int reg)` becomes `hal_read(int reg, int bank)`; sensor.c updated; the stub is not | 🟨 tests | 2 failing test(s)<br>`TEST(Sensor, Real)`<br>`TEST(Sensor, Spy)` | - | n/a (not in the clangd index) | Compiles and links; 2 of 3 tests fail with garbage values: the stub still calls `__real_hal_read(reg)` without `bank`, so the real function reads an undefined register. Silent ABI mismatch. |
| X2 | **Same change; stub declares `__real_`/`__wrap_` with `__typeof__(hal_read)`**<br>as X1, but the stub file uses `extern "C" __typeof__(hal_read) __real_hal_read, __wrap_hal_read;` | 🟥 compiler | 2 compile error(s) in 1 file(s): `hal_wrap_stubs.cpp` (2) | - | n/a (not in the clangd index) | The same change with `__typeof__(hal_read)` declarations in the stub: a compile error in the stub, at the exact line. Use this guard in every C stub. |
| X3 | **C function return type changed; stub not updated (no guard)**<br>int hal_read(int) becomes double hal_read(int) (sensor.c updated, the stub is not) | 🟨 tests | 1 failing test(s)<br>`TEST(Sensor, Mocked)` | - | n/a (not in the clangd index) | Compiles and links; the mocked test fails (the wrapper returns an int where the caller reads a double register), the real-path tests pass by accident. |

## What this means for the prep script

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

## Details per scenario

<details><summary><b>B1</b> Refactor with identical behaviour (⬜ nothing)</summary>

```diff
diff --git a/src/request_queue.cpp b/src/request_queue.cpp
--- a/src/request_queue.cpp
+++ b/src/request_queue.cpp
@@ -51,7 +51,7 @@ unsigned RequestQueue::size(CoreType core) const {
 
 unsigned RequestQueue::sizeTotal() const {
     unsigned total = 0;
-    for (const auto& q : queues_) total += static_cast<unsigned>(q.size());
+    for (unsigned c = 0; c < kCoreCount; ++c) total += size(static_cast<CoreType>(c));
     return total;
 }
 
```
`unit_tests`: OK (215 tests, 215 ran, 926 checks, 0 ignored, 0 filtered out, 2 ms)
`unit_tests_wrap`: OK (3 tests, 3 ran, 18 checks, 0 ignored, 0 filtered out, 0 ms)

</details>

<details><summary><b>B2</b> Off-by-one in a tested boundary (🟨 tests)</summary>

```diff
diff --git a/src/request_queue.cpp b/src/request_queue.cpp
--- a/src/request_queue.cpp
+++ b/src/request_queue.cpp
@@ -15,7 +15,7 @@ Status RequestQueue::enqueue(const Request& r) {
     unsigned coreIdx = static_cast<unsigned>(r.core);
     if (coreIdx >= kCoreCount) return Status::INVALID_ARG;
     std::deque<Request>& q = queues_[coreIdx];
-    if (q.size() >= kMaxQueuePerCore) return Status::QUEUE_FULL;
+    if (q.size() > kMaxQueuePerCore) return Status::QUEUE_FULL;
 
     // Insert before the first entry with strictly lower priority, keeping FIFO within a priority.
     auto it = q.begin();
```
`unit_tests`: Errors (3 failures, 215 tests, 215 ran, 926 checks, 0 ignored, 0 filtered out, 2 ms)<br>`TEST(RequestQueueEnqueue, Enqueue_L18QueueAtMaxSize_ReturnsQueueFull)`<br>`TEST(CvAccelService, Submit_L118StNotOk_ReturnsSt)`<br>`TEST(RequestQueue, Enqueue_QueueSizeAtMax_ReturnsQueueFull)`
```
CHECK(st == cvaccel::Status::QUEUE_FULL) failed
LONGS_EQUAL((int)Status::QUEUE_FULL, (int)st) failed
LONGS_EQUAL((int)Status::QUEUE_FULL, (int)queue.enqueue(extra)) failed
```
`unit_tests_wrap`: OK (3 tests, 3 ran, 18 checks, 0 ignored, 0 filtered out, 0 ms)

</details>

<details><summary><b>B3</b> Off-by-one in a boundary nobody tests exactly (🟨 tests)</summary>

```diff
diff --git a/src/memory_pool.cpp b/src/memory_pool.cpp
--- a/src/memory_pool.cpp
+++ b/src/memory_pool.cpp
@@ -25,7 +25,7 @@ Status MemoryPool::allocate(SessionId owner, size_t bytes, MemHandle& outHandle,
         cursor = it->offset + it->reserved;
     }
     size_t gapEnd = (it == blocks_.end()) ? poolBytes_ : it->offset;
-    if (gapEnd - cursor < reserved) return Status::NO_MEMORY;
+    if (gapEnd - cursor <= reserved) return Status::NO_MEMORY;
 
     MemBlock blk;
     blk.handle = nextHandle_++;
```
`unit_tests`: Errors (4 failures, 215 tests, 215 ran, 922 checks, 0 ignored, 0 filtered out, 4 ms)<br>`TEST(CvAccelService, MemoryPoolAllocate_GapAtStartFits_PlacesBeforeFirstBlock)`<br>`TEST(CvAccelService, MemoryPoolAllocate_GapBetweenBlocksFits_ReusesGap)`<br>`TEST(MemoryPool, Allocate_GapAtStartFits_PlacesBeforeFirstBlock)`<br>`TEST(MemoryPool, Allocate_GapBetweenBlocksFits_ReusesGap)`
```
CHECK(status == cvaccel::Status::OK) failed
CHECK(status == cvaccel::Status::OK) failed
CHECK(status == cvaccel::Status::OK) failed
```
`unit_tests_wrap`: OK (3 tests, 3 ran, 18 checks, 0 ignored, 0 filtered out, 0 ms)

</details>

<details><summary><b>B4</b> Different error code returned (🟨 tests)</summary>

```diff
diff --git a/src/memory_pool.cpp b/src/memory_pool.cpp
--- a/src/memory_pool.cpp
+++ b/src/memory_pool.cpp
@@ -47,7 +47,7 @@ Status MemoryPool::release(MemHandle h, SessionId owner) {
             return Status::OK;
         }
     }
-    return Status::INVALID_ARG;
+    return Status::NOT_OWNER;
 }
 
 void MemoryPool::releaseAll(SessionId owner) {
```
`unit_tests`: Errors (3 failures, 215 tests, 215 ran, 926 checks, 0 ignored, 0 filtered out, 4 ms)<br>`TEST(CvAccelService, FreeMem_L80BlkFalse_ReturnsInvalidArg)`<br>`TEST(MemoryPool, Release_HandleNotFound_ReturnsInvalidArg)`<br>`TEST(MemoryPool, Release_EmptyPool_ReturnsInvalidArg)`
```
LONGS_EQUAL((int)Status::INVALID_ARG, (int)st) failed
CHECK(status == cvaccel::Status::INVALID_ARG) failed
CHECK(status == cvaccel::Status::INVALID_ARG) failed
```
`unit_tests_wrap`: OK (3 tests, 3 ran, 18 checks, 0 ignored, 0 filtered out, 0 ms)

</details>

<details><summary><b>B5</b> New branch (new validation) (⬜ nothing)</summary>

```diff
diff --git a/src/request_queue.cpp b/src/request_queue.cpp
--- a/src/request_queue.cpp
+++ b/src/request_queue.cpp
@@ -14,6 +14,7 @@ Status RequestQueue::enqueue(const Request& r) {
     for (const auto& q : queues_) for (const auto& x : q) if (x.id == r.id) return Status::INVALID_ARG;   // duplicate id
     unsigned coreIdx = static_cast<unsigned>(r.core);
     if (coreIdx >= kCoreCount) return Status::INVALID_ARG;
+    if (r.bytes > kMaxJobBytes) return Status::INVALID_ARG;
     std::deque<Request>& q = queues_[coreIdx];
     if (q.size() >= kMaxQueuePerCore) return Status::QUEUE_FULL;
 
```
`unit_tests`: OK (215 tests, 215 ran, 926 checks, 0 ignored, 0 filtered out, 2 ms)
`unit_tests_wrap`: OK (3 tests, 3 ran, 18 checks, 0 ignored, 0 filtered out, 0 ms)

</details>

<details><summary><b>B6</b> Side effect removed (🟨 tests)</summary>

```diff
diff --git a/src/dispatcher.cpp b/src/dispatcher.cpp
--- a/src/dispatcher.cpp
+++ b/src/dispatcher.cpp
@@ -103,9 +103,6 @@ Status Dispatcher::onCompletion(const hw::JobResult& res) {
     rec.status = res.status;
     perf_.record(rec);
 
-    SessionInfo* si = sessions_.find(r.session);
-    if (si && si->openRequests > 0) --si->openRequests;
-
     // r.clientFd is set to -1 by cancelSession() for jobs whose session closed while they were
     // still running (see below), so this also covers "the session is no longer active".
     if (r.clientFd != -1) {
```
`unit_tests`: Errors (2 failures, 215 tests, 215 ran, 925 checks, 0 ignored, 0 filtered out, 2 ms)<br>`TEST(CvAccelService, OnHwCompletion_TypicalCompletion_RecordsAndWakesClient)`<br>`TEST(Dispatcher, OnCompletion_L107_SessionFoundWithOpenRequests_DecrementsOpenRequests)`
```
expected <0 (0x0)>
expected <0 (0x0)>
```
`unit_tests_wrap`: OK (3 tests, 3 ran, 18 checks, 0 ignored, 0 filtered out, 1 ms)

</details>

<details><summary><b>B7</b> Extra call to a collaborator (🟨 tests)</summary>

```diff
diff --git a/src/dispatcher.cpp b/src/dispatcher.cpp
--- a/src/dispatcher.cpp
+++ b/src/dispatcher.cpp
@@ -19,7 +19,7 @@ Status Dispatcher::start(Request& r) {
     hw::JobDesc job{};
     job.jobId = r.id;
     job.core = r.core;
-    job.physAddr = pool_.physAddr(r.mem);
+    job.physAddr = pool_.physAddr(r.mem) ? pool_.physAddr(r.mem) : 0;
     job.bytes = r.bytes;
     for (unsigned i = 0; i < kConfigWords; ++i) job.config[i] = r.config[i];
 
```
`unit_tests`: OK (215 tests, 215 ran, 926 checks, 0 ignored, 0 filtered out, 2 ms)
`unit_tests_wrap`: Errors (1 failures, 3 tests, 3 ran, 18 checks, 0 ignored, 0 filtered out, 0 ms)<br>`TEST(DispatcherWrap, Start_UsesPhysAddrOfHandle_Mocked)`
```
Mock Failure: Unexpected additional (2nd) call to function: MemoryPool::physAddr::MemoryPool::physAddr
```

</details>

<details><summary><b>B8</b> Call order changed (⬜ nothing)</summary>

```diff
diff --git a/src/dispatcher.cpp b/src/dispatcher.cpp
--- a/src/dispatcher.cpp
+++ b/src/dispatcher.cpp
@@ -101,8 +101,6 @@ Status Dispatcher::onCompletion(const hw::JobResult& res) {
     rec.tFinished = dev_.nowNs();
     rec.hwCycles = res.hwCycles;
     rec.status = res.status;
-    perf_.record(rec);
-
     SessionInfo* si = sessions_.find(r.session);
     if (si && si->openRequests > 0) --si->openRequests;
 
@@ -121,6 +119,7 @@ Status Dispatcher::onCompletion(const hw::JobResult& res) {
         dev_.ioctlToClient(r.clientFd, IoctlCmd::WAKE, &info, sizeof(info));
     }
 
+    perf_.record(rec);
     running_.erase(it);
     return Status::OK;
 }
```
`unit_tests`: OK (215 tests, 215 ran, 926 checks, 0 ignored, 0 filtered out, 4 ms)
`unit_tests_wrap`: OK (3 tests, 3 ran, 18 checks, 0 ignored, 0 filtered out, 0 ms)

</details>

<details><summary><b>B9</b> Wrong argument passed to a collaborator (⬜ nothing)</summary>

```diff
diff --git a/src/dispatcher.cpp b/src/dispatcher.cpp
--- a/src/dispatcher.cpp
+++ b/src/dispatcher.cpp
@@ -75,7 +75,7 @@ unsigned Dispatcher::pump() {
             if (r.clientFd != -1) {
                 // See onCompletion(): this in-process sim's wake handler never calls back into
                 // the service, so it is safe to hold the service mutex while calling it here.
-                dev_.ioctlToClient(r.clientFd, IoctlCmd::WAKE, &info, sizeof(info));
+                dev_.ioctlToClient(r.clientFd, IoctlCmd::WAKE, &info, sizeof(info) - 1);
             }
 
             SessionInfo* si = sessions_.find(r.session);
@@ -118,7 +118,7 @@ Status Dispatcher::onCompletion(const hw::JobResult& res) {
         // Not calling this under mtx_ would let a queued completion race a session close; in this
         // in-process sim the client's wake handler never calls back into the service, so holding
         // the service mutex (via the caller) across this ioctl is safe.
-        dev_.ioctlToClient(r.clientFd, IoctlCmd::WAKE, &info, sizeof(info));
+        dev_.ioctlToClient(r.clientFd, IoctlCmd::WAKE, &info, sizeof(info) - 1);
     }
 
     running_.erase(it);
@@ -140,7 +140,7 @@ unsigned Dispatcher::cancelSession(SessionId session) {
             info.status = Status::CANCELLED;
             info.latencyNs = 0;
             info.hwCycles = 0;
-            dev_.ioctlToClient(fd, IoctlCmd::WAKE, &info, sizeof(info));
+            dev_.ioctlToClient(fd, IoctlCmd::WAKE, &info, sizeof(info) - 1);
         }
         if (si && si->openRequests > 0) --si->openRequests;
     }
```
`unit_tests`: OK (215 tests, 215 ran, 926 checks, 0 ignored, 0 filtered out, 3 ms)
`unit_tests_wrap`: OK (3 tests, 3 ran, 18 checks, 0 ignored, 0 filtered out, 1 ms)

</details>

<details><summary><b>G1</b> Parameter added, with a default value (⬜ nothing)</summary>

```diff
diff --git a/include/cvaccel/request_queue.hpp b/include/cvaccel/request_queue.hpp
--- a/include/cvaccel/request_queue.hpp
+++ b/include/cvaccel/request_queue.hpp
@@ -25,7 +25,7 @@ public:
     Status   enqueue(const Request& r);                 // QUEUE_FULL at kMaxQueuePerCore, INVALID_ARG for a bad core
     bool     dequeue(CoreType core, Request& out);      // false when empty
     bool     peek(CoreType core, Request& out) const;
-    unsigned size(CoreType core) const;
+    unsigned size(CoreType core, bool includeRunning = false) const;
     unsigned sizeTotal() const;
     // removes every queued request of the session; returns how many were removed (their ids appended to removed)
     unsigned cancelSession(SessionId session, std::vector<RequestId>& removed);
diff --git a/src/request_queue.cpp b/src/request_queue.cpp
--- a/src/request_queue.cpp
+++ b/src/request_queue.cpp
@@ -43,7 +43,8 @@ bool RequestQueue::peek(CoreType core, Request& out) const {
     return true;
 }
 
-unsigned RequestQueue::size(CoreType core) const {
+unsigned RequestQueue::size(CoreType core, bool includeRunning) const {
+    (void)includeRunning;
     unsigned coreIdx = static_cast<unsigned>(core);
     if (coreIdx >= kCoreCount) return 0;
     return static_cast<unsigned>(queues_[coreIdx].size());
```
`unit_tests`: OK (215 tests, 215 ran, 926 checks, 0 ignored, 0 filtered out, 4 ms)
`unit_tests_wrap`: OK (3 tests, 3 ran, 18 checks, 0 ignored, 0 filtered out, 0 ms)

</details>

<details><summary><b>G2</b> Parameter added, no default (production callers updated) (🟥 compiler)</summary>

```diff
diff --git a/include/cvaccel/memory_pool.hpp b/include/cvaccel/memory_pool.hpp
--- a/include/cvaccel/memory_pool.hpp
+++ b/include/cvaccel/memory_pool.hpp
@@ -21,7 +21,7 @@ class MemoryPool {
 public:
     explicit MemoryPool(size_t poolBytes = kPoolBytes, uint64_t physBase = 0, uint8_t* virtBase = nullptr);
     Status    allocate(SessionId owner, size_t bytes, MemHandle& outHandle, size_t align = kMemAlign);   // NO_MEMORY, INVALID_ARG (0 or > pool)
-    Status    release(MemHandle h, SessionId owner);                          // NOT_OWNER if owner differs
+    Status    release(MemHandle h, SessionId owner, bool force);                          // NOT_OWNER if owner differs
     void      releaseAll(SessionId owner);
     const MemBlock* find(MemHandle h) const;
     uint64_t  physAddr(MemHandle h) const;                                     // 0 if unknown
diff --git a/src/memory_pool.cpp b/src/memory_pool.cpp
--- a/src/memory_pool.cpp
+++ b/src/memory_pool.cpp
@@ -39,7 +39,8 @@ Status MemoryPool::allocate(SessionId owner, size_t bytes, MemHandle& outHandle,
     return Status::OK;
 }
 
-Status MemoryPool::release(MemHandle h, SessionId owner) {
+Status MemoryPool::release(MemHandle h, SessionId owner, bool force) {
+    (void)force;
     for (auto it = blocks_.begin(); it != blocks_.end(); ++it) {
         if (it->handle == h) {
             if (it->owner != owner) return Status::NOT_OWNER;
diff --git a/src/service.cpp b/src/service.cpp
--- a/src/service.cpp
+++ b/src/service.cpp
@@ -78,7 +78,7 @@ Status CvAccelService::freeMem(ClientFd fd, FreeMemArgs& a) {
     if (!sessions_.owns(a.session, fd)) return Status::NOT_OWNER;
     const MemBlock* blk = pool_.find(a.handle);
     uint64_t bytes = blk ? blk->bytes : 0;
-    Status st = pool_.release(a.handle, a.session);
+    Status st = pool_.release(a.handle, a.session, false);
     if (st != Status::OK) return st;
     if (SessionInfo* si = sessions_.find(a.session)) {
         si->bytesAllocated = (bytes <= si->bytesAllocated) ? si->bytesAllocated - bytes : 0;
```
First errors:
```
tests/memory_pool_test.cpp:96: no matching function for call to ‘cvaccel::MemoryPool::release(cvaccel::MemHandle&, int)’
tests/memory_pool_test.cpp:111: no matching function for call to ‘cvaccel::MemoryPool::release(cvaccel::MemHandle&, int)’
tests/memory_pool_test.cpp:141: no matching function for call to ‘cvaccel::MemoryPool::release(cvaccel::MemHandle&, int)’
tests/memory_pool_test.cpp:174: no matching function for call to ‘cvaccel::MemoryPool::release(int, int)’
tests/memory_pool_test.cpp:184: no matching function for call to ‘cvaccel::MemoryPool::release(cvaccel::MemHandle&, int)’
tests/memory_pool_test.cpp:196: no matching function for call to ‘cvaccel::MemoryPool::release(cvaccel::MemHandle&, int)’
```
`unit_tests`: not built
`unit_tests_wrap`: OK (3 tests, 3 ran, 18 checks, 0 ignored, 0 filtered out, 0 ms)

</details>

<details><summary><b>G3</b> Type alias widened (⬜ nothing)</summary>

```diff
diff --git a/include/cvaccel/types.hpp b/include/cvaccel/types.hpp
--- a/include/cvaccel/types.hpp
+++ b/include/cvaccel/types.hpp
@@ -12,7 +12,7 @@ enum class Status : int8_t {
     QUEUE_FULL = -5, HW_ERROR = -6, CANCELLED = -7, BUSY = -8, INTEGRITY = -9
 };
 
-using SessionId = uint16_t;   // 0 = invalid
+using SessionId = uint32_t;   // 0 = invalid
 using MemHandle = uint32_t;   // 0 = invalid
 using RequestId = uint32_t;   // 0 = invalid
 using ClientFd  = int;        // the client's device file descriptor (identity for the wake-up ioctl)
```
`unit_tests`: OK (215 tests, 215 ran, 926 checks, 0 ignored, 0 filtered out, 3 ms)
`unit_tests_wrap`: OK (3 tests, 3 ran, 18 checks, 0 ignored, 0 filtered out, 0 ms)

</details>

<details><summary><b>G4</b> Return type bool becomes an enum class (🟥 compiler)</summary>

```diff
diff --git a/include/cvaccel/request_queue.hpp b/include/cvaccel/request_queue.hpp
--- a/include/cvaccel/request_queue.hpp
+++ b/include/cvaccel/request_queue.hpp
@@ -23,7 +23,7 @@ struct Request {
 class RequestQueue {
 public:
     Status   enqueue(const Request& r);                 // QUEUE_FULL at kMaxQueuePerCore, INVALID_ARG for a bad core
-    bool     dequeue(CoreType core, Request& out);      // false when empty
+    Status   dequeue(CoreType core, Request& out);      // false when empty
     bool     peek(CoreType core, Request& out) const;
     unsigned size(CoreType core) const;
     unsigned sizeTotal() const;
diff --git a/src/dispatcher.cpp b/src/dispatcher.cpp
--- a/src/dispatcher.cpp
+++ b/src/dispatcher.cpp
@@ -37,7 +37,7 @@ unsigned Dispatcher::pump() {
         CoreType core = static_cast<CoreType>(c);
         while (!hw_.isBusy(core)) {
             Request r;
-            if (!queue_.dequeue(core, r)) break;
+            if (queue_.dequeue(core, r) != Status::OK) break;
 
             Status st = start(r);
             if (st == Status::OK) {
diff --git a/src/request_queue.cpp b/src/request_queue.cpp
--- a/src/request_queue.cpp
+++ b/src/request_queue.cpp
@@ -24,14 +24,14 @@ Status RequestQueue::enqueue(const Request& r) {
     return Status::OK;
 }
 
-bool RequestQueue::dequeue(CoreType core, Request& out) {
+Status RequestQueue::dequeue(CoreType core, Request& out) {
     unsigned coreIdx = static_cast<unsigned>(core);
-    if (coreIdx >= kCoreCount) return false;
+    if (coreIdx >= kCoreCount) return Status::INVALID_ARG;
     std::deque<Request>& q = queues_[coreIdx];
-    if (q.empty()) return false;
+    if (q.empty()) return Status::BUSY;
     out = q.front();
     q.pop_front();
-    return true;
+    return Status::OK;
 }
 
 bool RequestQueue::peek(CoreType core, Request& out) const {
```
First errors:
```
tests/request_queue_test.cpp:131: no match for ‘operator!’ (operand type is ‘cvaccel::Status’)
tests/request_queue_test.cpp:148: no match for ‘operator!’ (operand type is ‘cvaccel::Status’)
```
`unit_tests`: not built
`unit_tests_wrap`: OK (3 tests, 3 ran, 18 checks, 0 ignored, 0 filtered out, 1 ms)

</details>

<details><summary><b>G5</b> Function renamed (production callers updated) (🟥 compiler)</summary>

```diff
diff --git a/include/cvaccel/request_queue.hpp b/include/cvaccel/request_queue.hpp
--- a/include/cvaccel/request_queue.hpp
+++ b/include/cvaccel/request_queue.hpp
@@ -26,7 +26,7 @@ public:
     bool     dequeue(CoreType core, Request& out);      // false when empty
     bool     peek(CoreType core, Request& out) const;
     unsigned size(CoreType core) const;
-    unsigned sizeTotal() const;
+    unsigned totalSize() const;
     // removes every queued request of the session; returns how many were removed (their ids appended to removed)
     unsigned cancelSession(SessionId session, std::vector<RequestId>& removed);
 private:
diff --git a/src/request_queue.cpp b/src/request_queue.cpp
--- a/src/request_queue.cpp
+++ b/src/request_queue.cpp
@@ -49,7 +49,7 @@ unsigned RequestQueue::size(CoreType core) const {
     return static_cast<unsigned>(queues_[coreIdx].size());
 }
 
-unsigned RequestQueue::sizeTotal() const {
+unsigned RequestQueue::totalSize() const {
     unsigned total = 0;
     for (const auto& q : queues_) total += static_cast<unsigned>(q.size());
     return total;
diff --git a/src/service.cpp b/src/service.cpp
--- a/src/service.cpp
+++ b/src/service.cpp
@@ -154,7 +154,7 @@ unsigned CvAccelService::pump() {
 
 unsigned CvAccelService::queued() const {
     std::lock_guard<std::mutex> lock(mtx_);
-    return queue_.sizeTotal();
+    return queue_.totalSize();
 }
 
 }  // namespace cvaccel
```
First errors:
```
tests/request_queue_test.cpp:234: ‘class cvaccel::RequestQueue’ has no member named ‘sizeTotal’
tests/dispatcher_test.cpp:332: ‘class cvaccel::RequestQueue’ has no member named ‘sizeTotal’
```
`unit_tests`: not built
`unit_tests_wrap`: OK (3 tests, 3 ran, 18 checks, 0 ignored, 0 filtered out, 0 ms)

</details>

<details><summary><b>G6</b> Function removed (only tests used it) (🟥 compiler)</summary>

```diff
diff --git a/include/cvaccel/memory_pool.hpp b/include/cvaccel/memory_pool.hpp
--- a/include/cvaccel/memory_pool.hpp
+++ b/include/cvaccel/memory_pool.hpp
@@ -28,7 +28,6 @@ public:
     uint8_t*  map(MemHandle h);                                                // nullptr if unknown or no virt base
     size_t    bytesInUse() const;
     size_t    bytesInUse(SessionId owner) const;
-    size_t    largestFree() const;
     size_t    capacity() const { return poolBytes_; }
 private:
     size_t    poolBytes_;
diff --git a/src/memory_pool.cpp b/src/memory_pool.cpp
--- a/src/memory_pool.cpp
+++ b/src/memory_pool.cpp
@@ -84,7 +84,7 @@ size_t MemoryPool::bytesInUse(SessionId owner) const {
     return total;
 }
 
-size_t MemoryPool::largestFree() const {
+static size_t largestFree_removed(const std::vector<MemBlock>& blocks_, size_t poolBytes_) {
     size_t largest = 0;
     size_t cursor = 0;
     for (const auto& b : blocks_) {
```
First errors:
```
tests/memory_pool_test.cpp:322: ‘class cvaccel::MemoryPool’ has no member named ‘largestFree’
```
`unit_tests`: not built
`unit_tests_wrap`: OK (3 tests, 3 ran, 18 checks, 0 ignored, 0 filtered out, 0 ms)

</details>

<details><summary><b>G7</b> Test-only public helpers made private (🟥 compiler)</summary>

```diff
diff --git a/include/cvaccel/perf_monitor.hpp b/include/cvaccel/perf_monitor.hpp
--- a/include/cvaccel/perf_monitor.hpp
+++ b/include/cvaccel/perf_monitor.hpp
@@ -37,11 +37,10 @@ public:
     uint64_t totalCount() const;
     std::string report() const;                       // human-readable, one line per core
     void     reset();
-    // integrity rules, exposed for testing
-    static bool timestampsOk(const PerfRecord& r);    // queued <= started <= finished, finished > 0
-    static bool bytesOk(const PerfRecord& r);         // 0 < bytes <= allocated
-    static bool coreBytesOk(const PerfRecord& r);     // bytes <= kMaxJobBytes for that core
 private:
+    static bool timestampsOk(const PerfRecord& r);
+    static bool bytesOk(const PerfRecord& r);
+    static bool coreBytesOk(const PerfRecord& r);
     std::array<PerfStats, kCoreCount> perCore_{};
     std::map<SessionId, PerfStats> perSession_;
     uint64_t integrityErrors_ = 0;
```
First errors:
```
tests/perf_monitor_test.cpp:53: ‘static bool cvaccel::PerfMonitor::timestampsOk(const cvaccel::PerfRecord&)’ is private within this context
tests/perf_monitor_test.cpp:59: ‘static bool cvaccel::PerfMonitor::bytesOk(const cvaccel::PerfRecord&)’ is private within this context
tests/perf_monitor_test.cpp:67: ‘static bool cvaccel::PerfMonitor::coreBytesOk(const cvaccel::PerfRecord&)’ is private within this context
tests/service_test.cpp:1886: ‘static bool cvaccel::PerfMonitor::coreBytesOk(const cvaccel::PerfRecord&)’ is private within this context
```
`unit_tests`: not built
`unit_tests_wrap`: OK (3 tests, 3 ran, 18 checks, 0 ignored, 0 filtered out, 0 ms)

</details>

<details><summary><b>G8</b> Overload added that makes calls ambiguous (⬜ nothing)</summary>

```diff
diff --git a/include/cvaccel/memory_pool.hpp b/include/cvaccel/memory_pool.hpp
--- a/include/cvaccel/memory_pool.hpp
+++ b/include/cvaccel/memory_pool.hpp
@@ -28,6 +28,7 @@ public:
     uint8_t*  map(MemHandle h);                                                // nullptr if unknown or no virt base
     size_t    bytesInUse() const;
     size_t    bytesInUse(SessionId owner) const;
+    size_t    bytesInUse(uint32_t tag) const;
     size_t    largestFree() const;
     size_t    capacity() const { return poolBytes_; }
 private:
diff --git a/src/memory_pool.cpp b/src/memory_pool.cpp
--- a/src/memory_pool.cpp
+++ b/src/memory_pool.cpp
@@ -56,6 +56,8 @@ void MemoryPool::releaseAll(SessionId owner) {
                   blocks_.end());
 }
 
+size_t MemoryPool::bytesInUse(uint32_t) const { return 0; }
+
 const MemBlock* MemoryPool::find(MemHandle h) const {
     for (const auto& b : blocks_) if (b.handle == h) return &b;
     return nullptr;
```
`unit_tests`: OK (215 tests, 215 ran, 926 checks, 0 ignored, 0 filtered out, 2 ms)
`unit_tests_wrap`: OK (3 tests, 3 ran, 18 checks, 0 ignored, 0 filtered out, 1 ms)

</details>

<details><summary><b>G9</b> Overload added that tests silently switch to (🟨 tests)</summary>

```diff
diff --git a/include/cvaccel/memory_pool.hpp b/include/cvaccel/memory_pool.hpp
--- a/include/cvaccel/memory_pool.hpp
+++ b/include/cvaccel/memory_pool.hpp
@@ -22,6 +22,7 @@ public:
     explicit MemoryPool(size_t poolBytes = kPoolBytes, uint64_t physBase = 0, uint8_t* virtBase = nullptr);
     Status    allocate(SessionId owner, size_t bytes, MemHandle& outHandle, size_t align = kMemAlign);   // NO_MEMORY, INVALID_ARG (0 or > pool)
     Status    release(MemHandle h, SessionId owner);                          // NOT_OWNER if owner differs
+    Status    release(MemHandle h, int legacyOwner);
     void      releaseAll(SessionId owner);
     const MemBlock* find(MemHandle h) const;
     uint64_t  physAddr(MemHandle h) const;                                     // 0 if unknown
diff --git a/src/memory_pool.cpp b/src/memory_pool.cpp
--- a/src/memory_pool.cpp
+++ b/src/memory_pool.cpp
@@ -50,6 +50,8 @@ Status MemoryPool::release(MemHandle h, SessionId owner) {
     return Status::INVALID_ARG;
 }
 
+Status MemoryPool::release(MemHandle h, int) { for (auto it = blocks_.begin(); it != blocks_.end(); ++it) if (it->handle == h) { blocks_.erase(it); return Status::OK; } return Status::INVALID_ARG; }
+
 void MemoryPool::releaseAll(SessionId owner) {
     blocks_.erase(std::remove_if(blocks_.begin(), blocks_.end(),
                                   [owner](const MemBlock& b) { return b.owner == owner; }),
```
`unit_tests`: Errors (1 failures, 215 tests, 215 ran, 926 checks, 0 ignored, 0 filtered out, 2 ms)<br>`TEST(MemoryPool, Release_OwnerMismatch_ReturnsNotOwner)`
```
CHECK(status == cvaccel::Status::NOT_OWNER) failed
```
`unit_tests_wrap`: OK (3 tests, 3 ran, 18 checks, 0 ignored, 0 filtered out, 0 ms)

</details>

<details><summary><b>V1</b> Pure virtual method added (🟥 compiler)</summary>

```diff
diff --git a/include/cvaccel/hw_block.hpp b/include/cvaccel/hw_block.hpp
--- a/include/cvaccel/hw_block.hpp
+++ b/include/cvaccel/hw_block.hpp
@@ -28,6 +28,7 @@ public:
     virtual Status   submit(const JobDesc& job) = 0;
     virtual bool     isBusy(CoreType core) const = 0;
     virtual void     setCompletionHandler(std::function<void(const JobResult&)> handler) = 0;
+    virtual void     reset() = 0;
     virtual unsigned coreCount() const { return kCoreCount; }
 };
 
```
First errors:
```
tests/service_test.cpp:75: cannot declare variable ‘hw’ to be of abstract type ‘{anonymous}::FakeAccelBlock’
tests/service_test.cpp:85: cannot declare variable ‘hw’ to be of abstract type ‘{anonymous}::FakeAccelBlock’
tests/service_test.cpp:98: cannot declare variable ‘hw’ to be of abstract type ‘{anonymous}::FakeAccelBlock’
tests/service_test.cpp:113: cannot declare variable ‘hw’ to be of abstract type ‘{anonymous}::FakeAccelBlock’
tests/service_test.cpp:128: cannot declare variable ‘hw’ to be of abstract type ‘{anonymous}::FakeAccelBlock’
tests/service_test.cpp:149: cannot declare variable ‘hw’ to be of abstract type ‘{anonymous}::FakeAccelBlock’
```
`unit_tests`: not built
`unit_tests_wrap`: not built

</details>

<details><summary><b>V2</b> Virtual method with a default body added (⬜ nothing)</summary>

```diff
diff --git a/include/cvaccel/hw_block.hpp b/include/cvaccel/hw_block.hpp
--- a/include/cvaccel/hw_block.hpp
+++ b/include/cvaccel/hw_block.hpp
@@ -28,6 +28,7 @@ public:
     virtual Status   submit(const JobDesc& job) = 0;
     virtual bool     isBusy(CoreType core) const = 0;
     virtual void     setCompletionHandler(std::function<void(const JobResult&)> handler) = 0;
+    virtual void     reset() {}
     virtual unsigned coreCount() const { return kCoreCount; }
 };
 
```
`unit_tests`: OK (215 tests, 215 ran, 926 checks, 0 ignored, 0 filtered out, 2 ms)
`unit_tests_wrap`: OK (3 tests, 3 ran, 18 checks, 0 ignored, 0 filtered out, 0 ms)

</details>

<details><summary><b>V3</b> const dropped from a pure virtual (🟥 compiler)</summary>

```diff
diff --git a/include/cvaccel/device.hpp b/include/cvaccel/device.hpp
--- a/include/cvaccel/device.hpp
+++ b/include/cvaccel/device.hpp
@@ -11,7 +11,7 @@ public:
     virtual ~IDevice() = default;
     // ioctl in the service->client direction: wakes the client that owns clientFd. Returns OK or INVALID_ARG.
     virtual Status  ioctlToClient(ClientFd clientFd, IoctlCmd cmd, const void* payload, size_t payloadBytes) = 0;
-    virtual TimeNs  nowNs() const = 0;
+    virtual TimeNs  nowNs() = 0;
     // physical memory backing the pool: the service calls this once at start-up.
     virtual uint64_t poolPhysBase() const = 0;
     virtual uint8_t* poolVirtBase() = 0;
```
First errors:
```
tests/service_test.cpp:62: ‘cvaccel::TimeNs {anonymous}::FakeDevice::nowNs() const’ marked ‘override’, but does not override
tests/service_test.cpp:76: cannot declare variable ‘dev’ to be of abstract type ‘{anonymous}::FakeDevice’
tests/service_test.cpp:86: cannot declare variable ‘dev’ to be of abstract type ‘{anonymous}::FakeDevice’
tests/service_test.cpp:99: cannot declare variable ‘dev’ to be of abstract type ‘{anonymous}::FakeDevice’
tests/service_test.cpp:114: cannot declare variable ‘dev’ to be of abstract type ‘{anonymous}::FakeDevice’
tests/service_test.cpp:129: cannot declare variable ‘dev’ to be of abstract type ‘{anonymous}::FakeDevice’
```
`unit_tests`: not built
`unit_tests_wrap`: not built

</details>

<details><summary><b>V4</b> Parameter with default added to a pure virtual (🟥 compiler)</summary>

```diff
diff --git a/include/cvaccel/hw_block.hpp b/include/cvaccel/hw_block.hpp
--- a/include/cvaccel/hw_block.hpp
+++ b/include/cvaccel/hw_block.hpp
@@ -26,7 +26,7 @@ class IAccelBlock {
 public:
     virtual ~IAccelBlock() = default;
     virtual Status   submit(const JobDesc& job) = 0;
-    virtual bool     isBusy(CoreType core) const = 0;
+    virtual bool     isBusy(CoreType core, bool strict = false) const = 0;
     virtual void     setCompletionHandler(std::function<void(const JobResult&)> handler) = 0;
     virtual unsigned coreCount() const { return kCoreCount; }
 };
```
First errors:
```
tests/dispatcher_test.cpp:16: ‘bool {anonymous}::FakeAccelBlock::isBusy(cvaccel::CoreType) const’ marked ‘override’, but does not override
tests/dispatcher_test.cpp:62: cannot declare variable ‘hw’ to be of abstract type ‘{anonymous}::FakeAccelBlock’
tests/dispatcher_test.cpp:83: cannot declare variable ‘hw’ to be of abstract type ‘{anonymous}::FakeAccelBlock’
tests/dispatcher_test.cpp:101: cannot declare variable ‘hw’ to be of abstract type ‘{anonymous}::FakeAccelBlock’
tests/dispatcher_test.cpp:121: cannot declare variable ‘hw’ to be of abstract type ‘{anonymous}::FakeAccelBlock’
tests/dispatcher_test.cpp:143: cannot declare variable ‘hw’ to be of abstract type ‘{anonymous}::FakeAccelBlock’
```
`unit_tests`: not built
`unit_tests_wrap`: not built

</details>

<details><summary><b>V5</b> Return type of a pure virtual changed (🟥 compiler)</summary>

```diff
diff --git a/include/cvaccel/device.hpp b/include/cvaccel/device.hpp
--- a/include/cvaccel/device.hpp
+++ b/include/cvaccel/device.hpp
@@ -11,7 +11,7 @@ public:
     virtual ~IDevice() = default;
     // ioctl in the service->client direction: wakes the client that owns clientFd. Returns OK or INVALID_ARG.
     virtual Status  ioctlToClient(ClientFd clientFd, IoctlCmd cmd, const void* payload, size_t payloadBytes) = 0;
-    virtual TimeNs  nowNs() const = 0;
+    virtual int64_t nowNs() const = 0;
     // physical memory backing the pool: the service calls this once at start-up.
     virtual uint64_t poolPhysBase() const = 0;
     virtual uint8_t* poolVirtBase() = 0;
```
First errors:
```
tests/dispatcher_test.cpp:32: conflicting return type specified for ‘virtual cvaccel::TimeNs {anonymous}::FakeDevice::nowNs() const’
tests/service_test.cpp:62: conflicting return type specified for ‘virtual cvaccel::TimeNs {anonymous}::FakeDevice::nowNs() const’
tests/wrap/dispatcher_wrap_test.cpp:19: conflicting return type specified for ‘virtual cvaccel::TimeNs {anonymous}::Dev::nowNs() const’
```
`unit_tests`: not built
`unit_tests_wrap`: not built

</details>

<details><summary><b>T1</b> Field added at the end of a struct (with initializer) (⬜ nothing)</summary>

```diff
diff --git a/include/cvaccel/request_queue.hpp b/include/cvaccel/request_queue.hpp
--- a/include/cvaccel/request_queue.hpp
+++ b/include/cvaccel/request_queue.hpp
@@ -17,6 +17,7 @@ struct Request {
     uint32_t  bytes = 0;
     TimeNs    tQueued = 0;
     TimeNs    tStarted = 0;
+    uint32_t  flags = 0;
 };
 
 // One FIFO per core; dequeue returns the highest priority first, FIFO inside a priority.
```
`unit_tests`: OK (215 tests, 215 ran, 926 checks, 0 ignored, 0 filtered out, 3 ms)
`unit_tests_wrap`: OK (3 tests, 3 ran, 18 checks, 0 ignored, 0 filtered out, 0 ms)

</details>

<details><summary><b>T2</b> Field inserted in the middle of a struct built with {...} (🟥 compiler)</summary>

```diff
diff --git a/include/cvaccel/hw_block.hpp b/include/cvaccel/hw_block.hpp
--- a/include/cvaccel/hw_block.hpp
+++ b/include/cvaccel/hw_block.hpp
@@ -15,6 +15,7 @@ struct JobDesc {
 
 struct JobResult {
     uint32_t jobId;
+    CoreType core;
     Status   status;                   // OK or HW_ERROR
     uint32_t hwCycles;
 };
```
First errors:
```
tests/dispatcher_test.cpp:481: cannot convert ‘cvaccel::Status’ to ‘cvaccel::CoreType’ in initialization
tests/dispatcher_test.cpp:503: cannot convert ‘cvaccel::Status’ to ‘cvaccel::CoreType’ in initialization
tests/dispatcher_test.cpp:531: cannot convert ‘cvaccel::Status’ to ‘cvaccel::CoreType’ in initialization
tests/dispatcher_test.cpp:555: cannot convert ‘cvaccel::Status’ to ‘cvaccel::CoreType’ in initialization
tests/dispatcher_test.cpp:584: cannot convert ‘cvaccel::Status’ to ‘cvaccel::CoreType’ in initialization
tests/dispatcher_test.cpp:605: cannot convert ‘cvaccel::Status’ to ‘cvaccel::CoreType’ in initialization
```
`unit_tests`: not built
`unit_tests_wrap`: not built

</details>

<details><summary><b>T3</b> Fields of the same type reordered (🟨 tests)</summary>

```diff
diff --git a/include/cvaccel/hw_block.hpp b/include/cvaccel/hw_block.hpp
--- a/include/cvaccel/hw_block.hpp
+++ b/include/cvaccel/hw_block.hpp
@@ -14,9 +14,9 @@ struct JobDesc {
 };
 
 struct JobResult {
-    uint32_t jobId;
-    Status   status;                   // OK or HW_ERROR
     uint32_t hwCycles;
+    Status   status;                   // OK or HW_ERROR
+    uint32_t jobId;
 };
 
 // The accelerator block. One implementation talks to registers; the sim runs a thread per core.
```
`unit_tests`: Errors (5 failures, 215 tests, 215 ran, 923 checks, 0 ignored, 0 filtered out, 4 ms)<br>`TEST(Dispatcher, CancelSession_L150_RunningJobDifferentSession_ClientFdUnaffected)`<br>`TEST(Dispatcher, OnCompletion_L111_ClientFdSet_WakesClient)`<br>`TEST(Dispatcher, OnCompletion_L107_SessionNotFound_StillErasesRunningAndReturnsOk)`<br>`TEST(Dispatcher, OnCompletion_L107_SessionFoundWithOpenRequests_DecrementsOpenRequests)`<br>`TEST(Dispatcher, OnCompletion_L90_JobIdInRunning_ErasesFromRunningAndReturnsOk)`
```
expected <1 (0x1)>
expected <1 (0x1)>
LONGS_EQUAL((int)Status::OK, (int)dispatcher.onCompletion(res)) failed
```
`unit_tests_wrap`: Errors (1 failures, 3 tests, 3 ran, 15 checks, 0 ignored, 0 filtered out, 0 ms)<br>`TEST(DispatcherWrap, Completion_RealPath)`
```
LONGS_EQUAL(static_cast<int>(Status::OK), static_cast<int>(d.onCompletion(res))) failed
```

</details>

<details><summary><b>T4</b> Field renamed (production updated) (🟥 compiler)</summary>

```diff
diff --git a/include/cvaccel/session_manager.hpp b/include/cvaccel/session_manager.hpp
--- a/include/cvaccel/session_manager.hpp
+++ b/include/cvaccel/session_manager.hpp
@@ -8,7 +8,7 @@ struct SessionInfo {
     SessionId id = 0;
     ClientFd  clientFd = -1;
     Priority  priority = Priority::NORMAL;
-    uint32_t  openRequests = 0;    // queued or running
+    uint32_t  pendingRequests = 0;    // queued or running
     uint64_t  bytesAllocated = 0;
     bool      active = false;
 };
diff --git a/src/dispatcher.cpp b/src/dispatcher.cpp
--- a/src/dispatcher.cpp
+++ b/src/dispatcher.cpp
@@ -79,7 +79,7 @@ unsigned Dispatcher::pump() {
             }
 
             SessionInfo* si = sessions_.find(r.session);
-            if (si && si->openRequests > 0) --si->openRequests;
+            if (si && si->pendingRequests > 0) --si->pendingRequests;
         }
     }
     return started;
@@ -104,7 +104,7 @@ Status Dispatcher::onCompletion(const hw::JobResult& res) {
     perf_.record(rec);
 
     SessionInfo* si = sessions_.find(r.session);
-    if (si && si->openRequests > 0) --si->openRequests;
+    if (si && si->pendingRequests > 0) --si->pendingRequests;
 
     // r.clientFd is set to -1 by cancelSession() for jobs whose session closed while they were
     // still running (see below), so this also covers "the session is no longer active".
@@ -142,7 +142,7 @@ unsigned Dispatcher::cancelSession(SessionId session) {
             info.hwCycles = 0;
             dev_.ioctlToClient(fd, IoctlCmd::WAKE, &info, sizeof(info));
         }
-        if (si && si->openRequests > 0) --si->openRequests;
+        if (si && si->pendingRequests > 0) --si->pendingRequests;
     }
 
     // Jobs already handed to the hardware keep running; mark them so their completion is silent.
diff --git a/src/service.cpp b/src/service.cpp
--- a/src/service.cpp
+++ b/src/service.cpp
@@ -118,7 +118,7 @@ Status CvAccelService::submit(ClientFd fd, SubmitArgs& a) {
     if (st != Status::OK) return st;   // e.g. QUEUE_FULL: leave it posted so the client can retry
 
     posted_.erase(it);
-    if (SessionInfo* si = sessions_.find(a.session)) ++si->openRequests;
+    if (SessionInfo* si = sessions_.find(a.session)) ++si->pendingRequests;
 
     dispatcher_.pump();
     return Status::OK;
diff --git a/src/session_manager.cpp b/src/session_manager.cpp
--- a/src/session_manager.cpp
+++ b/src/session_manager.cpp
@@ -9,7 +9,7 @@ Status SessionManager::open(ClientFd clientFd, Priority prio, SessionId& ou
```
First errors:
```
tests/session_manager_test.cpp:54: ‘struct cvaccel::SessionInfo’ has no member named ‘openRequests’; did you mean ‘pendingRequests’?
tests/service_test.cpp:1470: ‘const struct cvaccel::SessionInfo’ has no member named ‘openRequests’; did you mean ‘pendingRequests’?
tests/service_test.cpp:1586: ‘const struct cvaccel::SessionInfo’ has no member named ‘openRequests’; did you mean ‘pendingRequests’?
tests/dispatcher_test.cpp:522: ‘struct cvaccel::SessionInfo’ has no member named ‘openRequests’; did you mean ‘pendingRequests’?
tests/dispatcher_test.cpp:534: ‘struct cvaccel::SessionInfo’ has no member named ‘openRequests’; did you mean ‘pendingRequests’?
tests/dispatcher_test.cpp:575: ‘struct cvaccel::SessionInfo’ has no member named ‘openRequests’; did you mean ‘pendingRequests’?
```
`unit_tests`: not built
`unit_tests_wrap`: OK (3 tests, 3 ran, 18 checks, 0 ignored, 0 filtered out, 0 ms)

</details>

<details><summary><b>T5</b> Field narrowed (⬜ nothing)</summary>

```diff
diff --git a/include/cvaccel/types.hpp b/include/cvaccel/types.hpp
--- a/include/cvaccel/types.hpp
+++ b/include/cvaccel/types.hpp
@@ -37,7 +37,7 @@ struct CompletionInfo {
     RequestId request;
     SessionId session;
     Status    status;
-    TimeNs    latencyNs;     // finished - queued
+    uint32_t  latencyNs;     // finished - queued
     uint32_t  hwCycles;      // reported by the block
 };
 
```
`unit_tests`: OK (215 tests, 215 ran, 926 checks, 0 ignored, 0 filtered out, 3 ms)
`unit_tests_wrap`: OK (3 tests, 3 ran, 18 checks, 0 ignored, 0 filtered out, 1 ms)

</details>

<details><summary><b>T6</b> Enumerator inserted in the middle (values shift), count updated (🟪 crash)</summary>

```diff
diff --git a/include/cvaccel/types.hpp b/include/cvaccel/types.hpp
--- a/include/cvaccel/types.hpp
+++ b/include/cvaccel/types.hpp
@@ -4,8 +4,8 @@
 
 namespace cvaccel {
 
-enum class CoreType : uint8_t { RESIZE = 0, CONVOLVE = 1, WARP = 2, HISTOGRAM = 3, MATCH = 4 };
-constexpr unsigned kCoreCount = 5;
+enum class CoreType : uint8_t { RESIZE = 0, CROP = 1, CONVOLVE = 2, WARP = 3, HISTOGRAM = 4, MATCH = 5 };
+constexpr unsigned kCoreCount = 6;
 
 enum class Status : int8_t {
     OK = 0, INVALID_ARG = -1, NO_SESSION = -2, NO_MEMORY = -3, NOT_OWNER = -4,
```
`unit_tests`: CRASHED (exit -11): lCoreCount_ReturnsInvalidArg) | 	LONGS_EQUAL((int)Status::INVALID_ARG, (int)queue.enqueue(r)) failed | 	expected <-1 (0xffffffffffffffff)> | 	but was  < 0 (0x0)> |  | ...<br>`TEST(RequestQueueEnqueue, Enqueue_L16CoreIdxAtOrAboveCoreCount_ReturnsInvalidArg)`<br>`TEST(CvAccelService, PerfMonitorRecord_CoreIndexOutOfRange_SkipsPerCoreAccumulation)`<br>`TEST(RequestQueue, Enqueue_CoreIdxGreaterOrEqualCoreCount_ReturnsInvalidArg)`
```
CHECK(st == cvaccel::Status::INVALID_ARG) failed
expected <0 (0x0)>
LONGS_EQUAL((int)Status::INVALID_ARG, (int)queue.enqueue(r)) failed
```
`unit_tests_wrap`: OK (3 tests, 3 ran, 18 checks, 0 ignored, 0 filtered out, 1 ms)

</details>

<details><summary><b>T7</b> Enumerator added at the end (⬜ nothing)</summary>

```diff
diff --git a/include/cvaccel/types.hpp b/include/cvaccel/types.hpp
--- a/include/cvaccel/types.hpp
+++ b/include/cvaccel/types.hpp
@@ -25,7 +25,7 @@ constexpr size_t   kMemAlign      = 64;
 constexpr unsigned kConfigWords   = 8;
 constexpr uint32_t kMaxJobBytes   = 8u * 1024u * 1024u;
 
-enum class Priority : uint8_t { LOW = 0, NORMAL = 1, HIGH = 2, URGENT = 3 };
+enum class Priority : uint8_t { LOW = 0, NORMAL = 1, HIGH = 2, URGENT = 3, CRITICAL = 4 };
 
 // ioctl command numbers (client -> service and service -> client)
 enum class IoctlCmd : uint32_t {
```
`unit_tests`: OK (215 tests, 215 ran, 926 checks, 0 ignored, 0 filtered out, 2 ms)
`unit_tests_wrap`: OK (3 tests, 3 ran, 18 checks, 0 ignored, 0 filtered out, 0 ms)

</details>

<details><summary><b>T8</b> Constant changed; tests use the constant (⬜ nothing)</summary>

```diff
diff --git a/include/cvaccel/types.hpp b/include/cvaccel/types.hpp
--- a/include/cvaccel/types.hpp
+++ b/include/cvaccel/types.hpp
@@ -19,7 +19,7 @@ using ClientFd  = int;        // the client's device file descriptor (identity f
 using TimeNs    = uint64_t;
 
 constexpr unsigned kMaxSessions   = 16;
-constexpr unsigned kMaxQueuePerCore = 32;
+constexpr unsigned kMaxQueuePerCore = 16;
 constexpr size_t   kPoolBytes     = 64u * 1024u * 1024u;
 constexpr size_t   kMemAlign      = 64;
 constexpr unsigned kConfigWords   = 8;
```
`unit_tests`: OK (215 tests, 215 ran, 814 checks, 0 ignored, 0 filtered out, 3 ms)
`unit_tests_wrap`: OK (3 tests, 3 ran, 18 checks, 0 ignored, 0 filtered out, 0 ms)

</details>

<details><summary><b>T9</b> Constant changed; tests hard-code its value (🟨 tests)</summary>

```diff
diff --git a/include/cvaccel/types.hpp b/include/cvaccel/types.hpp
--- a/include/cvaccel/types.hpp
+++ b/include/cvaccel/types.hpp
@@ -21,7 +21,7 @@ using TimeNs    = uint64_t;
 constexpr unsigned kMaxSessions   = 16;
 constexpr unsigned kMaxQueuePerCore = 32;
 constexpr size_t   kPoolBytes     = 64u * 1024u * 1024u;
-constexpr size_t   kMemAlign      = 64;
+constexpr size_t   kMemAlign      = 128;
 constexpr unsigned kConfigWords   = 8;
 constexpr uint32_t kMaxJobBytes   = 8u * 1024u * 1024u;
 
```
`unit_tests`: Errors (16 failures, 215 tests, 215 ran, 923 checks, 0 ignored, 0 filtered out, 5 ms)<br>`TEST(CvAccelService, MemoryPoolAllocate_RemainingSpaceTooSmall_ReturnsNoMemory)`<br>`TEST(CvAccelService, MemoryPoolAllocate_NoFittingGapAmongBlocks_PlacesAfterLast)`<br>`TEST(CvAccelService, MemoryPoolAllocate_GapBetweenBlocksTooSmall_SkipsGap)`<br>`TEST(CvAccelService, MemoryPoolAllocate_GapBetweenBlocksFits_ReusesGap)`<br>`TEST(CvAccelService, MemoryPoolAllocate_ThreeExistingBlocks_PlacesAfterAll)`<br>`TEST(CvAccelService, MemoryPoolAllocate_SingleExistingBlock_PlacesAfterIt)`<br>`TEST(MemoryPool, LargestFree_SingleBlock_ReturnsTailGap)`<br>`TEST(MemoryPool, BytesInUse_TwoBlocks_ReturnsSumOfReservedBytes)`
```
CHECK(pool.allocate(1, 64, a) == cvaccel::Status::OK) failed
expected <128 (0x80)>
expected <128 (0x80)>
```
`unit_tests_wrap`: OK (3 tests, 3 ran, 18 checks, 0 ignored, 0 filtered out, 0 ms)

</details>

<details><summary><b>K1</b> Constructor parameter added (production updated) (🟥 compiler)</summary>

```diff
diff --git a/include/cvaccel/dispatcher.hpp b/include/cvaccel/dispatcher.hpp
--- a/include/cvaccel/dispatcher.hpp
+++ b/include/cvaccel/dispatcher.hpp
@@ -16,7 +16,7 @@ namespace cvaccel {
 // by the service's completion handler, also under the mutex.
 class Dispatcher {
 public:
-    Dispatcher(hw::IAccelBlock& hw, os::IDevice& dev, RequestQueue& q, MemoryPool& pool, SessionManager& sm, PerfMonitor& perf);
+    Dispatcher(hw::IAccelBlock& hw, os::IDevice& dev, RequestQueue& q, MemoryPool& pool, SessionManager& sm, PerfMonitor& perf, unsigned maxInFlight);
     // submits as many queued requests as the block accepts; returns how many were started
     unsigned pump();
     // hardware completion for one job: perf record, session bookkeeping, wake-up ioctl. Returns INVALID_ARG for an unknown job.
diff --git a/src/dispatcher.cpp b/src/dispatcher.cpp
--- a/src/dispatcher.cpp
+++ b/src/dispatcher.cpp
@@ -12,8 +12,8 @@ uint32_t blockBytesOf(const MemoryPool& pool, MemHandle h) {
 }  // namespace
 
 Dispatcher::Dispatcher(hw::IAccelBlock& hw, os::IDevice& dev, RequestQueue& q, MemoryPool& pool,
-                        SessionManager& sm, PerfMonitor& perf)
-    : hw_(hw), dev_(dev), queue_(q), pool_(pool), sessions_(sm), perf_(perf) {}
+                        SessionManager& sm, PerfMonitor& perf, unsigned maxInFlight)
+    : hw_(hw), dev_(dev), queue_(q), pool_(pool), sessions_(sm), perf_(perf) { (void)maxInFlight; }
 
 Status Dispatcher::start(Request& r) {
     hw::JobDesc job{};
diff --git a/src/service.cpp b/src/service.cpp
--- a/src/service.cpp
+++ b/src/service.cpp
@@ -7,7 +7,7 @@ CvAccelService::CvAccelService(hw::IAccelBlock& hw, os::IDevice& dev)
     : hw_(hw),
       dev_(dev),
       pool_(kPoolBytes, dev.poolPhysBase(), dev.poolVirtBase()),
-      dispatcher_(hw_, dev_, queue_, pool_, sessions_, perf_) {
+      dispatcher_(hw_, dev_, queue_, pool_, sessions_, perf_, 64) {
     hw_.setCompletionHandler([this](const hw::JobResult& res) { onHwCompletion(res); });
 }
 
```
First errors:
```
tests/dispatcher_test.cpp:64: no matching function for call to ‘cvaccel::Dispatcher::Dispatcher({anonymous}::FakeAccelBlock&, {anonymous}::FakeDevice&, cvaccel::RequestQueue&, cvaccel::MemoryPool&, cvaccel::SessionManager&, cvaccel::PerfMonitor&)’
tests/dispatcher_test.cpp:85: no matching function for call to ‘cvaccel::Dispatcher::Dispatcher({anonymous}::FakeAccelBlock&, {anonymous}::FakeDevice&, cvaccel::RequestQueue&, cvaccel::MemoryPool&, cvaccel::SessionManager&, cvaccel::PerfMonitor&)’
tests/dispatcher_test.cpp:103: no matching function for call to ‘cvaccel::Dispatcher::Dispatcher({anonymous}::FakeAccelBlock&, {anonymous}::FakeDevice&, cvaccel::RequestQueue&, cvaccel::MemoryPool&, cvaccel::SessionManager&, cvaccel::PerfMonitor&)’
tests/dispatcher_test.cpp:123: no matching function for call to ‘cvaccel::Dispatcher::Dispatcher({anonymous}::FakeAccelBlock&, {anonymous}::FakeDevice&, cvaccel::RequestQueue&, cvaccel::MemoryPool&, cvaccel::SessionManager&, cvaccel::PerfMonitor&)’
tests/dispatcher_test.cpp:145: no matching function for call to ‘cvaccel::Dispatcher::Dispatcher({anonymous}::FakeAccelBlock&, {anonymous}::FakeDevice&, cvaccel::RequestQueue&, cvaccel::MemoryPool&, cvaccel::SessionManager&, cvaccel::PerfMonitor&)’
tests/dispatcher_test.cpp:168: no matching function for call to ‘cvaccel::Dispatcher::Dispatcher({anonymous}::FakeAccelBlock&, {anonymous}::FakeDevice&, cvaccel::RequestQueue&, cvaccel::MemoryPool&, cvaccel::SessionManager&, cvaccel::PerfMonitor&)’
```
`unit_tests`: not built
`unit_tests_wrap`: not built

</details>

<details><summary><b>K2</b> Default constructor argument changed (⬜ nothing)</summary>

```diff
diff --git a/include/cvaccel/memory_pool.hpp b/include/cvaccel/memory_pool.hpp
--- a/include/cvaccel/memory_pool.hpp
+++ b/include/cvaccel/memory_pool.hpp
@@ -19,7 +19,7 @@ struct MemBlock {
 // within a run (so a stale handle is detected). Free blocks are coalesced.
 class MemoryPool {
 public:
-    explicit MemoryPool(size_t poolBytes = kPoolBytes, uint64_t physBase = 0, uint8_t* virtBase = nullptr);
+    explicit MemoryPool(size_t poolBytes = 4096, uint64_t physBase = 0, uint8_t* virtBase = nullptr);
     Status    allocate(SessionId owner, size_t bytes, MemHandle& outHandle, size_t align = kMemAlign);   // NO_MEMORY, INVALID_ARG (0 or > pool)
     Status    release(MemHandle h, SessionId owner);                          // NOT_OWNER if owner differs
     void      releaseAll(SessionId owner);
```
`unit_tests`: OK (215 tests, 215 ran, 926 checks, 0 ignored, 0 filtered out, 2 ms)
`unit_tests_wrap`: OK (3 tests, 3 ran, 18 checks, 0 ignored, 0 filtered out, 0 ms)

</details>

<details><summary><b>H1</b> Header stops including what tests relied on (🟥 compiler)</summary>

```diff
diff --git a/include/cvaccel/dispatcher.hpp b/include/cvaccel/dispatcher.hpp
--- a/include/cvaccel/dispatcher.hpp
+++ b/include/cvaccel/dispatcher.hpp
@@ -6,10 +6,10 @@
 #include "cvaccel/device.hpp"
 #include "cvaccel/request_queue.hpp"
 #include "cvaccel/memory_pool.hpp"
-#include "cvaccel/session_manager.hpp"
-#include "cvaccel/perf_monitor.hpp"
 
 namespace cvaccel {
+class SessionManager;
+class PerfMonitor;
 
 // Moves queued requests to free cores and turns hardware completions into client wake-ups.
 // Not thread-safe by itself: the service holds its mutex around every call; onCompletion() is called
diff --git a/src/dispatcher.cpp b/src/dispatcher.cpp
--- a/src/dispatcher.cpp
+++ b/src/dispatcher.cpp
@@ -1,4 +1,6 @@
 #include "cvaccel/dispatcher.hpp"
+#include "cvaccel/session_manager.hpp"
+#include "cvaccel/perf_monitor.hpp"
 #include <vector>
 
 namespace cvaccel {
```
First errors:
```
tests/dispatcher_test.cpp:60: aggregate ‘cvaccel::SessionManager sessions’ has incomplete type and cannot be defined
tests/dispatcher_test.cpp:61: aggregate ‘cvaccel::PerfMonitor perf’ has incomplete type and cannot be defined
tests/dispatcher_test.cpp:81: aggregate ‘cvaccel::SessionManager sessions’ has incomplete type and cannot be defined
tests/dispatcher_test.cpp:82: aggregate ‘cvaccel::PerfMonitor perf’ has incomplete type and cannot be defined
tests/dispatcher_test.cpp:99: aggregate ‘cvaccel::SessionManager sessions’ has incomplete type and cannot be defined
tests/dispatcher_test.cpp:100: aggregate ‘cvaccel::PerfMonitor perf’ has incomplete type and cannot be defined
```
`unit_tests`: not built
`unit_tests_wrap`: OK (3 tests, 3 ran, 18 checks, 0 ignored, 0 filtered out, 0 ms)

</details>

<details><summary><b>H2</b> Namespace renamed (production updated) (🟥 compiler)</summary>

```diff
diff --git a/include/cvaccel/dispatcher.hpp b/include/cvaccel/dispatcher.hpp
--- a/include/cvaccel/dispatcher.hpp
+++ b/include/cvaccel/dispatcher.hpp
@@ -16,18 +16,18 @@ namespace cvaccel {
 // by the service's completion handler, also under the mutex.
 class Dispatcher {
 public:
-    Dispatcher(hw::IAccelBlock& hw, os::IDevice& dev, RequestQueue& q, MemoryPool& pool, SessionManager& sm, PerfMonitor& perf);
+    Dispatcher(hwif::IAccelBlock& hw, os::IDevice& dev, RequestQueue& q, MemoryPool& pool, SessionManager& sm, PerfMonitor& perf);
     // submits as many queued requests as the block accepts; returns how many were started
     unsigned pump();
     // hardware completion for one job: perf record, session bookkeeping, wake-up ioctl. Returns INVALID_ARG for an unknown job.
-    Status   onCompletion(const hw::JobResult& res);
+    Status   onCompletion(const hwif::JobResult& res);
     // a session is closing: its running jobs stay in flight but will not wake anybody; queued ones are cancelled (wake with CANCELLED)
     unsigned cancelSession(SessionId session);
     unsigned inFlight() const { return static_cast<unsigned>(running_.size()); }
     bool     isRunning(RequestId id) const { return running_.count(id) != 0; }
 private:
     Status   start(Request& r);
-    hw::IAccelBlock& hw_; os::IDevice& dev_; RequestQueue& queue_; MemoryPool& pool_; SessionManager& sessions_; PerfMonitor& perf_;
+    hwif::IAccelBlock& hw_; os::IDevice& dev_; RequestQueue& queue_; MemoryPool& pool_; SessionManager& sessions_; PerfMonitor& perf_;
     std::unordered_map<RequestId, Request> running_;     // jobs handed to the hardware
 };
 
diff --git a/include/cvaccel/hw_block.hpp b/include/cvaccel/hw_block.hpp
--- a/include/cvaccel/hw_block.hpp
+++ b/include/cvaccel/hw_block.hpp
@@ -3,7 +3,7 @@
 #include <functional>
 #include "cvaccel/types.hpp"
 
-namespace cvaccel::hw {
+namespace cvaccel::hwif {
 
 struct JobDesc {
     uint32_t jobId;                    // == RequestId
diff --git a/include/cvaccel/service.hpp b/include/cvaccel/service.hpp
--- a/include/cvaccel/service.hpp
+++ b/include/cvaccel/service.hpp
@@ -24,14 +24,14 @@ struct GetStatsArgs     { SessionId session; uint64_t outCount; uint64_t outAvgL
 // The base app: one instance per SoC. handle() is the ioctl entry point for every client command.
 class CvAccelService {
 public:
-    CvAccelService(hw::IAccelBlock& hw, os::IDevice& dev);
+    CvAccelService(hwif::IAccelBlock& hw, os::IDevice& dev);
     ~CvA
```
First errors:
```
tests/wrap/dispatcher_wrap_test.cpp:9: ‘hw’ has not been declared
tests/wrap/dispatcher_wrap_test.cpp:9: expected ‘{’ before ‘IAccelBlock’
tests/wrap/dispatcher_wrap_test.cpp:10: expected primary-expression before ‘public’
tests/wrap/dispatcher_wrap_test.cpp:10: expected ‘}’ before ‘public’
tests/wrap/dispatcher_wrap_test.cpp:12: virt-specifiers in ‘isBusy’ not allowed outside a class definition
tests/wrap/dispatcher_wrap_test.cpp:12: non-member function ‘bool {anonymous}::isBusy(cvaccel::CoreType)’ cannot have cv-qualifier
```
`unit_tests`: not built
`unit_tests_wrap`: not built

</details>

<details><summary><b>H3</b> Function moved to a new source file (🟧 linker)</summary>

```diff
diff --git a/include/cvaccel/perf_monitor.hpp b/include/cvaccel/perf_monitor.hpp
--- a/include/cvaccel/perf_monitor.hpp
+++ b/include/cvaccel/perf_monitor.hpp
@@ -37,6 +37,7 @@ public:
     uint64_t totalCount() const;
     std::string report() const;                       // human-readable, one line per core
     void     reset();
+    std::string report_moved() const;
     // integrity rules, exposed for testing
     static bool timestampsOk(const PerfRecord& r);    // queued <= started <= finished, finished > 0
     static bool bytesOk(const PerfRecord& r);         // 0 < bytes <= allocated
diff --git a/src/perf_monitor.cpp b/src/perf_monitor.cpp
--- a/src/perf_monitor.cpp
+++ b/src/perf_monitor.cpp
@@ -54,7 +54,7 @@ uint64_t PerfMonitor::totalCount() const {
     return total;
 }
 
-std::string PerfMonitor::report() const {
+std::string PerfMonitor::report_moved() const {
     std::string out;
     for (unsigned i = 0; i < kCoreCount; ++i) {
         const PerfStats& s = perCore_[i];
```
Link:
```
undefined reference to `cvaccel::PerfMonitor::report[abi:cxx11]() const'
undefined reference to `cvaccel::PerfMonitor::report[abi:cxx11]() const'
undefined reference to `cvaccel::PerfMonitor::report[abi:cxx11]() const'
```
`unit_tests`: not built
`unit_tests_wrap`: OK (3 tests, 3 ran, 18 checks, 0 ignored, 0 filtered out, 0 ms)

</details>

<details><summary><b>W1</b> Strict wrap stubs linked into the existing test binary (🟨 tests)</summary>

```diff
diff --git a/tests/CMakeLists.txt b/tests/CMakeLists.txt
--- a/tests/CMakeLists.txt
+++ b/tests/CMakeLists.txt
@@ -24,7 +24,8 @@ set(UT_CODE_UNDER_TEST
   ${CMAKE_SOURCE_DIR}/src/service.cpp
   ${CMAKE_SOURCE_DIR}/src/session_manager.cpp
 )
-add_executable(unit_tests ${UT_SOURCES} ${UT_CODE_UNDER_TEST})
+add_executable(unit_tests ${UT_SOURCES} ${UT_CODE_UNDER_TEST} ${CMAKE_CURRENT_SOURCE_DIR}/stubs/cvaccel_wrap_stubs.cpp)
+target_link_options(unit_tests PRIVATE "LINKER:--wrap=_ZN7cvaccel11PerfMonitor6recordERKNS_10PerfRecordE" "LINKER:--wrap=_ZNK7cvaccel10MemoryPool8physAddrEj")
 target_include_directories(unit_tests PRIVATE ${CMAKE_SOURCE_DIR}/client/include ${CMAKE_SOURCE_DIR}/include ${CMAKE_CURRENT_SOURCE_DIR}/mocks)
 target_link_libraries(unit_tests PRIVATE ${CPPUTEST_EXT} ${CPPUTEST_LIB} Threads::Threads)
 target_compile_options(unit_tests PRIVATE -Wall -Wextra)
```
`unit_tests`: Errors (74 failures, 215 tests, 215 ran, 855 checks, 0 ignored, 0 filtered out, 5 ms)<br>`TEST(CvAccelService, PerfMonitorRecord_IntegrityNotOk_ReturnsIntegrity)`<br>`TEST(CvAccelService, PerfMonitorRecord_IntegrityOk_ReturnsOk)`<br>`TEST(CvAccelService, PerfMonitorRecord_CoreIndexOutOfRange_SkipsPerCoreAccumulation)`<br>`TEST(CvAccelService, PerfMonitorRecord_CoreIndexWithinRange_AccumulatesPerCoreStats)`<br>`TEST(CvAccelService, PerfMonitorRecord_IntegrityOk_IntegrityErrorsStayZero)`<br>`TEST(CvAccelService, PerfMonitorRecord_IntegrityNotOk_IncrementsIntegrityErrors)`<br>`TEST(CvAccelService, MemoryPoolAllocate_GapAtStartFits_PlacesBeforeFirstBlock)`<br>`TEST(CvAccelService, MemoryPoolAllocate_NoFittingGapAmongBlocks_PlacesAfterLast)`
```
Mock Failure: Unexpected call to function: PerfMonitor::record::PerfMonitor::record
Mock Failure: Unexpected call to function: PerfMonitor::record::PerfMonitor::record
Mock Failure: Unexpected call to function: PerfMonitor::record::PerfMonitor::record
```
`unit_tests_wrap`: OK (3 tests, 3 ran, 18 checks, 0 ignored, 0 filtered out, 0 ms)

</details>

<details><summary><b>W2</b> Wrapped C++ function gets a defaulted parameter (mangled name changes) (🟧 linker)</summary>

```diff
diff --git a/include/cvaccel/memory_pool.hpp b/include/cvaccel/memory_pool.hpp
--- a/include/cvaccel/memory_pool.hpp
+++ b/include/cvaccel/memory_pool.hpp
@@ -24,7 +24,7 @@ public:
     Status    release(MemHandle h, SessionId owner);                          // NOT_OWNER if owner differs
     void      releaseAll(SessionId owner);
     const MemBlock* find(MemHandle h) const;
-    uint64_t  physAddr(MemHandle h) const;                                     // 0 if unknown
+    uint64_t  physAddr(MemHandle h, bool strict = false) const;                                     // 0 if unknown
     uint8_t*  map(MemHandle h);                                                // nullptr if unknown or no virt base
     size_t    bytesInUse() const;
     size_t    bytesInUse(SessionId owner) const;
diff --git a/src/memory_pool.cpp b/src/memory_pool.cpp
--- a/src/memory_pool.cpp
+++ b/src/memory_pool.cpp
@@ -61,7 +61,8 @@ const MemBlock* MemoryPool::find(MemHandle h) const {
     return nullptr;
 }
 
-uint64_t MemoryPool::physAddr(MemHandle h) const {
+uint64_t MemoryPool::physAddr(MemHandle h, bool strict) const {
+    (void)strict;
     const MemBlock* b = find(h);
     return b ? physBase_ + b->offset : 0;
 }
```
Link:
```
undefined reference to `cvaccel::MemoryPool::physAddr(unsigned int) const'
error: ld returned 1 exit status
```
`unit_tests`: OK (215 tests, 215 ran, 926 checks, 0 ignored, 0 filtered out, 2 ms)
`unit_tests_wrap`: not built

</details>

<details><summary><b>W3</b> Wrapped function moved inline into its header (🟨 tests)</summary>

```diff
diff --git a/include/cvaccel/memory_pool.hpp b/include/cvaccel/memory_pool.hpp
--- a/include/cvaccel/memory_pool.hpp
+++ b/include/cvaccel/memory_pool.hpp
@@ -24,7 +24,7 @@ public:
     Status    release(MemHandle h, SessionId owner);                          // NOT_OWNER if owner differs
     void      releaseAll(SessionId owner);
     const MemBlock* find(MemHandle h) const;
-    uint64_t  physAddr(MemHandle h) const;                                     // 0 if unknown
+    uint64_t  physAddr(MemHandle h) const { const MemBlock* b = find(h); return b ? physBase_ + b->offset : 0; }                                     // 0 if unknown
     uint8_t*  map(MemHandle h);                                                // nullptr if unknown or no virt base
     size_t    bytesInUse() const;
     size_t    bytesInUse(SessionId owner) const;
diff --git a/src/memory_pool.cpp b/src/memory_pool.cpp
--- a/src/memory_pool.cpp
+++ b/src/memory_pool.cpp
@@ -61,10 +61,6 @@ const MemBlock* MemoryPool::find(MemHandle h) const {
     return nullptr;
 }
 
-uint64_t MemoryPool::physAddr(MemHandle h) const {
-    const MemBlock* b = find(h);
-    return b ? physBase_ + b->offset : 0;
-}
 
 uint8_t* MemoryPool::map(MemHandle h) {
     const MemBlock* b = find(h);
```
`unit_tests`: OK (215 tests, 215 ran, 926 checks, 0 ignored, 0 filtered out, 2 ms)
`unit_tests_wrap`: Errors (1 failures, 3 tests, 3 ran, 10 checks, 0 ignored, 0 filtered out, 1 ms)<br>`TEST(DispatcherWrap, Start_UsesPhysAddrOfHandle_Mocked)`
```
expected <11255808 (0xabc000)>
```

</details>

<details><summary><b>W4</b> Function added to the --wrap list, stub not written (🟧 linker)</summary>

```diff
diff --git a/tests/CMakeLists.txt b/tests/CMakeLists.txt
--- a/tests/CMakeLists.txt
+++ b/tests/CMakeLists.txt
@@ -31,7 +31,7 @@ target_compile_options(unit_tests PRIVATE -Wall -Wextra)
 add_test(NAME unit_tests COMMAND unit_tests -v)
 
 # second binary: the shared --wrap + CppUMock stubs (C++ functions wrapped by mangled name)
-set(UT_WRAPPED _ZN7cvaccel11PerfMonitor6recordERKNS_10PerfRecordE _ZNK7cvaccel10MemoryPool8physAddrEj)
+set(UT_WRAPPED _ZNK7cvaccel10MemoryPool4findEj _ZN7cvaccel11PerfMonitor6recordERKNS_10PerfRecordE _ZNK7cvaccel10MemoryPool8physAddrEj)
 add_executable(unit_tests_wrap ${CMAKE_CURRENT_SOURCE_DIR}/wrap/dispatcher_wrap_test.cpp
   ${CMAKE_CURRENT_SOURCE_DIR}/stubs/cvaccel_wrap_stubs.cpp ${CMAKE_CURRENT_SOURCE_DIR}/main.cpp ${UT_CODE_UNDER_TEST})
 target_include_directories(unit_tests_wrap PRIVATE ${CMAKE_SOURCE_DIR}/client/include ${CMAKE_SOURCE_DIR}/include)
```
Link:
```
undefined reference to `__wrap__ZNK7cvaccel10MemoryPool4findEj'
undefined reference to `__wrap__ZNK7cvaccel10MemoryPool4findEj'
undefined reference to `__wrap__ZNK7cvaccel10MemoryPool4findEj'
```
`unit_tests`: OK (215 tests, 215 ran, 926 checks, 0 ignored, 0 filtered out, 3 ms)
`unit_tests_wrap`: not built

</details>

<details><summary><b>W5</b> Stub exists, --wrap flag dropped (🟧 linker)</summary>

```diff
diff --git a/tests/CMakeLists.txt b/tests/CMakeLists.txt
--- a/tests/CMakeLists.txt
+++ b/tests/CMakeLists.txt
@@ -31,7 +31,7 @@ target_compile_options(unit_tests PRIVATE -Wall -Wextra)
 add_test(NAME unit_tests COMMAND unit_tests -v)
 
 # second binary: the shared --wrap + CppUMock stubs (C++ functions wrapped by mangled name)
-set(UT_WRAPPED _ZN7cvaccel11PerfMonitor6recordERKNS_10PerfRecordE _ZNK7cvaccel10MemoryPool8physAddrEj)
+set(UT_WRAPPED _ZN7cvaccel11PerfMonitor6recordERKNS_10PerfRecordE)
 add_executable(unit_tests_wrap ${CMAKE_CURRENT_SOURCE_DIR}/wrap/dispatcher_wrap_test.cpp
   ${CMAKE_CURRENT_SOURCE_DIR}/stubs/cvaccel_wrap_stubs.cpp ${CMAKE_CURRENT_SOURCE_DIR}/main.cpp ${UT_CODE_UNDER_TEST})
 target_include_directories(unit_tests_wrap PRIVATE ${CMAKE_SOURCE_DIR}/client/include ${CMAKE_SOURCE_DIR}/include)
```
Link:
```
undefined reference to `__real__ZNK7cvaccel10MemoryPool8physAddrEj'
error: ld returned 1 exit status
```
`unit_tests`: OK (215 tests, 215 ran, 926 checks, 0 ignored, 0 filtered out, 4 ms)
`unit_tests_wrap`: not built

</details>

<details><summary><b>W6</b> Production stops calling the wrapped function (🟨 tests)</summary>

```diff
diff --git a/src/dispatcher.cpp b/src/dispatcher.cpp
--- a/src/dispatcher.cpp
+++ b/src/dispatcher.cpp
@@ -19,7 +19,7 @@ Status Dispatcher::start(Request& r) {
     hw::JobDesc job{};
     job.jobId = r.id;
     job.core = r.core;
-    job.physAddr = pool_.physAddr(r.mem);
+    job.physAddr = pool_.find(r.mem) ? pool_.find(r.mem)->offset : 0;
     job.bytes = r.bytes;
     for (unsigned i = 0; i < kConfigWords; ++i) job.config[i] = r.config[i];
 
```
`unit_tests`: OK (215 tests, 215 ran, 926 checks, 0 ignored, 0 filtered out, 4 ms)
`unit_tests_wrap`: Errors (1 failures, 3 tests, 3 ran, 10 checks, 0 ignored, 0 filtered out, 0 ms)<br>`TEST(DispatcherWrap, Start_UsesPhysAddrOfHandle_Mocked)`
```
expected <11255808 (0xabc000)>
```

</details>

<details><summary><b>X1</b> C function gets a new parameter; stub declares its own `__real_` prototype (🟨 tests)</summary>

```diff
diff --git a/hal.c b/hal.c
--- a/hal.c
+++ b/hal.c
@@ -1,2 +1,2 @@
 #include "hal.h"
-int hal_read(int reg) { return reg * 10; }
+int hal_read(int reg, int bank) { return reg * 10 + bank * 1000; }
diff --git a/hal.h b/hal.h
--- a/hal.h
+++ b/hal.h
@@ -2,7 +2,7 @@
 #ifdef __cplusplus
 extern "C" {
 #endif
-int hal_read(int reg);
+int hal_read(int reg, int bank);
 int sensor_get(int reg);
 #ifdef __cplusplus
 }
diff --git a/sensor.c b/sensor.c
--- a/sensor.c
+++ b/sensor.c
@@ -1,2 +1,2 @@
 #include "hal.h"
-int sensor_get(int reg) { return hal_read(reg) / 2; }
+int sensor_get(int reg) { return hal_read(reg, 0) / 2; }
```
`unit_tests`: Errors (2 failures, 3 tests, 3 ran, 13 checks, 0 ignored, 0 filtered out, 0 ms)<br>`TEST(Sensor, Real)`<br>`TEST(Sensor, Spy)`

</details>

<details><summary><b>X2</b> Same change; stub declares `__real_`/`__wrap_` with `__typeof__(hal_read)` (🟥 compiler)</summary>

```diff
diff --git a/hal.c b/hal.c
--- a/hal.c
+++ b/hal.c
@@ -1,2 +1,2 @@
 #include "hal.h"
-int hal_read(int reg) { return reg * 10; }
+int hal_read(int reg, int bank) { return reg * 10 + bank * 1000; }
diff --git a/hal.h b/hal.h
--- a/hal.h
+++ b/hal.h
@@ -2,7 +2,7 @@
 #ifdef __cplusplus
 extern "C" {
 #endif
-int hal_read(int reg);
+int hal_read(int reg, int bank);
 int sensor_get(int reg);
 #ifdef __cplusplus
 }
diff --git a/sensor.c b/sensor.c
--- a/sensor.c
+++ b/sensor.c
@@ -1,2 +1,2 @@
 #include "hal.h"
-int sensor_get(int reg) { return hal_read(reg) / 2; }
+int sensor_get(int reg) { return hal_read(reg, 0) / 2; }
diff --git a/stubs/hal_wrap_stubs.cpp b/stubs/hal_wrap_stubs.cpp
--- a/stubs/hal_wrap_stubs.cpp
+++ b/stubs/hal_wrap_stubs.cpp
@@ -1,7 +1,7 @@
 // shared --wrap + CppUMock stub for the C function hal_read (project headers before CppUTest headers)
 #include "hal.h"
 #include "CppUTestExt/MockSupport.h"
-extern "C" int __real_hal_read(int reg);
+extern "C" __typeof__(hal_read) __real_hal_read, __wrap_hal_read;
 extern "C" int __wrap_hal_read(int reg) {
     mock("hal_read").actualCall("hal_read").withIntParameter("reg", reg);
     if (mock("hal_read").hasReturnValue()) return mock("hal_read").intReturnValue();
```
First errors:
```
stubs/hal_wrap_stubs.cpp:5: conflicting declaration of C function ‘int __wrap_hal_read(int)’
stubs/hal_wrap_stubs.cpp:8: too few arguments to function ‘int __real_hal_read(int, int)’
```
`unit_tests`: not built

</details>

<details><summary><b>X3</b> C function return type changed; stub not updated (no guard) (🟨 tests)</summary>

```diff
diff --git a/hal.c b/hal.c
--- a/hal.c
+++ b/hal.c
@@ -1,2 +1,2 @@
 #include "hal.h"
-int hal_read(int reg) { return reg * 10; }
+double hal_read(int reg) { return reg * 10.0; }
diff --git a/hal.h b/hal.h
--- a/hal.h
+++ b/hal.h
@@ -2,7 +2,7 @@
 #ifdef __cplusplus
 extern "C" {
 #endif
-int hal_read(int reg);
+double hal_read(int reg);
 int sensor_get(int reg);
 #ifdef __cplusplus
 }
diff --git a/sensor.c b/sensor.c
--- a/sensor.c
+++ b/sensor.c
@@ -1,2 +1,2 @@
 #include "hal.h"
-int sensor_get(int reg) { return hal_read(reg) / 2; }
+int sensor_get(int reg) { return (int)(hal_read(reg) / 2); }
```
`unit_tests`: Errors (1 failures, 3 tests, 3 ran, 13 checks, 0 ignored, 0 filtered out, 1 ms)<br>`TEST(Sensor, Mocked)`

</details>

