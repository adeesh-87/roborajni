# Testwell CTC++ (Verifysoft) — quick reference

CTC++ instruments C/C++ sources at compile time. The instrumented test program writes counters
when it exits. `ctcpost` makes listings, `ctc2html` makes HTML. **VERIFY options with `ctc -h`,
`ctcpost -h`, `ctc2html -h` for the installed version**; record verified commands in status.md section 3.

## Files
| File | Made by | Contains |
|------|---------|----------|
| `MON.sym` (symbol file) | `ctc` at compile time | code structure of instrumented files |
| `MON.dat` (data file) | the instrumented program at exit | execution counters (added up over runs) |
| `profile.txt` | `ctcpost -p` | Execution Profile Listing (text, per function / line) |
| `CTCHTML/index.html` | `ctc2html` | HTML report |
Names and locations can change with `-n`, `ctc.ini` settings or environment variables: check the build scripts.

## Instrumented build
Option A — prefix each compile AND link command:
```sh
ctc -i m gcc -c src/sensor.c -o build/sensor.o
ctc -i m gcc -o build/tests build/*.o      # link through ctc so the CTC++ runtime is linked
```
Option B — wrap the whole build (intercepts compiler calls configured in ctc.ini):
```sh
ctcwrap -i m make -C tests
ctcwrap -i m cmake --build build
```
Instrumentation level `-i`: `f` function, `d` decision, `m` multicondition. Use `m` for condition or
MC/DC reports. Instrument ONLY the code under test: exclude tests, mocks and framework
(e.g. `-C "EXCLUDE+*/tests/*"` or the project's ctc.ini — check how the repo does it).

## Run and report
```sh
rm -f MON.dat                                  # fresh data (and MON.sym after source changes)
./build/tests                                  # must EXIT normally to write MON.dat
ctcpost MON.sym MON.dat -p profile.txt         # execution profile listing
ctcpost MON.sym MON.dat -u untested.txt        # only untested code (smaller, good for gap search)
ctc2html -i profile.txt -o CTCHTML             # HTML
```
View options for listings (typical): `-ff` function, `-fd` decision, `-fc` condition, `-fmcdc` MC/DC.

## Reading the text listings
- Totals per function and file: `grep -n '\*\*\*TER' profile.txt` → lines like
  `***TER  75 % (  3/  4) of FUNCTION sensor_read()` and `... of FILE src/sensor.c`
  (TER = test effectiveness ratio = coverage for the chosen measure).
- In the listing, each decision line shows how often it was true and false. A count of `0` / `-`
  in one column marks the missing outcome; untested.txt lists exactly those lines.
- For each gap write `file:line`, the condition text and which outcome (true/false, which condition) is missing.

## Excluding code (only with user approval)
```c
#pragma CTC SKIP
... code not measured ...
#pragma CTC ENDSKIP
#pragma CTC ANNOTATION reason text      /* documents a justification in the report */
```

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
