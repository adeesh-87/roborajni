# Phase 3 — Knowledge

Goal: `KB_DIR` holds everything a test writer needs about THIS codebase, in the form a small model uses best:
one real example to copy, counted facts, one card per function and diagrams. No questions in this phase.

## 1. KB folder
```sh
"$SKILL_DIR/resources/scripts/kb-id.sh" "<repo root>"       # id=...
KB_DIR="$SKILL_DIR/resources/kb/<id>"; KB="$KB_DIR/kb.md"
mkdir -p "$KB_DIR/exemplars" "$KB_DIR/modules" "$KB_DIR/decompositions"
[ -f "$KB" ] || cp "$SKILL_DIR/resources/templates/kb.md" "$KB"
```
Not writable → use `$TASK/kb/` instead and record it. Fill KB `Identity` and `Profile` (from Config), add a row
to `resources/kb/INDEX.md`. Record `KB dir` in Config. Never open another codebase's KB folder.
KB exists with `Conventions approved on <date>` and the code did not change much → do only steps 2 and 5, then finish.

## 2. Code index (always; local; seconds to a minute)
```sh
I="$SKILL_DIR/resources/scripts/index.sh"; GD="$KB_DIR/index"
"$I" setup                                     # once per machine (Python 3.10+)
"$I" build --cdb <compile DB from KB Commands> "$GD" <code paths> <header paths> <test paths> <mock paths>   # omit --cdb if none
```
Check the output for `preprocessed with compile flags` (good) and `not preprocessed` / syntax warnings: record those
files in KB `Build notes`. How to ask the index: `resources/graph-queries.md`.

## 3. How the existing tests are written
```sh
"$SKILL_DIR/resources/scripts/testscan.sh" "$KB_DIR" <test paths> <mock paths>
```
Read `$KB_DIR/testscan.md`. Then read fully (they are short): the top exemplar candidate, the top mock/stub file,
and the lines that register one existing test file in the build (`grep -n '<test file name>' CMakeLists.txt Makefile* project.yml`).
Write:
- `KB_DIR/exemplars/test.md` from `resources/templates/exemplar.md`: the candidate file VERBATIM (cut to ≤ 80 lines
  keeping 2–3 tests), each part labelled in the comment column; then the skeleton to copy for a new file.
- `KB_DIR/exemplars/mock.md`: one real mock/stub function verbatim + how a test sets its return value and checks its
  arguments (from a test that uses it). Greenfield or no mocks → write `none yet`.
- `KB_DIR/exemplars/register.md`: the exact lines that add a test file to the build, with file:line.
- KB `Conventions`: ≤ 12 lines of facts with counts from testscan (file name pattern, test name pattern, fixture use,
  top asserts, mock API, `extern "C"`, statics access). Mark `DRAFT (from N files); approved: no`.
No tests exist → write `greenfield` in Conventions; the pilot will create the exemplars.

Test seams already in use (evidence table at the end of `resources/test-seams.md`; grep is right here: it looks at
test and build files): for each hit write KB `Test seams` `<need>: <ID> ... (detected in the existing tests, <date>,
evidence file:line)`. Two techniques for one need → record the first, name the other under it ("also in old tests; do
not use for new tests") and tell the user in one line.

## 4. Module cards and diagrams (in-scope code only)
For the in-scope source files `F...` (from Config paths and the request):
```sh
"$I" kb-cards "$GD" "$KB_DIR" F...          # KB_DIR/modules/<basename>.cards.md = cards + dependencies per file
"$I" diagrams "$GD" "$KB_DIR/diagrams"       # Mermaid text: flow/, seq/, scenarios/, SCENARIOS.md, INDEX.md
```
Create `KB_DIR/modules/<name>.md` from `resources/templates/module.md` if missing: purpose (1 line, from the header
comment or file name), files, test file(s) (from testscan / graph `tests`), the cards file name.
Read the docs the user named in setup (context.md section 2): write ≤ 8 lines per module into the module file,
each ending `(source: <path>)`. Link, never copy.

## 5. Decomposition by a stronger model (only when it pays)
If no notes exist for the in-scope modules AND (the cards show > 40 functions, or state machines, ISR/RTOS,
protocol parsing, or the user said the code is tricky): copy `resources/templates/decompose-codebase.md` to
`$TASK/decompose-codebase.md`, fill `<KB_DIR>` and `<MODULES>`, and tell the user in one line that giving that file
to a stronger model will produce module notes you and later tasks reuse. Do not wait for it.

Update KB `Last updated` and INDEX.md. Tick phase 3.
