# Playbook: remove-tests
1. Confirm the code is gone: `grep -rnw '<name>' <code paths>` finds nothing.
2. Nothing else uses the test helper or mock: `grep -rnw '<name>' <test paths> <mock paths>` shows only lines you will delete.
3. Permission: Config says `ask each` → Ask with the exact list of files/tests. Wait.
4. Delete the test function (only it), or the file plus its registration line, or the mock function (file if empty).
   Remove includes/helpers that became unused in the files you touched.
5. Build + run the affected groups. `undefined reference` = something still used it: fix or restore and report.
6. Result: every removed test, function, file.
