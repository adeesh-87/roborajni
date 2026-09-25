# Playbook: raise-coverage
1. For each G row: open the card and the source at the uncovered lines. Walk the conditions back to the function
   entry; write the exact inputs, state and mock returns needed as a `Cases` line.
2. Add the tests to the module's existing test file, copying the exemplar. Each test still checks real outputs.
   MC/DC: each sub-condition flips the outcome alone; write the truth-table rows you need.
3. Build, run the file; then rebuild with coverage, delete old data files first, regenerate the report (KB `Commands`).
4. Update the G rows: now %, covered by <test>. Unreachable without production changes → "needs justification or
   exclusion" in `Result`; never add exclusion pragmas without approval.
5. Result: coverage per function before → after.
