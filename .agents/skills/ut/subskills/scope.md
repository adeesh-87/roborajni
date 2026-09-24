# Sub-skill: scope (phase 5)

Goal: the user approves exactly what will be done. Result: context.md section 6.

## Step 1 — Show candidates by category
Read context.md section 5. Show it grouped like this (skip empty groups):

| Cat | Meaning | Typical work |
|-----|---------|--------------|
| A | Remove | delete tests, mocks or stubs for code that no longer exists |
| B | Update tests | expectations, parameters or setup changed with the code |
| C | Mocks / stubs | add, change or delete mocks, stubs, fakes; signature updates |
| D | New tests | tests for new functions, new branches, untested files |
| E | Fix build | test code does not compile or link |
| F | Fix run | tests fail, crash, hang, leak or are order-dependent |
| G | Coverage | raise coverage to a target |
| H | Cleanup | refactor or tidy tests (only when asked) |
| I | Production bug | a test shows the code under test is wrong: REPORT, do not change the test to match |

## Step 2 — Ask
1. "Which rows are in scope? [all]"
2. "Anything to add?" (the user may add items of any category)
3. "Priority order? [E, F, C, B, A, D, G, H]" — the build must work before anything else can be checked.
4. "Acceptance for the whole task? [build OK, all tests pass, no new warnings]"
   If G is in scope: "Coverage target, metric and files? [from Config]"
5. For A rows: "May I delete these files/tests? [ask each]" — record the answer per row.

## Step 3 — Record
Write context.md section 6: one row per item, `S1`, `S2`, ... with category, priority and an
acceptance check someone can verify (a command and the expected result).
Write `Out of scope:` with the rows the user dropped.
Write `Confirmed by user on <date>`.
Every I row also goes to status.md `Open issues` so the user sees it.

## Finish
If any S row has category G: phase 6 is next. Otherwise tick phase 6 as "skipped".
Tick phase 5, add a Log line.
