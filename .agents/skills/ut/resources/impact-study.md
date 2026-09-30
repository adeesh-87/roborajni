# Re-running the change-impact study on your codebase

`resources/change-impact.md` was measured on a toy codebase. This guide re-runs the same study on the real one, so
test agents learn what a change does to YOUR tests: which changes the compiler catches, which only a test catches,
and which pass silently. The runner is `resources/scripts/impactstudy.py`; the reference numbers were reproduced with
it (all 43 C++ scenarios gave the same outcome and the same failing tests).

Output, both in `KB_DIR`:
- `STUDY.md`: the full study, with what happened per scenario, coverage of the change, the index prediction, details;
- `change-impact.md`: the short form. The skill reads it instead of `resources/change-impact.md` for this codebase.

Cost: one incremental build and one test run per scenario, 40–50 scenarios. Build only the test targets. On a large
codebase, run it in the background; it resumes where it stopped.

## 1. Set up
```sh
mkdir -p "$KB_DIR/study"
```
Write `$KB_DIR/study/study.json` (the format is at the top of `impactstudy.py`):
- `source`: `$REPO`. `work`: `$TASK/study-src` (a clone outside the repository; the runner makes it).
- `configure` and `build`: your verified build commands (KB Commands), with these changes:
  - build folder `build-study`;
  - gcov coverage flags (`--coverage -O0`) so the report shows whether a test ran the changed lines;
  - keep going after errors (`-- -k 0` for Ninja, `-- -k` for Make), so every broken file is counted;
  - only the unit-test targets.
- `tests`: every test binary, with its run command and its path (`binary`). A binary that is not rebuilt must not
  run stale.
- `framework`, `code_paths`, `test_paths`: from KB `Profile`. `index`: `$KB_DIR/index`.
```sh
python3 "$S/impactstudy.py" setup "$KB_DIR/study/study.json"      # clone, configure, build, run: the baseline
```
The baseline must build and its tests must pass. A test that already fails is subtracted from every scenario; list
it in REPORT.

## 2. Pick one target in your code for every reference scenario
For each ID in `resources/change-impact.md`, find the place in YOUR code where that kind of change can happen, and
write the change as a developer would make it:
- update production callers until production code compiles;
- never edit test sources: the point is to see what the tests do;
- change a test BUILD file only where that build file is the change itself (H3, W1, W4, W5).

Rules for choosing:
- Spread the targets over at least 3 components (`codebase.md`). Prefer code that changes often:
  `git log --format= --name-only -- <code paths> | sort | uniq -c | sort -rn | head`.
- The target must match the scenario's condition. B2 needs a boundary that a test pins; B3 needs one no test pins
  exactly. Check with `index.sh card` (decisions and tests) and `index.sh tests`.
- A scenario that cannot happen here gets `"na": "<why>"`. For example: no C++ means no G8, G9, V1–V5 or K*; no
  `--wrap` stubs means no W* or X*; stubs already guarded with `__typeof__` mean no X1 or X3. Where C has an
  equivalent, use it (the table below says which).
- Write `why` (the evidence that the target fits, with file:line) and `expect` (your prediction) BEFORE running.

| ID | Where to find a target | The edit |
|---|---|---|
| B1 | any tested function with a loop or a helper | the same result written another way |
| B2 | a comparison with a limit, pinned by a test (a TEST name with Max/Full/Limit, or `card` decisions) | `>=` → `>` |
| B3 | a comparison whose equal case no test hits (`flow` shows it) | `<` → `<=` |
| B4 | an error path that returns a code a test checks | return another error code |
| B5 | a tested function that validates its input | add an early return for a new invalid case |
| B6 | a statement that updates state (counter, flag, output parameter) | delete it |
| B7 | a call to a collaborator that tests stub or mock (a wrapped function is best) | call it twice |
| B8 | two collaborator calls in a row | swap them |
| B9 | a size or length argument to a collaborator | pass `len - 1` |
| G1 | C++: a function with test callers | add a parameter with a default (C: na) |
| G2 | a function with test callers and 2+ production callers | add a parameter; a `regex` edit on the code paths updates the callers |
| G3 | a `typedef`/`using` for an ID or size in the API | widen it (`uint16_t` → `uint32_t`) |
| G4 | a `bool` result that callers test with `!` | return a status enum; update production callers |
| G5 | a function with test callers | rename it in the code paths only (`regex` with `\b`) |
| G6 | a function only tests call (codemap "Entry points" plus `refs`) | delete it |
| G7 | C++: members "public for testing"; C: a function tests call through a header | make them private / `static` |
| G8, G9 | C++: an overloaded name that tests call with literals | add an overload (G9: one that an `int` literal binds to) |
| V1–V5 | an interface with fakes in tests (codemap "Interfaces"); C: an ops table of function pointers | V1 new pure virtual (C: new member), V2 with a default body, V3 drop `const`, V4 default argument, V5 return type |
| T1 | a struct tests build | new field at the end, with an initializer |
| T2 | a struct tests build with positional `{...}` (hazards "positional init") | new field in the middle |
| T3 | the same struct, two fields of the same type | swap them |
| T4 | a field tests read | rename it; update production code |
| T5 | a 64-bit field | narrow it to 32 bits |
| T6 | an enum with a count constant sizing a table (hazards "count-sized table") | new enumerator in the middle, count + 1 |
| T7 | an enum | new enumerator at the end |
| T8 | a constant the tests use by name | change its value |
| T9 | a constant whose value the tests write as a literal (hazards "literal constant") | change its value |
| K1 | C++: a class tests construct; C: an `init` function tests call | add a parameter; update production callers |
| K2 | a default argument or default config value | change it |
| H1 | a header that includes another that tests use without including it | forward-declare instead of including |
| H2 | C++: a namespace; C: na, or a module's name prefix | rename it in the code paths |
| H3 | a function in a file listed in the test build (hazards "test source list") | move it to a new source file (`new_files`) |
| W1 | a test binary that does not link the strict stubs | link them into it |
| W2 | a wrapped C++ function (`wrapcheck.py` list) | add a defaulted parameter |
| W3 | a wrapped function | move its body into the header as `inline` |
| W4 | the wrap list | add a function that has no stub |
| W5 | the wrap list | remove a flag whose stub stays |
| W6 | a production function that calls a wrapped one | stop calling it (compute the value another way) |
| X1–X3 | a wrapped C function, if stubs declare `__real_` by hand | X1 new parameter, X2 the same with a `__typeof__` guard, X3 return type |

