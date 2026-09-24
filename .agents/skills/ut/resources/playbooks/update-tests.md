# Playbook: update-tests
Existing tests must follow a code change (behaviour, parameters, types, names).

1. Read the code change: `git diff <base> -- <source file>` (base in context.md section 3).
2. Read the tests listed for this task (context.md 3.2 "Existing tests").
3. For each test decide:
   | Situation | Action |
   |-----------|--------|
   | Test still valid, only call or type changed | update the call / types |
   | Expected value changed because behaviour changed on purpose | update the expected value; note the reason from the diff or requirement |
   | Behaviour changed and you are NOT sure it was on purpose | do not change the test; record as category I and ask |
   | Test tests something that no longer exists | leave it; it belongs to a remove-tests task (tell the user) |
   | New branch appeared | add tests for it (follow add-tests steps 3–5) if in scope |
4. Update mock expectations in these tests when the function's calls changed
   (new call, removed call, different arguments or order).
5. Build, run the affected tests, then the whole group. Max 3 fix attempts per error.
6. Result: per test: `updated | unchanged | flagged (reason)`.
