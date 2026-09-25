# Knowledge base: <codebase-id>
> ONLY about this codebase. Facts with sources (file:line or person). Keep this file under 120 lines;
> details go to `modules/<name>.md`, examples to `exemplars/`. Last updated: YYYY-MM-DD by <task>

## Identity
| id | remote | roots seen | last graph build (date, compile DB yes/no) |
|----|--------|------------|--------------------------------------------|

## Profile
| Code paths | Test paths | Mock paths | Framework | Mock style | Build system | Compile DB | Coverage tool | Env before build |
|------------|------------|------------|-----------|------------|--------------|------------|---------------|------------------|

## Commands (verified by running them; run from `Run from`)
| Purpose | Command | Run from | Verified on |
|---------|---------|----------|-------------|
| Env setup | | | |
| Clean | | | |
| Build tests | | | |
| Run all tests | | | |
| Run one group / test | | | |
| Compile DB (test build) | path or none | | |
| Coverage build / report | | | |
Paths written by build (lock these in parallel mode):
Test summary line looks like:

## Conventions  (approved: no | approved on <date> (pilot: <file>))
Facts with counts from testscan.md, ≤ 12 lines. Example lines:
- Test file: `tests/<module>_test.cpp`, one per source file (14/14). Register in tests/CMakeLists.txt (see exemplars/register.md).
- Test name: `TEST(<Module>, <Function>_<Condition>_<Expected>)` (61 of 68).
- Asserts: LONGS_EQUAL (84), CHECK_TRUE (31), STRCMP_EQUAL (12). Expected value first.
- Mocks: CppUMock, `mock().expectOneCall(...)`; mocks live in tests/mocks/<header>_mock.cpp; `mock().clear()` in teardown.
- Statics: tested through public callers (no `#include "x.c"` anywhere).
- Headers: `extern "C" { #include }` for C headers; copyright header copied from the exemplar.
Exemplars: exemplars/test.md, exemplars/mock.md, exemplars/register.md

## Build notes
(quirks, slow steps, files the graph could not preprocess, flaky tests, license limits)

## Modules
| Module | File | Purpose | Tests | Notes file |
|--------|------|---------|-------|------------|

## Glossary
| Term | Meaning |
|------|---------|
