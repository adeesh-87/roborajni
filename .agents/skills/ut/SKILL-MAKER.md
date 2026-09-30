# ut skill maker: turn the ut skill into a skill for one real codebase

Read this if you are an AI agent that was given this file, the `ut` skill folder, and a C/C++ repository. Your job:
make the skill ready for THAT repository. Later agents, some of them small models, will write and fix unit tests
from what you record, so record facts, not guesses.

The result has three layers:
1. **What the skill already knows** (do not rewrite it): how to use the code index, clangd and llvm-cov; CppUTest and
   its pitfalls; test seams; shared `--wrap` stubs; what code changes do to tests. It is all in `resources/`, and
   `resources/learnings.md` lists every learning with a way to check it in a codebase. Read that list first:
   it tells you what to look for.
2. **What is true for this codebase** (you write it, in `KB_DIR`): commands, exemplars, conventions, the team's design
   choices for tests and stubs, the workarounds it already uses and why, a map of the code, a verdict on every
   learning, and the change-impact study re-run on this code with its own examples.
3. **The project skill** (you design it): a short `ut-<project>` skill next to `ut` that triggers on this project and
   says which KB file to read when. It also has project playbooks where the generic ones do not fit.

**You are done only when `python3 "$S/makercheck.py" "$KB_DIR" "$REPO"` prints `ALL PASS`** (step 13). It checks your
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
   new folders (`build-ut*`, `build-mcdc`). If a step needs a scratch test file, create it, build it, then delete it,
   and write in `REPORT` that you did. **Keep the build folders** when you finish: test-writing agents and
   `makercheck.py` use the binaries and objects in them. Never `rm -rf` them as a final cleanup.
4. **Ask little.** Collect every question until step 10 and ask them in ONE message: at most 8, each with a default in
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
9. **Every fact about this codebase goes into `KB_DIR`**, never into the generic files of `resources/`. A generic file
   that is wrong for this codebase gets a verdict in `learnings.md` (step 8c) or a project playbook (step 12).

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
| `KB_DIR/workarounds.md` | step 8b | every workaround and test design choice: where, why, rule for new tests, the error it prevents |
| `KB_DIR/learnings.md` | step 8c | a verdict with evidence for every learning in `resources/learnings.md` |
| `KB_DIR/codebase.md` | step 9 | the code map: `codemap.py` facts, plus purpose, domain words, rules and test mapping |
| `KB_DIR/study/`, `STUDY.md`, `change-impact.md` | step 11 | the change-impact study on this code, with lessons and findings |
| `<skills>/ut-<project>/SKILL.md`, `KB_DIR/playbooks/` | step 12 | the project skill and the project playbooks |
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
A need with no evidence stays `not decided`. It goes into the questions (step 10) with exactly these defaults, never
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
First read `$SKILL_DIR/resources/change-impact.md`: 46 kinds of change and what each did to the tests (compile
error, link error, failing test, crash, or nothing). The IDs in the scanner output (T3, T6, T9, H3, W3, ...) are its rows.
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

## Step 8b. Workarounds and design choices already made
The team has already fought the problems in `resources/learnings.md`. Find how, and why:
```sh
python3 "$S/workarounds.py" "$REPO" --code <code paths> <header paths> --tests <test paths> <mock paths> \
    --build <test build files and folders, CI scripts>
```
Create `$KB_DIR/workarounds.md` from `resources/templates/workarounds.md`:
- **One row per category line of the output.** Every category stays. A category that is not a workaround gets a row
  whose "Rule" says `not a workaround: <reason>`.
- **One more row per comment or commit in the output that explains a choice** not covered by a category row.
- **Where:** the file:line. Read the lines around it.
- **Why:** the comment next to it; otherwise the commit that added it: `git -C "$REPO" log -L <n>,<n>:<file> --format='%h %s' -n 3`,
  or `git -C "$REPO" log -S '<text>' --format='%h %s' -- <file>`. Nothing explains it → `unknown`, and a question.
- **Rule for new tests:** `copy`, `never`, or `ask`, plus what exactly to copy.
- **Error:** the exact message this workaround prevents or causes, from the commit, the comment, or the matching row
  of `resources/tools/errors/*.md`. Test agents search this file with the error text they get, so write the text as
  the tool prints it (`undefined reference to`, `Memory leak(s) found`, …).

