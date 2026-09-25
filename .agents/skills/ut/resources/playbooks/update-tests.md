# Playbook: update-tests
1. `git diff <base> -- <source file>` for the change; read the tests named in the work item and the function's card.
2. Per test: only a call/type changed → update it. Expected value changed on purpose (diff or requirement says so)
   → update it and note why. Not sure it was on purpose → leave the test, open issue (category I). Tests something
   that no longer exists → leave it for a remove-tests task. New decision in the card → add a test (add-tests steps 2–6).
3. Mock expectations follow the function's calls (new, removed, reordered, different arguments).
4. Build, run the affected tests, then the module's group. Max 3 fix attempts per error.
5. Result per test: `updated | unchanged | flagged (reason)`.
