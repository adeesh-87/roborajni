# Test seams: reaching hidden code and replacing collaborators (C/C++, CppUTest first)

Checked on GCC 13 + GNU ld + CppUTest (Linux): A2, A4, A6, C1, C2 (one test mocked and one real in the same binary)
and C4 build and pass as written below.

## Rule: one choice per need per project, then stick to it
The KB records the chosen technique per NEED in `Test seams (decided)` (kb.json `seams`). The ut tool detects
techniques already used by the existing tests and records them; otherwise the user picks once.
1. Before writing code that needs one of the needs below, look up KB `Test seams`. Decided → use exactly that
   technique, even where another looks easier here. Never mix a second technique into the project.
2. Not decided → do NOT improvise. Tool-driven: finish with `RESULT: PARTIAL needs seam <need>`. Agent-driven: ask
   the user once, showing the default and at most three alternatives from this file, then record the answer
   (`ut seams --set <need>=<ID>`, or KB `Test seams` by hand with date and `decided by: user`).
3. A decision changes ONLY when the user explicitly says so. Record the change with its date; do not rewrite
   existing tests to the new technique unless the user asks.
4. Techniques marked **production change** are offered only when Config allows changing production code.

| Need | What it is for | Default |
|------|----------------|---------|
| `access` | call `static` functions, anonymous-namespace code, `private`/`protected` members from a test | A1 |
| `replace` | replace a collaborator for a whole test binary | B1 (C) / B2 (C++ with interfaces) |
| `per-test` | mock a function in some tests and use the real one in others, same binary | C1 if a pointer exists, else C5 |
| `hardware` | registers, HAL macros, inline functions | D1 |
| `state` | reset file-static state between tests | E4 |

## access
**A1 test-through-public** (no seam). Drive the static/private code through its public callers; the card's `Callers`
and `index.sh refs` show the path. Limit: deep branches can need long setups.

**A2 include-source.** The test file includes the file under test, so the test's translation unit sees its statics,
anonymous namespace and file-static variables.
```cpp
// tests/sensor_internal_test.cpp
#include "../src/sensor.cpp"          // FIRST, before CppUTest headers (CppUTest redefines new/delete via macros)
#include "CppUTest/TestHarness.h"
TEST(SensorInternal, Scale_Negative) { LONGS_EQUAL(-5, scale(-10)); }   // scale() is static in sensor.cpp
```
- Build: that source must NOT also be linked into the same test binary (duplicate symbols). Remove it from the test
  target's sources, or give each include-source test file its own executable.
- A C file included into a C++ test compiles as C++ (void* casts, designated initializers fail). Include it in a
  small C shim instead: `tests/sensor_access.c` does `#include "../src/sensor.c"` and exports
  `int sensor_test_scale(int v) { return scale(v); }`; the C++ test calls the shim through an `extern "C"` header.
- Coverage: gcov maps the included file correctly. CTC++ does not instrument included source files by default:
  enable it in ctc.ini (include/exclude file settings) and check that `ctcpost` lists the file.
- C++ `private` members stay private: combine with A4, A5 or A6 if needed.

**A3 static-macro** (production change). `#ifdef UNIT_TEST` → `#define STATIC` else `#define STATIC static`;
production writes `STATIC int scale(int)`; tests compile with `-DUNIT_TEST` and declare the function. Limit: two files
with a same-named static now collide in the test binary.

**A4 private-public-define.** In the test file, after every system and third-party header:
`#define private public` / `#define protected public`, then include the class header (or `-Dprivate=public` on the
test target). No production change. Limits: formally undefined behaviour; link errors on MSVC (access is part of the
mangled name); members that are private only by default (no `private:` keyword in a `class`) stay private.

**A5 friend-test** (production change). The class declares `friend class SensorTest;` (gtest: `FRIEND_TEST`). The test
group's fixture class uses the access. Standard C++.

**A6 access-template.** Standard C++ lets an explicit template instantiation name private members; store the member
pointer and use it. No production change, no macros; verbose; one helper per member.
```cpp
template <typename Tag, typename Tag::type M> struct Rob { friend typename Tag::type get(Tag) { return M; } };
struct Sensor_scale { using type = int (Sensor::*)(int); friend type get(Sensor_scale); };
template struct Rob<Sensor_scale, &Sensor::scale>;
// in a test: (sensor.*get(Sensor_scale()))(-10)
```

**A7 test-subclass** (protected only). `class TestableSensor : public Sensor { public: using Sensor::scale; };`

## replace (whole test binary)
**B1 link-seam.** The test binary links a fake `.c/.cpp` defining the same functions instead of the real one (CMake:
a different source list per test executable). Most portable; granularity is one binary.