## Step 8c. A verdict on every learning
```sh
python3 "$S/makercheck.py" --skeleton learnings > "$KB_DIR/learnings.md"
```
Fill every row from what you recorded in steps 3–8b. Columns: Applies (`yes`, `no`, `partly` or `unknown`), Evidence
(file:line, a command with its result, or a count) and Project rule (what agents do HERE).
- `yes` and `partly` need a rule an agent can follow, e.g. "new C stubs declare `__typeof__`; old ones stay as they
  are (the team's choice, question 4)". The project rule wins over the generic docs.
- `no` says why the situation cannot happen, e.g. "no C++ in the code paths: `find src -name '*.cpp' | wc -l` = 0".
- `unknown` goes into the questions; its evidence says what you looked at, e.g. "no CI file found".
- L22–L25 are settled by your own study: write `pending study` now and fill them after step 11.

## Step 9. The codebase map, and the main modules
The code map gives a test writer the code's shape in one file: its components, how they call each other, where a
change spreads, what is untested, and the rules the code relies on. It is built in two passes. First the facts the
index can count:
```sh
python3 "$S/codemap.py" "$KB_DIR" > "$KB_DIR/codebase.md"      # after the coverage import of step 7
```
The components must be the units the team talks about (directories, libraries, drivers). If they are not, re-run
with `--depth N` and say which depth in REPORT.

Then write the four sections marked `(agent)`. Every line ends with its source:
- **Purpose of each component:** one line per component row. Sources, in order: the file header comment of its main
  file, a README or doc in its folder, doxygen `@file` / `@brief`, the `card` of its entry points.
- **Domain words:** abbreviations and terms that appear in 3+ names or comments. Explain them from comments and docs.
  Terms you cannot explain go into ONE question.
- **Rules the code relies on:** look for asserts, "must" / "only" / "before" in comments, init functions, critical
  sections and locks, ISR or task context, `volatile`, ownership (who frees). Each rule gets the file:line that shows
  it and what a test must do about it, e.g. "call `uart_init()` in setup".
- **How the tests map to the code:** the test binaries and what each links (the link lines in the build folder);
  components that are tested only through others (TESTs reaching them, but no test file of their own); fixtures
  shared across files.

For C++, ask clangd what the index cannot show: the namespace and the header that provides a name, and the
implementations of an interface (every fake breaks when it changes):
```sh
python3 "$S/clangd.py" "$REPO" "$REPO/build-ut" warm                # once: clangd's index, in build-ut/.cache
python3 "$S/clangd.py" "$REPO" "$REPO/build-ut" hover <Class>        # "provided by <header>", namespace
python3 "$S/clangd.py" "$REPO" "$REPO/build-ut" impl <Iface::method> # implementations, fakes included
```
Keep `codebase.md` under 250 lines: a map, not a copy of the code.

Then, for the 5–10 most important production files (the hotspots and the components with the most TESTs, or what the
user names), create `modules/<name>.md` from `resources/templates/module.md`:
- purpose in 1 line, with its source;
- files, and test files (`"$S/index.sh" tests ...`);
- the cards file;
- "how to test": fixture, fakes and stubs used, seams, from the existing tests.
If a module is large or tricky (state machines, ISR/RTOS, protocol parsing, more than 40 functions), say so in REPORT:
`resources/templates/decompose-codebase.md` lets a stronger model write deeper notes later.

## Step 10. Questions for the user (ONE message)
Only what the files could not answer, at most 8 questions, each with a default. Typical ones:
1. Test seams not decided: "<need>: which technique? [<default from test-seams.md>]" (one line per need).
2. "Is `exemplars/test.md` (<file>) the style every new test should copy? [yes]"
3. Shared stubs: "Tests that want the real function call `mock("<fn>").ignoreOtherCalls()` (strict). Keep it? [yes]"
4. "Must every stub declare `__real_`/`__wrap_` with `__typeof__(fn)`? It turns C signature changes into compile
   errors. [yes, for new stubs]"
5. Coverage: "Official measure and target? [CTC++, MC/DC, 100 % of the changed code]" and "May agents use clang 18
   MC/DC locally as the stand-in? [yes]"
6. Test agents' access: "May test-writing agents read code files after asking the index first? [yes]". On small code,
   agents that could read wrote better tests (`resources/learnings.md` L01). The tool's default denies reading code;
   `ut run --agent` takes the command to use.
7. Workarounds whose reason you could not find (step 8b), in one question: "Why does <file:line> do <x>? [keep it,
   reason unknown]". Also: "Do agents need to know about any other workaround, for example in a wiki or CI? [no]"
