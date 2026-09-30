# ut skill maker: fill the ut skill with real data from one codebase

Read this if you are an AI agent that was given this file, the `ut` skill folder, and a C/C++ repository. Your job:
make the skill ready for THAT repository by filling its knowledge base with facts you have verified in the
repository. Later agents, some of them small models, will write and fix unit tests from what you record, so
record facts, not guesses.

**You are done only when `python3 "$S/makercheck.py" "$KB_DIR" "$REPO"` prints `ALL PASS`** (step 10). It checks your
work and says what to fix for each FAIL. If it crashes, write the error into REPORT and do not report the work as done.

## Names
| Name | Meaning |
|---|---|
| `SKILL_DIR` | absolute path of the folder holding this file (it contains `SKILL.md`) |
| `S` | `$SKILL_DIR/resources/scripts` |
| `REPO` | absolute path of the repository root |
| `KB_DIR` | `$SKILL_DIR/resources/kb/<codebase-id>/` (step 1 prints the id) |
| `TASK` | a folder OUTSIDE the repository for the tool's task files, e.g. `~/ut-tasks/skill-maker` |
| `REPORT` | `$KB_DIR/SETUP-REPORT.md`: your running log and final report |

Write real absolute paths in every command; shell variables are not kept between separate commands.

## Rules
1. **Verify, then record.** A command goes into the KB only after you ran it and saw it succeed. A command you could not
   run is recorded as `UNVERIFIED: <reason>`. A fact carries its source: `file:line`, a command and its output, or
   "the user said".
2. **Unknown is an answer.** Write `unknown` and put the question in `REPORT` section "Questions". Never invent a path,
   flag, convention or number.
3. **Do not change the repository.** No edits to production code, tests or build files, and no commits. Build only in
   new folders (`build-ut*`). If a step needs a scratch test file, create it, build it, then delete it, and write in
   `REPORT` that you did.
4. **Ask little.** Collect every question until step 11 and ask them in ONE message: at most 8, each with a default in
   `[brackets]`. Ask earlier only when a step cannot continue (for example, you cannot build at all).
5. **Keep it short.** `kb.md` is generated and stays under 120 lines. Details go to `$KB_DIR/notes.md` and
   `$KB_DIR/modules/<name>.md`. Examples go to `$KB_DIR/exemplars/`, copied verbatim from the repository.
6. **Look at the code in this order:** the code index (`$S/index.sh ...`, after step 4), then the named lines of a file,
   then grep. Read whole files only for tests, stubs and build files.
7. After every step, append 1–3 lines to `REPORT`: what you did, what you verified, what is unknown.
8. **Never edit `kb.json` or `kb.md` by hand**: the tool writes them. Correct a command with
   `"$S/ut" baseline --task "$TASK" --yes --run "<cmd>"` (also `--build`, `--clean`, `--env-setup`); it replaces the
   stored command and verifies it. Record a seam with `"$S/ut" seams --task "$TASK" --set need=ID --by "<who>"`. Your
   own notes go to `notes.md`, `modules/`, `exemplars/` and REPORT.

## What you produce (definition of done)
| File | Made by | Must contain |
|---|---|---|
| `KB_DIR/kb.json`, `kb.md` | `ut init/baseline/kb` (steps 2–5) | profile, VERIFIED commands, conventions with counts, test seams, modules |
| `KB_DIR/exemplars/test.md` | step 5 | one real test file, verbatim, parts labelled, plus a skeleton |
| `KB_DIR/exemplars/mock.md` | step 5–6 | one real stub/mock verbatim, plus the test lines that drive it |
| `KB_DIR/exemplars/register.md` | step 5 | the exact lines that add a test file to the build |
| `KB_DIR/testscan.md`, `index/`, `modules/*.cards.md`, `diagrams/` | `ut kb` | generated |
| `KB_DIR/notes.md` | you | Toolchain, Build notes, Stubs, Coverage, Change hazards, Index spot-check (sections below) |
| `KB_DIR/modules/<name>.md` | you | purpose, files, tests, how to test, for the main modules |
| `REPORT` | you | log, verified vs unverified, questions and answers, final checklist |

