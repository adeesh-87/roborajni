# Learnings to check against a real codebase

Everything this skill learned on its test codebases, as one list. Each learning was measured (experiments, the
change-impact study) or is a documented tool behaviour. A codebase may confirm it, not have the situation at all, or
have already solved it its own way. SKILL-MAKER.md step 8c turns every row into a verdict for your codebase in
`KB_DIR/learnings.md`. Later tasks read that file, not this one.

Verdicts: `yes` (applies; the project rule says what agents do), `no` (the situation cannot happen here; say why),
`partly`, `unknown` (add a question). Evidence is a file:line, a command with its output, or a count.

| ID | Learning | Source | Check in your codebase |
|---|---|---|---|
| **Finding code** | | | |
| L01 | On small code, agents allowed to read and grep wrote better tests than index-only agents (32/36 builds, 77% branches vs 26/36 and 63%). The index wins on precision (callers: 0.95 vs grep 0.25 in C++) and should matter more as code grows. | graph-queries.md; SKILL-MAKER step 10 q6 | Size of the production code (`wc -l`); decide the read policy for test agents. |
| L02 | A name-based index (Graphify) confuses same-named methods of different classes in C++ and misses constructor calls. | graph-queries.md | `spotcheck.py` lines in notes.md; count classes sharing method names. |
| L03 | clangd misses macros in symbol search, calls into `-isystem` headers, and TEST callers in call hierarchy (references find them); it counts a function passed as a pointer as a call. | graph-queries.md | Macro-heavy code? Vendored code included with `-isystem`? (`grep -c isystem compile_commands.json`) |
| L04 | The compile DB must contain the test files, or the index cannot link tests to code. | SKILL-MAKER step 3 | `grep -c '"file".*test' compile_commands.json` |
| L05 | For C++, a test writer needs the namespace, the declaring header and every pure virtual of an interface; name-based graphs do not show them, the header or clangd `hover` does. | graph-queries.md | Namespaces and interfaces in the code? |
| **CppUTest** | | | |
| L06 | Project and standard headers go BEFORE CppUTest headers: CppUTest redefines `new`/`delete`/`malloc`. | tools/cpputest.md | Include order in the exemplar and the stub files. |
| L07 | Teardown must call `mock().checkExpectations()` and `mock().clear()`; the leak detector counts mock allocations. | tools/errors/cpputest.md | `mock().clear` in the fixtures. |
| L08 | `expect` and `actual` parameter types must match (cast both); struct parameters need a comparator. | tools/errors/cpputest.md | `withParameterOfType`, `installComparator` in tests. |
| L09 | The `...OrDefault` return helpers hide a missing `andReturnValue`: the mock returns 0 silently. | tools/errors/cpputest.md | Which return helpers the stubs use. |
| L10 | CppUMock does not check call order unless `strictOrder()`; a reordered call passes (B8). | change-impact.md | `strictOrder` in tests. |
| L11 | `malloc` leaks are reported only when `MemoryLeakDetectorMallocMacros.h` is force-included; `new` leaks always are. | tools/errors/cpputest.md | Forced includes in the test build; leak detection disabled anywhere? |
| L12 | `UT_PTR_SET` swaps a function pointer and restores it after the test. | tools/cpputest.md, test-seams.md B3/C1 | Function pointers or ops tables in the code. |
| **Test seams** | | | |
| L13 | One technique per need (access, replace, per-test, hardware, state) per project, recorded and never mixed. | test-seams.md | `ut seams` detection output; `workarounds.py`. |
| L14 | State leaks between tests unless setup re-initialises it (E4); `-r2` finds leaks, `-p` isolates each test. | test-seams.md E1-E4 | File-static state; reset functions; `codemap.py` global state. |
| **Shared `--wrap` stubs** | | | |
| L15 | Strict stubs: a test that wants the real function must say so (`mock("fn").ignoreOtherCalls()` or a group-level ignore), else "Unexpected call". | test-seams.md C2/C3 | Stub mode (`expectedCallsLeft` = lenient). |
| L16 | Every parameter a stub passes with `withParameter` must be in each expectation, or the expectation uses `ignoreOtherParameters()`. | test-seams.md C3 | Stub bodies and one test using each. |
| L17 | C++ functions are wrapped by mangled name. A signature change leaves the old name: link error naming the old signature (W2). | change-impact.md W2 | C++ names in the wrap list; `wrapcheck.py`. |
| L18 | `--wrap` redirects only undefined references: calls to inline or template functions, and calls from the object file that defines the function, bypass the stub silently (W3). | change-impact.md W3, wrapcheck.py | `wrapcheck.py` "inline / weak"; wrapped functions called inside their own file. |
| L19 | C stubs declared with `__typeof__(fn)` turn a signature change into a compile error; hand-written prototypes pass garbage (X1-X3). | change-impact.md X1-X3 | `wrapcheck.py` "unguarded C stub". |
| L20 | A wrap flag without a stub, or a stub without a flag, is a link error (W4, W5): check the list against the stubs before building. | change-impact.md W4/W5 | `wrapcheck.py`. |
| L21 | Linking strict stubs into an existing binary fails every test that reaches a wrapped function (W1: 74 of 215). | change-impact.md W1 | Are stubs per binary or shared by all? |
| **Change impact** | | | |
| L22 | Structural changes (signatures, fields, constructors, interfaces) fail to compile; references predict the broken test files, except namespace renames (text search). | change-impact.md | Your study (SKILL-MAKER step 11). |
| L23 | Behaviour changes are caught only by tests that pin the value; the exact set is the TESTs that execute the changed lines. Never update an expected value without asking "intended or bug?". | change-impact.md | Your study. |
| L24 | Silent changes: new branches (only diff branch coverage shows them), interaction changes (only strict mocks), wider or narrower types, constants, default arguments. | change-impact.md | Your study. |
| L25 | Test-side traps: literal values instead of constants (T9), positional struct init (T3), tables sized by a count (T6), an explicit test source list (H3), hand-written fakes of interfaces (V1-V5). | hazards.py | `hazards.py` lines. |
| **Coverage** | | | |
| L26 | The official measure (usually CTC++) decides; clang 18 MC/DC is a local stand-in that agents can run. Cross-check a sample before trusting it. Coverage builds use `-O0`. | tools/llvm-mcdc.md, tools/ctc.md | Official tool, target, where it runs. |
| L27 | clang MC/DC limits: at most 6 conditions per decision, constant-folded conditions, macros reported at their definition, templates per instantiation. | tools/llvm-mcdc.md | "exceeds max" count from the MC/DC build log. |
| L34 | gcov: delete `.gcda` before a run; exclude throw branches; parallel runs need separate build folders. | tools/errors/gcov-lcov.md | Coverage scripts in the repo. |
| **Host builds of embedded code** | | | |
| L28 | Target compiler keywords and intrinsics (`__IO`, `__irq`, `__packed`, `__disable_irq`) must be defined away for the host build; code under `#ifdef TARGET` is not what the host tests run. | test-seams.md D* | `workarounds.py` "compiler keywords", "host shims". |
| L29 | Registers and time must be faked: registers redirected to RAM (D1/D2), tick and delay functions stubbed. | test-seams.md D1-D3 | `workarounds.py` "register fakes", "time and delay stubs". |
| L30 | C headers included from C++ tests need `extern "C"`; without it, the link error shows a C++ signature. | tools/errors/build-systems.md | How tests include C headers. |
| L31 | Sanitizers in the test build find memory bugs the asserts miss; note which tests they exclude. | - | `-fsanitize` in the test build. |
| L32 | The test link must fail on real errors: `--allow-multiple-definition` or `--unresolved-symbols` hide them. | tools/errors/build-systems.md | `workarounds.py` "loosened link". |
| L33 | Ignored or disabled tests are known problems: each needs a reason, or it rots. | - | `IGNORE_TEST` count and reasons. |
| **Building and asking** | | | |
| L35 | Build with keep-going (`ninja -k 0`, `make -k`) to see every error; fix the first one first. | tools/errors/build-systems.md | The recorded build command. |
| L36 | Ask at most 8 questions in one message, each with a default; record answers where they belong. | SKILL-MAKER step 10 | - |
