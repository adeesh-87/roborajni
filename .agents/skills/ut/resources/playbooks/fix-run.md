# Playbook: fix-run
Tests build but fail, crash, hang, leak or depend on order.

1. Run only the failing test with the single-test command and verbose output. Save the log.
2. Classify by what you see:
   | Symptom | Look at |
   |---------|---------|
   | expected X but was Y | is the test expectation or the code wrong? (step 3) |
   | unexpected / missing mock call | mock expectations vs the code's real calls and order |
   | crash / segfault | NULL pointer from a stub, uninitialised fake register memory, out-of-bounds buffer |
   | hang / timeout | loop waiting for a register/flag the fake never sets; missing mocked tick |
   | memory leak report | allocation in code not freed in test; framework leak checker + mocks (see tool file) |
   | passes alone, fails in full run | state not reset in setup/teardown (globals, statics, mock state) |
3. Expected value wrong or code wrong?
   - Work out the correct result by hand from the code and the requirement / comment / docs.
   - Test wrong → fix the test. Code wrong → do NOT change the test; record category I in status.md
     Open issues and ask the user. Mark the task PARTIAL.
4. Fix, then run the single test, then the whole group, then all tests if cheap. Max 3 attempts per failure.
5. Order-dependent failures: run with the framework's shuffle/repeat option if it has one (tool file).
6. Result: per test: cause and fix, one line.