---

## Step 0. Toolchain (what exists on this machine)
Run each command and record the version, or `missing`, in notes.md `## Toolchain`:
```sh
python3 --version; git --version; cmake --version | head -1; ninja --version; make --version | head -1
gcc --version | head -1; g++ --version | head -1; clang --version | head -1
llvm-cov --version | head -2; llvm-profdata --version | head -1; clangd --version | head -1
nm --version | head -1; c++filt --version | head -1; gcov --version | head -1; lcov --version; gcovr --version | head -1
ctc -h 2>&1 | head -2; ctcpost -h 2>&1 | head -2        # Testwell CTC++ (may be absent on this machine)
ls /usr/lib/x86_64-linux-gnu/libCppUTest* /usr/local/lib/libCppUTest* 2>/dev/null   # or where the repo vendors its test framework
```
- The skill needs Python 3.10+. Then run `"$S/index.sh" setup` once: it creates the skill's venv with the bundled
  Graphify.
- Cross compilers in the build (arm-none-eabi-gcc, IAR, ...): note them. Unit tests normally build for the host.
  Record which compiler the TEST build uses.

## Step 1. Identity
```sh
"$S/kb-id.sh" "$REPO"          # prints id=... ; KB_DIR = $SKILL_DIR/resources/kb/<id>
```
Create `REPORT` with a header: date, REPO, id, `git -C "$REPO" rev-parse --short HEAD`, branch.

## Step 2. Profile (paths, framework, build system)
Look before you ask. Collect, with evidence:
| Key | How to find it |
|---|---|
| `code_paths` | folders with the production `.c/.cpp` that unit tests target (not tests, mocks, third party, generated) |
| `header_paths` | include folders of that code |
| `test_paths`, `mock_paths` | folders with `TEST(`/`TEST_F(`/`void test_` files; folders named mock/mocks/stub/stubs/fake/fakes |
| `framework` | includes: `CppUTest/`, `gtest/`, `unity.h`, `cmock`, Parasoft `cpptest` |
| `mock_style` | CppUMock `mock().`, gMock `MOCK_METHOD`, CMock `_Expect`, hand-written fakes, `--wrap` stubs |
| `build_system`, `build_cmd`, `run_cmd`, `clean_cmd` | CMakeLists.txt / Makefile / project.yml; CI files (`.gitlab-ci.yml`, `Jenkinsfile`, `.github/workflows`) show the real commands |
| `compile_db` | `compile_commands.json` of the TEST build (step 3) |
| `coverage_tool` | CTC++ (`ctc`, `ctcwrap`, `MON.sym` in scripts), gcov/lcov, llvm-cov |
| `env_setup` | a script sourced before the build (toolchain paths, license servers) |

Write `$TASK/answers.json` and run the tool's first phase with it:
```json
{"request": "diff", "production_code": "no", "delete_tests": "ask", "commit": "no", "safe_run": "yes", "inputs": "none",
 "coverage": "no", "profile": {"code_paths": ["src"], "header_paths": ["include"], "test_paths": ["tests"],
 "mock_paths": ["tests/stubs"], "framework": "cpputest", "mock_style": "CppUMock + --wrap stubs", "build_system": "cmake",
 "build_cmd": "...", "run_cmd": "...", "clean_cmd": "...", "compile_db": "build-ut/compile_commands.json",
 "coverage_tool": "Testwell CTC++", "env_setup": "none"}}
```
```sh
mkdir -p "$TASK"; "$S/ut" init --task "$TASK" --repo "$REPO" --answers "$TASK/answers.json"
```
`init` prints the detected profile. Compare it with yours, and where they differ, trust the evidence you can cite.

