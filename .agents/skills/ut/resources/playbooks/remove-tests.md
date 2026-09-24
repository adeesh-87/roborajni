# Playbook: remove-tests
Remove tests, mocks or stubs that belong to code that no longer exists.

1. Confirm the code is really gone: `grep -rnw '<name>' <code paths>` must show nothing.
2. Check nothing else needs the test helper or mock:
   `grep -rnw '<name>' <test paths> <mock paths>` — only the lines you will delete may remain.
3. Check the deletion permission in context.md section 6 for this S row. No permission → ask the user
   with the exact list of files / tests to delete. Wait.
4. Delete:
   - Single test: remove the whole test function (and nothing else).
   - Whole file: `git rm <file>` only if the commit policy allows git operations, else plain delete;
     also remove it from the build registration.
   - Mock/stub: remove the function; remove the file if empty; update the build registration.
5. Remove includes, fixtures or helpers that became unused in files you touched.
6. Build and run the affected group(s). A link error "undefined reference" means something still
   used what you deleted: find it and fix, or restore and report.
7. Result: list every removed test, function and file.