Edits (paths relative to the repository root):
- `{"file", "old", "new", "count"}` replaces exact text; `count` is how many times it must occur (default 1).
- `{"glob", "regex", "new", "min"}` is for callers: `"glob": "src/**/*.c"`, and `\1` in `new` refers to groups.
- `{"patch": "P1.diff"}` applies a diff (see step 3).

## 3. Add scenarios from your own history (P1, P2, …)
The reference IDs are generic. The most useful rows are changes your team really made:
```sh
git -C "$REPO" log --no-merges --format='%h %ad %s' --date=short -- <test paths> | head -60
git -C "$REPO" show --stat <sha>
```
Pick 3–6 commits that changed production code AND tests (or stubs, or the test build). Prefer kinds that are not
already in the reference list. Take the commit's production part only:
```sh
git -C "$REPO" show <sha> -- <code paths> > "$KB_DIR/study/P1.diff"
```
Scenario: `{"id": "P1", "cat": "From history", "title": "<kind of change>", "change": "<sha>: <subject>",
"edits": [{"patch": "P1.diff"}], ...}`. The patch must apply to HEAD (`check` tells you). An old commit that does
not apply can be re-made by hand as edits on today's code. The result shows what the test-side part of that commit
had to fix, and whether the team's fix was the one the study predicts. If the history has nothing usable, write
`"history": "<why>"` at the top level of study.json.

## 4. Check, run, fix the edits
```sh
python3 "$S/impactstudy.py" check  "$KB_DIR/study/study.json"      # every edit applies; every reference ID covered
python3 "$S/impactstudy.py" run    "$KB_DIR/study/study.json"      # resumable; background it on large code
python3 "$S/impactstudy.py" status "$KB_DIR/study/study.json"
```
- `EDIT INCOMPLETE` means production files do not compile after the change, so a developer would have fixed them
  first. Add edits for those files, then `run ... <ID> --force`.
- A result far from your `expect`: read `results/<ID>.json` (errors, failing TESTs, the diff) and make sure the edit
  does what the row says before you trust it.

## 5. Write the lessons and the findings
For every scenario, `lesson` says what a diff task must do when this kind of change happens here. Name real files,
stubs, fakes and tests, for example: "a change to `hal_uart_*` signatures breaks `tests/stubs/hal_stubs.c`
and 3 fakes; update them with the declaration". Do not repeat the outcome.

`findings` has 3–6 numbered conclusions for this codebase, each with IDs. Say where it differs from the reference
(`resources/change-impact.md` Summary): which silent kinds are silent here too, what the index predicted well or
badly, and which hazards turned out real.

## 6. Reports
```sh
python3 "$S/impactstudy.py" report "$KB_DIR/study/study.json"         > "$KB_DIR/STUDY.md"
python3 "$S/impactstudy.py" report "$KB_DIR/study/study.json" --short > "$KB_DIR/change-impact.md"
```
Re-run the study after large refactors, or when the test infrastructure changes (stubs, the test build, framework
version): `run --force`, then both reports again.

The clone `$TASK/study-src` is outside the repository. Keep it while you may re-run; it can be deleted afterwards
(`setup` clones it again).