## Step 3. Commands that work (build, run, one group, compile DB)
Make each one work in a NEW build folder and record the exact command:
1. **Build tests.** For CMake: `cmake -S <dir> -B build-ut -DCMAKE_EXPORT_COMPILE_COMMANDS=ON <options the CI uses>`,
   then `cmake --build build-ut -j`. For Make: `bear -- make <target>` writes `compile_commands.json` (install bear if
   allowed). No way to get one → record `compile_db: none`: the index then parses without the build's flags, which
   misses macros and `#if` branches. Say so in Build notes.
2. **Run all tests.** The run command must name the real binary path (`ls <path>` must succeed). Record the summary
   line exactly: `OK (215 tests, 215 ran, ...)` for CppUTest, `[  PASSED  ] 42 tests.` for gtest.
   **Several test executables:** the main one holds most test files. Put it in the run command, and list the others
   with their purpose in Build notes.
3. **Run one group or test.** CppUTest `-sg <Group>` / `-sn <Name>`; gtest `--gtest_filter=Group.*`; Unity: one
   executable per file.
4. **The compile DB must include the TEST files.** Check with
   `grep -c '"file".*test' build-ut/compile_commands.json`. Without them the index cannot see which tests call what.

Then let the tool verify and store them:
```sh
"$S/ut" baseline --task "$TASK" --yes
```
A wrong stored command (for example, the run command names a binary that does not exist): rerun with the corrected
one, e.g. `"$S/ut" baseline --task "$TASK" --yes --run "build-ut/tests/unit_tests"`, until it prints `tests: N/N passed`.
Anything that failed: record the first error and your diagnosis in notes.md `## Build notes`, and put a question in
REPORT. Do not "fix" build files in the repository.

## Step 4. Code index, and a spot-check of its answers
```sh
"$S/ut" kb --task "$TASK" --yes        # index, testscan, exemplar drafts, conventions, cards, diagrams, seams
"$S/index.sh" stats "$KB_DIR/index"
```
- The build output must say `preprocessed with compile flags`. Files reported as `not preprocessed` go to Build notes.
- **Spot-check the index before anyone trusts it:**
  ```sh
  python3 "$S/spotcheck.py" "$KB_DIR" "$REPO" <F1> <F2> <F3> <F4> <F5>
  ```
  Choose 5 production functions that tests call. In C++, include at least 2 methods whose name also exists in another
  class (`"$S/index.sh" defs "$KB_DIR/index" <short name>` shows 2+ definitions).
  - Paste the script's lines verbatim into notes.md `## Index spot-check`.
  - For each line that says `INDEX MAY MISS CALLERS`: read 2 of the listed TESTs, then add a line
    `confirmed: the index misses <N> TEST callers of <F> (<why, e.g. calls on a local object>)`, or `not confirmed: <why>`.
  - Any confirmed miss: add the line "C++: the index can miss callers of methods called on objects; confirm test
    callers with a text search" to KB Conventions.
  - Background: on other codebases, Graphify was near-perfect on C. In C++ it confused same-named methods of
    different classes, picked the wrong const overload, and missed constructor calls.

## Step 5. How tests are written here (exemplars and conventions)
`ut kb` drafted `testscan.md`, `exemplars/*.md` and KB `Conventions`. Check and complete them:
1. **Exemplar.** Choose it by these rules, in order:
   - it comes from the test executable with the most test files;
   - it uses the fixture, assert and double style that most test files use (testscan.md counts);
   - it is NOT a file that exists to test a special mechanism (wrap stubs, include-source, a timing harness), unless
     most test files do the same;
   - it is short, with 3–10 tests.
   Copy it verbatim, cut to at most 80 lines, with each part labelled in a comment column. The draft from `ut kb` is
   only a candidate: replace it when it breaks a rule.
2. **Register.** Record the exact lines that add a test file to the build, with `file:line`. Several test executables
   → describe which one a new test for module X joins.
