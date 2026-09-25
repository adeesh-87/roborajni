# Playbook: fix-run
1. Run only the failing test, verbose (single-test command). Load `tools/errors/<tool>.md`.
2. `expected X but was Y` → work out the right value by hand from the card's decisions, the code and the requirement.
   Test wrong → fix the test. Code wrong → do NOT touch the test; open issue (category I); PARTIAL.
   Unexpected/missing mock call → compare expectations with the card's `Calls` and their order.
   Crash → NULL from a stub, uninitialised fake register, buffer overrun. Hang → a fake never sets the flag the
   loop waits for, or the tick mock never advances. Passes alone, fails in the full run → state not reset in setup/teardown.
3. Fix; run the test, the group, then all tests if cheap. Max 3 attempts per failure. Order-dependence: the
   framework's shuffle/repeat option (tool file).
4. Result per test: cause and fix, one line.
