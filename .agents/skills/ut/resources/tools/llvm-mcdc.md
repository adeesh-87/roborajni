# MC/DC with clang 18+ (llvm-cov): measure, find the missing test vectors, raise it

Use it when:
- the task needs MC/DC and clang 18 or newer is available (for host unit tests);
- the project's MC/DC tool (e.g. CTC++) is not available where the agent works: clang is the stand-in for iterating, and
  the project tool stays the acceptance measure (see "Relation to CTC++" below);
- a fast MC/DC loop is wanted: measuring takes seconds and the gap list says which condition values each missing test
  needs.

## Build, run, merge
```sh
# CMake (a separate build dir; the unit-test target unchanged)
CC=clang CXX=clang++ cmake -S . -B build-mcdc -G Ninja -DBUILD_UNIT_TESTS=ON \
  -DCMAKE_C_FLAGS="-O0 -fprofile-instr-generate -fcoverage-mapping -fcoverage-mcdc" \
  -DCMAKE_CXX_FLAGS="-O0 -fprofile-instr-generate -fcoverage-mapping -fcoverage-mcdc"
cmake --build build-mcdc --target unit_tests
# Make / scripts: add the three -f flags to CFLAGS/CXXFLAGS and to the link command of the test program
rm -f build-mcdc/*.profraw
LLVM_PROFILE_FILE="build-mcdc/ut-%p.profraw" build-mcdc/tests/unit_tests      # %p: one file per process (CppUTest -p forks)
llvm-profdata merge -sparse build-mcdc/*.profraw -o build-mcdc/ut.profdata
```
Instrument only the code under test when the build allows it (a per-target option); the report can also be limited to
the code paths: `llvm-cov report <binary> -instr-profile=ut.profdata -show-mcdc-summary src/*.c`.

## Gaps as test instructions
```sh
I="$SKILL_DIR/resources/scripts/index.sh"; GD="$KB_DIR/index"
"$I" cov-import "$GD" --llvm build-mcdc/ut.profdata --object build-mcdc/tests/unit_tests   # repeat --object per binary
"$I" uncovered "$GD" <FUNCTION or FILE>
```
`cov-import` prints `MC/DC: 23/41 conditions shown independent in 20 decisions`. `uncovered` gives one line per
condition that is not shown independent, with the test that completes it:
```
L17 MC/DC 1/2 in (bytes == 0 || bytes > poolBytes_): `bytes > poolBytes_` not shown independent: add a test with
    `bytes == 0` FALSE, `bytes > poolBytes_` TRUE -> decision TRUE
    (pairs with an existing run: `bytes == 0` FALSE, `bytes > poolBytes_` FALSE -> decision FALSE)
```
- "not evaluated" means short-circuited: any value works.
- "add two tests" is printed when no existing run can be one half of the pair.
- The tool computes the vectors from the decision's own source text and all vectors its short-circuit evaluation can
  produce, and pairs them the way llvm-cov does.
- `ut coverage` turns these lines into work items (category G); the plan writes one test case per line.
- Choose inputs that make each condition take the listed value; the expected result of the test is what the code
  does for those inputs (never change production code to reach MC/DC unless Config allows it).
- The plain report, if needed: `llvm-cov show <binary> -instr-profile=ut.profdata -show-mcdc src/file.c`.

## Limits of clang 18 (checked with clang 18.1.3)
| Case | What clang does | What the tool does |
|---|---|---|
| a decision with more than 6 conditions | not instrumented (compile warning `number of conditions (N) exceeds max (6)`) | `uncovered` lists it as "not measured by clang 18": derive its pairs by hand |
| a condition that is a compile-time constant (`sizeof(int) > 8 && x`) | "constant folded": the decision can never reach 100% | listed as "not a test task; justify in the review" |
| a decision inside a macro | reported at the macro definition, with the macro's parameter names | keyed at the line that uses the macro when only one use exists |
| template functions | one decision per instantiation | merged per source location |
| `!(a && b)` | the decision is the inner `a && b`; outcomes refer to it | shown as written |
| `&&` / `||` outside if/while/for | also decisions: assignments, `return`, `?:`, function arguments | same |
| single-condition decisions | not MC/DC decisions (branch coverage covers them) | normal outcome gaps |

## Relation to CTC++ (MC/DC measured on the user's side)
MC/DC is a property of the test inputs, not of the compiler. A test that shows `bytes > poolBytes_` independent under
clang does the same under any tool that measures the same decision with a compatible MC/DC rule. Tests raised with clang
therefore carry over to CTC++, except where the two tools differ in these points. Confirm each point once per project:
1. **Which expressions are decisions.** clang counts every `&&`/`||` expression with 2–6 conditions, including
   assignments, returns and arguments. A tool that counts only control statements sees fewer decisions; that costs
   nothing.
2. **The pairing rule.** clang accepts a pair when the other conditions are equal or not evaluated in one of the runs
   (short-circuit). If the project tool is set to a stricter MC/DC variant, some clang pairs may not count there: add the
   missing vectors it reports.
3. **Decisions with more than 6 conditions.** CTC++ measures them; clang 18 does not (the table above). Plan them by hand.
4. **Constant conditions, macros, templates**: see the table.
5. **Same code.** The clang host build must compile the same sources with the same `#define`s as the CTC++ build.
   `#if TARGET`-dependent code changes the decisions.

Cross-check once per project, when CTC++ is available:
- Run the same test program under `ctc -i m`, report with `ctcpost ... -fmcdc` (see `ctc.md`).
- For 3–5 decisions, compare the conditions and which of them are MC/DC-covered.
- Record the result in KB `Commands` / `Conventions`: "clang MC/DC matches CTC++ (checked <date>)", or the deviations
  found. From then on, iterate with clang and accept with CTC++.

## Errors
| Error | Fix |
|---|---|
| `cannot find .../libclang_rt.profile-x86_64.a` | install the profile runtime: `apt install libclang-rt-18-dev` (same major as clang) |
| `unsupported MC/DC boolean expression; number of conditions (N) exceeds max (6)` | clang 18 limit; the decision is not measured (see above) |
| `llvm-profdata: ... unsupported instrumentation profile format version` | llvm-profdata / llvm-cov must match the clang major version (`llvm-cov-18`) |
| no `.profraw` written | the test program must exit normally; set `LLVM_PROFILE_FILE` to a writable path |
| `-fcoverage-mcdc` unknown | clang is older than 18: use branch coverage, or install clang 18+ |
| link errors with CppUTest built by gcc | clang++ on Linux uses libstdc++ by default, so this links; if the project forces libc++, rebuild CppUTest with it |