3. **Conventions.** At most 12 lines, each with a count ("61 of 68 test names follow `<Func>_<Cond>_<Expected>`").
   Include:
   - the include order, because CppUTest's `new`/`delete` macros break standard headers included after it;
   - how `extern "C"` is used;
   - where fixtures reset state.
4. **Prove the skeleton compiles.**
   - Copy the skeleton into `tests/ut_skillmaker_smoke_test.*` with one trivial test, register it as register.md says,
     build and run the one group.
   - Then remove the file and the registration line: `git -C "$REPO" status --porcelain` must be empty again.
   - Record "skeleton builds: yes, <date>" in the exemplar header.

## Step 6. Stubs, mocks and test seams
### 6a. Test seams (one decision per need; read `resources/test-seams.md`)
`ut kb` recorded the techniques the existing tests already use. Check each with its evidence line and complete it:
```sh
"$S/ut" seams --task "$TASK"                 # shows the recorded decisions
```
A need with no evidence stays `not decided`. It goes into the questions (step 11) with exactly these defaults, never
"not needed":
| Need | Default | Question |
|---|---|---|
| access (static / private / anonymous namespace) | A1 test through the public callers | `access: which technique? [A1]` |
| replace (a collaborator, whole binary) | B1 link-seam (C), B2 interface injection (C++ with interfaces) | `replace: which technique? [B1 or B2]` |
| per-test (mock in one test, real in another) | C5 separate binaries (C1 if a function pointer exists) | `per-test: which technique? [C5]` |
| hardware (registers, HAL macros) | D1 register header seam | `hardware: which technique? [D1]` |
| state (file-static state between tests) | E4 call the public init in setup() | `state: which technique? [E4]` |
Never set a seam yourself. `ut seams --set` is only for the user's answer.

### 6b. Shared `--wrap` stubs (if the project uses `__wrap_` / `__real_`)
Inventory them in notes.md `## Stubs`:
- **Where they live:** stub files, and where the wrap list is (CMake variable, Makefile, linker script).
- **Consistency:**
  ```sh
  python3 "$S/wrapcheck.py" "$REPO" "$REPO/build-ut" --stubs <stub dir> [--stubs <dir2>]
  ```
  Record its output verbatim. It checks four things:
  - every `--wrap` has a stub, and every stub has a `--wrap`;
  - every wrapped symbol still exists (for C++, a changed signature changes the mangled name);
  - no wrapped function is inline or weak in the objects that call it (then the wrap is silently bypassed);
  - C stubs declare `__real_`/`__wrap_` with `__typeof__(fn)`.
  Findings are facts for the report. Do not fix them in the repository.
- **The mode each stub uses.** Decide it by commands, not by impression:
  ```sh
  grep -n "expectedCallsLeft" <stub files>          # any hit -> lenient; none -> strict
  grep -rn "ignoreOtherCalls" <test paths> | head   # how strict-mode tests ask for the real function
  grep -rn "ignoreOtherParameters" <test paths> | head
  ```
  Write `mode: strict` or `mode: lenient` in notes.md `## Stubs` with the grep evidence, then fill this table by
  reading 3 stubs and 3 tests that use them:
  | Question | Record |
  |---|---|
  | Strict or lenient? | Strict: `actualCall` always; tests that want the real function call `mock("<scope>").ignoreOtherCalls()`. Lenient: the stub checks `expectedCallsLeft()` first. |
  | Scope naming | `mock("fn")` per function, or one scope per module |
  | Parameters | Does the stub pass them (`withXxxParameter`)? Then every expectation lists them or adds `.ignoreOtherParameters()`. |
  | Return values | Which `...ReturnValue()` accessor per return type; how structs and enums are returned |
  | Output parameters | `withOutputParameter` in the stub + `withOutputParameterReturning` in tests? |
  | No-real functions | Stubs without `__real_` (hardware, OS): list them |
  | Teardown | `mock().checkExpectations(); mock().clear();` in every group, or a plugin |
