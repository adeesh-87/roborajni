# Test design for C/C++ unit tests (read before writing any test)

## Golden rules
1. **Imitate.** Open the existing test file named in the task Inputs (or the closest one for the
   same module). Copy its includes, fixture, mock style, naming and layout exactly.
2. **One behaviour per test.** Name says input/state and expected result:
   `<Function>_<Condition>_<Expected>` (or the naming in KB section 3).
3. **Arrange / Act / Assert.** Set inputs and mock expectations, call the function once, check results.
4. **Check every output:** return value, out-parameters, changed globals/state, calls to dependencies.
5. **Independent tests.** Reset all state in setup/teardown. No test may rely on another test's order.
6. **Never** change an expected value just to make a test pass. Work out the right value from the
   code and the requirement. If code and requirement disagree, report it (category I).
7. Use exact literal expected values (`42`, `0x1F`). Do not recompute them with the code under test.

## Choosing test cases (do this list for every function)
Read the function top to bottom and write down:
| Look for | Tests to write |
|----------|----------------|
| each `if` / `else if` / `else` | one test per outcome (true and false) |
| `&&` / `\|\|` conditions | each sub-condition deciding the result (needed for MC/DC) |
| `switch` | each `case`, plus `default` |
| loops | 0 iterations, 1 iteration, many / max iterations, early `break` |
| input ranges | min, min-1, max, max+1, zero, typical value (boundary values) |
| pointers | `NULL` argument (if the code checks it), valid pointer |
| buffers / lengths | length 0, 1, exact size, size+1 |
| return codes of called functions | success, each handled error (mock returns the error) |
| state machines | each transition, invalid event in each state |
| arithmetic | overflow / wrap, division by zero guard, sign |
| enums | each value, out-of-range value if handled |
Make a short table in the task file before coding: `case | inputs | mock setup | expected`.

## Dependencies
- Everything the function calls outside its own module is replaced by a mock, stub or fake
  (as the repo already does). Use the mock to set return values and to check call arguments.
- Only expect calls the test is about. Use the framework's "ignore other calls" only if the repo does.
- Out-parameters from a dependency: make the mock write the value (see the tool file).

## Common embedded C patterns
| Problem | Usual solution (check KB first) |
|---------|--------------------------------|
| `static` function | test via public function; or `#include "module.c"` in the test file; or a `STATIC` macro that is empty in test builds |
| hardware registers `*(volatile uint32_t*)0x4000` | register macros point to a fake array in test builds; or a HAL layer that is mocked |
| globals of the module | `extern` them in the test, reset in setup |
| time / delays / ticks | mock the tick or delay function; control the returned time |
| interrupts / ISR | call the ISR function directly from the test |
| infinite loop `while(1)` | loop body in a separate function; or a test-only macro `FOREVER` |
| asserts / fatal handlers | mock the handler; with CppUTest/gtest check it was called |
| memory allocation | mock or wrap `malloc` to test the failure path |

## Before you build
- [ ] File name, location and group name follow KB section 3.
- [ ] New test file is registered in the build (see KB "How a new test file is registered").
- [ ] Every mock expectation has a matching check (framework verifies at teardown or explicitly).
- [ ] No leftover debug prints, no commented-out tests, no `IGNORE`/`DISABLED_` unless asked.
- [ ] Header/copyright/requirement comments as in the imitated file.
