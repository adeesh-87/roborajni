# Playbook: remove-tests
1. Confirm the code is gone: `"$I" refs "$GD" <name>` (after `"$I" refresh "$GD"`) shows no production definition.
2. Nothing else uses the test helper or mock: `"$I" refs "$GD" <name>` lists only callers you will delete.
   The index does not see macro bodies or strings: as the LAST check before deleting run `grep -rnw '<name>' <paths>` once.
3. Permission: Config says `ask each` → Ask with the exact list of files/tests. Wait.
4. Delete the test function (only it), or the file plus its registration line, or the mock function (file if empty).
   Remove includes/helpers that became unused in the files you touched.
5. Build + run the affected groups. `undefined reference` = something still used it: fix or restore and report.
6. Result: every removed test, function, file.
