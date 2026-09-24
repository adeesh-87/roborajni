# Sub-skill: coverage (phase 6)

Goal: a list of concrete coverage gaps (context.md section 7), each with an action.
Load the coverage tool file from Config `Resources to load`.

## Step 1 — How are reports made and where are they?
Check what is known: Config rows `Coverage tool`, `Coverage report location / format`,
status.md section 3 coverage rows, KB section 5, CI files (look for artifacts named
`coverage`, `CTCHTML`, `gcovr`, `lcov`, `cpptest`).
Ask what is still unknown:
1. "Is there an existing report I can use? Path and date? [generate a fresh one]"
2. "Which command or script creates the instrumented build and the report?"
3. "Report format you use: HTML, text, XML, JSON? [text is easiest for me]"
4. "Exclusions: tests, mocks, generated code, third-party? [tests + mocks]"
5. "Does coverage data survive a crash? Does the target need to send the data (embedded)?"
Record everything in status.md section 3 and Config.

## Step 2 — Generate the baseline report
Only with confirmed commands. Use a text or XML output if the tool supports it: it is easy to grep.
```sh
<coverage build> > "$TASK/logs/cov-build.log" 2>&1; echo "exit=$?"
<run tests>      > "$TASK/logs/cov-run.log"   2>&1; echo "exit=$?"
<report command> > "$TASK/logs/cov-report.log" 2>&1; echo "exit=$?"
```
Write the totals in status.md section 4 `Coverage:`. Save the report path and date in context.md 7.
Stale data warning: delete old data files first (the tool file says which ones).

## Step 3 — Extract gaps for in-scope files only
For each in-scope file, from the report, list per function: coverage now, uncovered lines,
uncovered branches or conditions. The tool file shows how to get this from text output.
One row per function in context.md section 7.

## Step 4 — Classify every gap
Open the source at each uncovered location and decide `Why uncovered`:
| Why | Action |
|-----|--------|
| Branch needs a specific input | `test` — write the input in the Action column |
| Error path: a dependency must fail | `test` — needs a mock/stub returning the error |
| Needs a state reached by earlier calls | `test` — list the call sequence |
| Static/internal function only reachable indirectly | `test` via the public caller, or per KB static-access convention |
| Defensive code that cannot be reached | `ask` — user decides: justify, exclude, or accept |
| Hardware, timeout, interrupt, infinite loop | `ask` — needs a fake or an exclusion |
| Debug / logging code compiled out | `exclude?` — ask |
Never add production-code changes to make coverage reachable unless Config allows it.

## Step 5 — Confirm
Show the gap table. Ask: "Approve the actions? Which `ask` rows should be justified or excluded?"
Record answers. Rows with action `test` become work for the planner.

## Finish
Tick phase 6, add a Log line.