- **Exemplar (required whenever the tests use any test double).** `exemplars/mock.md` holds one real stub verbatim,
  plus 3 excerpts from real tests, each copied with `file:line`:
  - a test that mocks it (expectation with a return value);
  - one that spies (expectation without a return value: the real function runs and the call is checked);
  - one that lets the real function run (`ignoreOtherCalls`).
  A kind that no test uses yet: write `none in the tests yet`. Never leave the file empty when doubles exist.
- **Other styles** (link-seam fakes, CMock, gMock, hand-written interface fakes): same inventory. Where are they, and
  is there one shared fake per interface or one per test file? `hazards.py` in step 8 lists the interface fakes.
  mock.md then holds one real fake verbatim, plus the test lines that set it up and check it.

## Step 7. Coverage and MC/DC
Read `resources/tools/ctc.md` and `resources/tools/llvm-mcdc.md` first.
1. **The project's official measure** (usually CTC++): find how it is run (CI, scripts, `ctc.ini`), and record the exact
   commands and instrumentation level (`-i m` for MC/DC) in KB Commands.
   - CTC++ installed here: run it once on the test build and record the TER totals.
   - Not installed: record the commands `UNVERIFIED: CTC++ not on this machine`.
2. **The local MC/DC stand-in (clang 18+).** Only if clang ≥ 18 and llvm-cov exist (step 0): build the TEST target in
   `build-mcdc` with `-O0 -fprofile-instr-generate -fcoverage-mapping -fcoverage-mcdc`. Save the build output:
   `cmake --build build-mcdc ... 2>&1 | tee "$TASK/mcdc-build.log"`. Then run, merge and import:
   ```sh
   LLVM_PROFILE_FILE="$REPO/build-mcdc/ut-%p.profraw" <test binary>
   llvm-profdata merge -sparse "$REPO"/build-mcdc/*.profraw -o "$REPO/build-mcdc/ut.profdata"
   "$S/index.sh" cov-import "$KB_DIR/index" --llvm "$REPO/build-mcdc/ut.profdata" --object <test binary>
   "$S/index.sh" uncovered "$KB_DIR/index" | head -40
   ```
   Record in notes.md `## Coverage`:
   - the build command;
   - the `MC/DC: x/y conditions` line;
   - the count of compile warnings `exceeds max (6)` (`grep -c "exceeds max" "$TASK/mcdc-build.log"`), written as
     `exceeds max (6) warnings: N`, and the file:line of each: decisions that clang 18 cannot measure and CTC++ will;
   - any `constant folded` conditions.
   If the build needs a flag or a library it does not have (for example `libclang-rt-18-dev` on Ubuntu), write the fix
   into Build notes.
3. **Cross-check** (llvm-mcdc.md, "Relation to CTC++"):
   - CTC++ available: compare 3–5 decisions and record "clang MC/DC matches CTC++: yes / deviations: ...".
   - Otherwise list those 5 decisions under "cross-check pending", as `src/x.cpp:93  (!blk || blk->owner != a.session)`,
     so a person with CTC++ can do it later. Take them from the `uncovered` lines: file from `(file:line)`, line from
     `L93`, and prefer decisions with 2+ conditions.

## Step 8. Change hazards (where a change breaks tests silently)
```sh
python3 "$S/hazards.py" "$REPO" --code <code paths> <header paths> --tests <test paths> <mock paths>
```
Paste the output into notes.md `## Change hazards`, then review each line:
- **Every line stays.** A false alarm keeps its line and gets `false alarm: <reason>` added, for example "the 64s in
  memory tests are sizes, not kMemAlign". Never delete a line, and never shorten the list to "the main ones".
- A true line gets `confirmed` plus 1 example from the code or the tests.
Each line tells a later diff task what to check:
- new source files → the test source list;
- a count that grows → sized tables;
- reordered struct fields → positional initialisers;
- a changed constant → literal values;
- a changed interface → fakes.