8. Hazards, domain words or learnings you could not settle (steps 8, 8c, 9), and anything that failed to build or run.
Record each answer where it belongs:
- seams: `"$S/ut" seams --task "$TASK" --set need=ID` (the user's answer). If the user cannot answer now and you were told
  to go on with defaults: `... --set need=ID --by "default, not confirmed by the user"`;
- conventions: KB `Conventions (approved on <date>)`;
- workarounds and learnings: the row in `workarounds.md` / `learnings.md`, with "asked: <date>" as the source;
- everything else: notes.md.
Then record the answers in REPORT.

Ask the questions before step 11: the study runs for a while, and the user can answer meanwhile.

## Step 11. The change-impact study, on this codebase
`resources/change-impact.md` says what 46 kinds of change did to the tests of a toy codebase. Re-run the study on
this codebase so every row has a real example from it, plus rows for changes from the team's own git history.
Follow `resources/impact-study.md`. In short:
1. `$KB_DIR/study/study.json`: the build in `build-study` with gcov and keep-going, the test binaries, and one
   scenario per reference ID. Each scenario is a real target in this code, or `na` with the reason.
2. Add 3–6 `P` scenarios replayed from the git history. They cover the kinds of change the team really makes.
3. Write `why` and `expect` for each scenario before running.
4. `impactstudy.py setup`, then `check` until OK, then `run` (background it; it resumes).
5. `EDIT INCOMPLETE` means the edit is not finished yet: add edits for the named production files, then `--force`.
6. Write a `lesson` per scenario (real files, stubs and tests here) and 3–6 `findings`.
7. `report > $KB_DIR/STUDY.md` and `report --short > $KB_DIR/change-impact.md`.
Then fill L22–L25 in `learnings.md` from the findings, and add each hazard line the study confirmed to notes.md
`Change hazards` as `confirmed by <ID>`.

## Step 12. Design the project skill
The `ut` skill stays generic. The project skill is a short entry point that makes an agent pick up this project's
knowledge at the right moment:
1. Create `<SKILL_DIR>/../ut-<project>/SKILL.md` from `resources/templates/project-skill.md`, where `<project>` is a
   short lower-case name.
   - **description:** the words a user or an agent would use about this code: the repository name, 3–6 component
     or product names from `codebase.md`, the test binaries. That is how the skill gets picked.
   - **Always:** at most 12 rules. Take the ones that decide whether a new test builds and matches the team's style:
     commands, exemplar, registration, seams, stub mode, the top workarounds (`copy` / `never` rows), the hazards
     the study confirmed. Each rule names its KB source.
   - **Load when:** keep the table. Remove a row only if its file does not exist.
   - At most 80 lines. It points to KB files and never copies them.
2. Read each generic playbook (`resources/playbooks/*.md`) against what you found. Where this project does it
   differently, write `$KB_DIR/playbooks/<same name>.md` with ONLY the differences and their sources. Examples: stubs
   are the shared `--wrap` files, so `fix-mocks` differs; tests are registered in two lists, so `add-tests` differs.
   Record one line per playbook in REPORT `## Playbooks`, in the form `<name>: same` or `<name>: KB override (<why>)`.
   The ut tool and executors read the KB playbook after the generic one.
3. Dry-run the project skill as a new agent would. Read only its SKILL.md, and for 3 situations (a new test for a
   hotspot function, a link error, a diff that changes a struct), check that the rules and the "Load when" rows
   lead to the right KB file. Fix what does not. Record the 3 checks in REPORT.

## Step 13. Validate what you made
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
`git status` may list the `build-ut*` / `build-mcdc` folders as untracked: that is expected. Leave them (rule 3); run
`makercheck.py` last, after any other command, so its `ALL PASS` describes what you hand over.
Also dry-run one real task to see what a test-writing agent would receive:
```sh
"$S/ut" discover --task "$TASK" --names <one production function> --yes
"$S/ut" scope --task "$TASK" --yes
"$S/ut" plan --task "$TASK" --yes
"$S/ut" run --task "$TASK" --dry-run      # writes prompts/*.md without calling an agent
```
Read the prompt. Every fact in it must be right: include lines, fixture, seam, stub names. Fix the KB where it is not,
never the prompt.

## Step 14. Final report
Finish `REPORT` with:
- **The last output of makercheck.py**, verbatim.
- **Checklist** (each ✓ or ✗ with the reason): toolchain recorded; profile; build, run and one-group commands verified;
  compile DB includes tests; index built and spot-checked; exemplar, register and mock verified by the smoke test;
  seams decided or asked; stubs checked (wrapcheck); coverage commands (official measure verified or UNVERIFIED;
  clang MC/DC baseline); hazards reviewed; workarounds with reasons; learnings with verdicts; codebase map; study
  (scenarios run, n/a, predictions right); project skill and playbooks; dry-run prompt correct; repository unchanged.
- **Unverified** items, each with what is needed to verify it.
- **Next**: "the skill is ready: ask for unit-test work on <project> (the `ut-<project>` skill picks it up), or run
  `resources/scripts/ut init` (tool-driven)".

Keep the KB folder with the skill (`resources/kb/README.md` says how). Every later task reads it and adds to it.
