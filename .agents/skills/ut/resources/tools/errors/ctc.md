# Testwell CTC++ (Verifysoft) — quick reference: errors and fixes
## Problems
| Symptom | Fix |
|---------|-----|
| `MON.dat` not created | program crashed or was killed; fix the crash, or call `ctc_append_all()` before exit if the repo does that; check write permission and data file path |
| Coverage lower than expected / old numbers | stale `MON.dat` from earlier runs: delete and re-run |
| Warnings about timestamps / sym mismatch | sources changed after instrumentation: delete `MON.sym` + `MON.dat`, rebuild |
| Tests and mocks appear in the report | exclude them from instrumentation |
| Link errors about `ctc_` symbols | link step was not done through `ctc`/`ctcwrap`, add the CTC++ runtime library |
| Embedded target | data must be sent with the Host-Target add-on: ask the user for their procedure |
Parallel executors share `MON.sym`/`MON.dat` unless each has its own build folder: lock them.