**B2 interface-injection** (C++; production design). The code depends on an abstract interface; tests pass a
CppUMock- or gMock-based fake. The index marks such calls `pure virtual; overridden by <doubles>`.

**B3 function-pointer-seam.** Calls go through a pointer or an ops table; a test swaps it with CppUTest
`UT_PTR_SET(ptr, fake)`, which restores the original after each test. Production change if no pointer exists.

**B4 weak-symbol** (production change). The real function is weak (`__attribute__((weak))`, usually via a macro); a
strong definition in the test binary replaces it. GCC/Clang/armcc; granularity is one binary.

**B5 macro-rename.** With A2: `#define hal_read fake_hal_read` before `#include "../src/sensor.c"` replaces the calls
of that translation unit only. Per test file.

**B6 header-seam.** A fake header with the same name earlier on the test include path (`-I tests/fakes` first)
replaces macros, inline functions and constants. Granularity is one binary.

## per-test (mocked in one test, real in another)
**C1 ut-ptr-set.** B3 with `UT_PTR_SET` in the tests that want the fake; the others see the real function.

**C2 linker-wrap.** Link the test binary with `-Wl,--wrap=fn`: every call to `fn` from OTHER object files goes to
`__wrap_fn`, and `__real_fn` is the original. The wrapper decides per test:
```cpp
extern "C" int __real_hal_read(int reg);
static bool g_mock_hal_read = false;                        // set in the tests that mock, reset in teardown
extern "C" int __wrap_hal_read(int reg) {
    if (!g_mock_hal_read) return __real_hal_read(reg);
    return mock().actualCall("hal_read").withIntParameter("reg", reg).returnIntValue();
}
```
CMake: `target_link_options(unit_tests PRIVATE "LINKER:--wrap=hal_read")`. Limits: GNU ld and lld only (not macOS
ld64, not MSVC; IAR/Keil/TI need their own linker options); calls from inside the same object file that defines `fn`
are NOT redirected; `static` functions cannot be wrapped; C++ functions need the mangled name
(`--wrap=_ZN6Sensor4readEv`, wrapper `__wrap__ZN6Sensor4readEv`); link-time optimisation can bypass it.

**C3 mock-with-passthrough.** A CppUMock fake that forwards to the real function unless the test expects calls; the
real one is reachable as `__real_fn` (C2) or `real_fn` (C4).

**C4 rename-copy.** Link a second, renamed copy of the real object: `objcopy --redefine-sym fn=real_fn sensor.o
sensor_real.o` (or compile it again with `-Dfn=real_fn`). The fake `fn` forwards to `real_fn` when not mocked.
Any linker; rename every exported symbol of that copy to avoid duplicates.

**C5 separate-binaries.** Tests that need the fake and tests that need the real function live in different
executables (B1 per binary). Portable and simple; more build targets.

**C6 gmock-delegate** (gMock only). `ON_CALL(mock, read).WillByDefault([&](int r) { return real.read(r); });`

**C7 ld-preload** (Linux, libc/shared-library functions). Define the function in the test binary and reach the real
one with `dlsym(RTLD_NEXT, "open")`. Per process.

## hardware
**D1 header-seam for registers.** The fake header turns `#define UART0_DR (*(volatile uint32_t*)0x4000C000)` into
`extern volatile uint32_t fake_UART0_DR; #define UART0_DR fake_UART0_DR`; tests set and check the variable.
**D2 overridable base address** (production change). `#ifndef UART0_BASE` in the header; tests compile with
`-DUART0_BASE=((uintptr_t)&fake_uart0)`.
**D3 hal-link-seam.** Vendor HAL functions replaced at link time (B1). Macros and inline functions cannot be link- or
wrap-mocked: use D1/B6 or B5.

## state
**E1 reset-via-include.** With A2 the test's `setup()` resets the file-static variables directly.
**E2 test-reset-function** (production change). `void sensor_reset_for_test(void)` under `UNIT_TEST`.
**E3 fork-per-test.** CppUTest `-p` runs each test in its own process (POSIX): no state leaks, slower.
**E4 re-init** (no seam). Call the module's public init in `setup()`.

## How the tool detects a technique already in use (the evidence recorded in the KB)
| ID | Evidence |
|----|----------|
| A2 | a test file includes a `.c`/`.cpp` file |
| A3 | `#define STATIC` / `#define PRIVATE` together with `UNIT_TEST` |
| A4 | `#define private public` or `-Dprivate=public` |
| A5 | `friend class ...Test` / `FRIEND_TEST` in code under test |
| B3 / C1 | `UT_PTR_SET` in tests |
| B4 | `__attribute__((weak))` or a `WEAK` macro in code under test |
| C2 | `--wrap=` in build files, or `__wrap_` / `__real_` in tests |
| C4 | `--redefine-sym` / `objcopy` in build files |
| E3 | `-p` in the test run command |
