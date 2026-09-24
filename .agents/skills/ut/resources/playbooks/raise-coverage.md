# Playbook: raise-coverage
Cover the gaps listed in context.md section 7 for this task (G rows). Read `resources/test-design.md`
and the coverage tool file.

1. For each G row: open the source at the uncovered lines. Write in the task file the exact input,
   state and mock setup that drives execution there. Walk the conditions backwards from the line
   to the function entry.
2. Prefer adding a case to an existing test group of that module. Imitate existing tests.
3. For condition / MC/DC gaps: each condition must change alone while the others stay fixed and the
   decision outcome must change. Write the truth-table rows you need.
4. Error paths: make the mock of the dependency return the error value.
5. Write the tests. Each test still checks real outputs (not only "runs the line").
6. Build, run the new tests. Then rebuild with coverage and regenerate the report (status.md commands).
   Delete old coverage data first (tool file says which files).
7. Compare the gaps: covered now? Update the G rows in context.md (lock it in parallel mode)
   with `now` and `covered by <test>`.
8. Lines that cannot be covered without changing production code: record them with reason under
   Result as "needs justification or exclusion" and tell the user; do not add `SKIP`/exclusion
   pragmas unless the user approved them.
9. Result: coverage per function before → after.
