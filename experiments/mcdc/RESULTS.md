# Can a Haiku agent raise MC/DC with clang 18 as the measure?

Yes. On cvaccel, Haiku 4.5 raised MC/DC of `src/` from 22 to 36–39 of 39 conditions in every run. All tests passed,
and no production file was changed. The remaining conditions are defensive code (see below).

## Setup
- The codebase is `examples/cvaccel` with its 215 existing tests. Baseline MC/DC of `src/`: 22 of 39 conditions shown
  independent, in 20 decisions. Measured by clang 18.1.3 (`-fcoverage-mcdc`) and `llvm-cov`.
- The task: new CppUTest tests in `tests/mcdc_test.cpp` until every condition in `src/` is shown independent. No
  changes to production code or existing tests. Reading and grepping code allowed.
- Measurement: `./mcdc.sh` builds with MC/DC instrumentation, runs all tests, and prints the gaps. Up to 60 turns.
- Two arms, 3 runs each. They differ only in what `./mcdc.sh` prints:
  - **suggest**: the ut index's gap list (`index.sh cov-import --llvm`, then `uncovered`). One line per missing
    condition, naming the condition values of the test that completes its pair.
  - **raw**: the plain `llvm-cov show -show-mcdc` blocks (conditions, executed vectors, pairs) of every decision
    below 100%.
- Scoring: after each run, `llvm-cov report -show-mcdc-summary src/*.cpp`, the test result, and a check that no
  production or existing test file changed.

## Results
| Arm | Conditions shown independent (of 39), per run | Tests pass | New TESTs per run | Cost/run | Turns | Time/run |
|---|---|---|---|---|---|---|
| baseline (existing tests) | 22 | ✓ | – | – | – | – |
| suggest | 36, 39, 37 | 3/3 | 21, 29, 23 | $0.73 | 61, 61, 38 | 270–500 s |
| raw | 37, 39, 37 | 3/3 | 37, 43, 36 | $0.75 | 61, 61, 50 | 310–375 s |

- **Both arms reach MC/DC with clang alone**: 95% of conditions on average, from 56%.
- **The suggested vectors did not raise the result here** (1.7 vs 1.3 conditions left on average; 3 runs each is too
  few to separate them). They did produce leaner tests: about 24 new TESTs instead of about 39 for the same coverage.
  llvm-cov's own report already lists each decision's executed vectors, which a model that can read the code turns into
  tests. The suggestions should matter more where reading is expensive or denied.
- **The conditions left over**: `s.id != id` in both `SessionManager::find` overloads (5 of 6 runs), and
  `si->openRequests > 0` in `Dispatcher::pump` (1 run).
  - `s.id != id` is defensive. Through the API a session's id always equals its slot, so the condition can only be true
    if a test corrupts that state.
  - The two runs that reached 39/39 did exactly that: they changed `id` through the mutable pointer `find()` returns.
    Whether such a test is wanted, or the condition is justified as unreachable, is a review decision (`ask` in
    `subskills/coverage.md`).
- Most runs used their 60 turns. They kept adding tests after reaching the reachable maximum, because the gap list never
  says "unreachable".

## Files
`run.py prepare|run|score`, `mcdc.sh` (the agents' measure), `results/results.json`. The skill side is
`resources/tools/llvm-mcdc.md` and `codeindex/mcdc.py`.
