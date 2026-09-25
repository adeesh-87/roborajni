# Phase 6 — Pilot

Goal: two real tests, built and passing, reviewed by the user. They become the exemplar every later test copies.
This replaces guessing conventions: the user corrects concrete code, once.

## 1. Pick two functions from the in-scope work items
Use the cards (`KB_DIR/modules/*.cards.md`): (a) the simplest with no external calls; (b) one with 1–2 dependencies
to mock. Prefer functions the scope needs anyway; the pilot tests count as done work.

## 2. Harness
- Tests exist → new tests go where `exemplars/register.md` and `Conventions` say (usually one test file per source file).
- Greenfield (no tests in the repo) → Ask once:
  "No unit tests exist yet. Framework and build? [<recommendation from resources/harness.md: e.g. CppUTest via CMake
  for C, GoogleTest for C++>]". Then create the minimal harness from `resources/harness.md` (one test target, one
  runner, the mock folder), verify it builds and runs an empty test, record the commands in KB `Commands`.

## 3. Write the pilot file
Load the framework file from `Resources to load` and `resources/test-design.md`. Write one test file with 2–3 tests
(one per function, plus one error path if (b) has one). Follow `exemplars/test.md` if it exists, else the framework
file skeleton. Register it. Build; run only this file (single-test command); fix, max 3 attempts per error.

## 4. Review (1–3 rounds)
Show the whole test file (it is short) and the mock lines it needed. Ask:
```
This is how I will write every test in this task. Change anything: names, file location, asserts, mock use,
setup/teardown, comments or headers. [approve as is]
```
Apply corrections, rebuild, rerun, show again. After the third round, take what is there.

## 5. Save the approved style
- `KB_DIR/exemplars/test.md` ← the approved file verbatim, annotated per `resources/templates/exemplar.md`.
- `KB_DIR/exemplars/mock.md` ← the mock/stub used, verbatim, with the test lines that drive it.
- `KB_DIR/exemplars/register.md` ← the exact registration lines.
- KB `Conventions` ← rewrite in ≤ 12 lines from the approved file; set `approved on <date> (pilot: <file>)`.
- Mark the two functions' work items as covered by the pilot (their remaining cases stay planned work).
Tick phase 6.