## Step 9. Modules
For the 5–10 most important production files (ask the user in step 11 if unclear; default: the largest files that have
tests), create `modules/<name>.md` from `resources/templates/module.md`:
- purpose in 1 line, from the header comment or docs, with its source;
- files, and test files (`"$S/index.sh" tests ...`);
- the cards file;
- "how to test": fixture, fakes and stubs used, seams, from the existing tests.
If a module is large or tricky (state machines, ISR/RTOS, protocol parsing, more than 40 functions), say so in REPORT:
`resources/templates/decompose-codebase.md` lets a stronger model write deeper notes later.

## Step 10. Validate what you made
First run the checker, and fix what it reports until it prints `ALL PASS`:
```sh
python3 "$S/makercheck.py" "$KB_DIR" "$REPO"
```
Then run each check below and record `PASS` / `FAIL: <why>` in REPORT:
```sh
"$S/index.sh" selftest                                   # the index tooling works on this machine
"$S/index.sh" card "$KB_DIR/index" <a production function>   # a card with decisions, calls, callers, tests
"$S/ut" status --task "$TASK"            # phases 1-3 done
wc -l "$KB_DIR/kb.md"                                     # <= 120
git -C "$REPO" status --porcelain                         # empty: the repository is unchanged
```
Also dry-run one real task to see what a test-writing agent would receive:
```sh
"$S/ut" discover --task "$TASK" --names <one production function> --yes
"$S/ut" scope --task "$TASK" --yes
"$S/ut" plan --task "$TASK" --yes
"$S/ut" run --task "$TASK" --dry-run      # writes prompts/*.md without calling an agent
```
Read the prompt. Every fact in it must be right: include lines, fixture, seam, stub names. Fix the KB where it is not,
never the prompt.

## Step 11. Questions for the user (ONE message)
Only what the files could not answer, at most 8 questions, each with a default. Typical ones:
1. Test seams not decided: "<need>: which technique? [<default from test-seams.md>]" (one line per need).
2. "Is `exemplars/test.md` (<file>) the style every new test should copy? [yes]"
3. Shared stubs: "Tests that want the real function call `mock("<fn>").ignoreOtherCalls()` (strict). Keep it? [yes]"
4. "Must every stub declare `__real_`/`__wrap_` with `__typeof__(fn)`? It turns C signature changes into compile
   errors. [yes, for new stubs]"
5. Coverage: "Official measure and target? [CTC++, MC/DC, 100 % of the changed code]" and "May agents use clang 18
   MC/DC locally as the stand-in? [yes]"
6. Test agents' access: "May test-writing agents read code files after asking the index first? [yes]". On small code,
   agents that could read wrote better tests (experiments/lsp-vs-graphify/RESULTS.md). The tool's default denies
   reading code; `ut run --agent` takes the command to use.
7. Hazards you could not settle (step 8).
8. Anything that failed to build or run (step 3).
Record each answer where it belongs:
- seams: `"$S/ut" seams --task "$TASK" --set need=ID` (the user's answer). If the user cannot answer now and you were told
  to go on with defaults: `... --set need=ID --by "default, not confirmed by the user"`;
- conventions: KB `Conventions (approved on <date>)`;
- everything else: notes.md.
Then record the answers in REPORT.

## Step 12. Final report
Finish `REPORT` with:
- **The last output of makercheck.py**, verbatim.
- **Checklist** (each ✓ or ✗ with the reason): toolchain recorded; profile; build, run and one-group commands verified;
  compile DB includes tests; index built and spot-checked; exemplar, register and mock verified by the smoke test;
  seams decided or asked; stubs checked (wrapcheck); coverage commands (official measure verified or UNVERIFIED;
  clang MC/DC baseline); hazards reviewed; modules; dry-run prompt correct; repository unchanged.
- **Unverified** items, each with what is needed to verify it.
- **Next**: "the skill is ready: start a task with `SKILL.md` (agent-driven) or `resources/scripts/ut init` (tool-driven)".

Keep the KB folder with the skill (`resources/kb/README.md` says how). Every later task reads it and adds to it.
