# Test design (read once per task, before the first test)

Shape: copy `exemplars/test.md`. One behaviour per test; name `<Function>_<Condition>_<Expected>` unless the
Conventions say otherwise. Arrange (inputs, mock returns, state) → Act (one call) → Assert (return value,
out-parameters, changed globals, calls made). Reset all state in setup/teardown; no test depends on another.
Expected values are literals worked out from the code and the requirement, never computed by calling the code
under test. Code and requirement disagree → open issue (category I), not a changed assertion.

Cases come from the card's `Decisions`; add these when they apply:
| Seen in the card | Cases |
|------------------|-------|
| `if` / `?:` | true and false (and `else`) |
| `[n sub-conditions]` | each sub-condition flips the outcome alone |
| `switch` | every case, the default, an unknown value if handled |
| loop | 0, 1, many/max iterations, early exit |
| numeric input | min, min−1, max, max+1, zero, typical |
| pointer input | NULL if checked, valid |
| buffer + length | 0, 1, exact, exact+1 |
| call to a dependency | success, each handled error (mock returns it) |
| state machine (globals written) | each transition, invalid event per state |

Embedded seams (check Conventions first): static function → via its public caller, or `#include "module.c"` in the test,
or a `STATIC` macro empty in test builds; registers → fake register array or mocked HAL; module globals → `extern`
+ reset in setup; ticks/delays → mock the tick function; ISR → call it directly; `while(1)` → body in a function.

Before building: file name, location and registration as in `exemplars/register.md`; every expectation checked;
no debug prints, no commented-out or disabled tests; header comment as in the exemplar.
