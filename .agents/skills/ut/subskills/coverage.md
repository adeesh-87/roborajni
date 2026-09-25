# Phase 7 — Coverage

Goal: a list of concrete gaps with an action each → context.md `Coverage gaps`. Load the coverage tool file.

## 1. Report
KB `Commands` has verified coverage rows → run them (delete old data files first; the tool file says which).
Unknown → Ask once: "How is the coverage report produced today? [I will try: <best guess from build files>]".
Use text/XML output when the tool allows (easy to grep). Record totals in status.md `Baseline`.
```sh
<coverage build> > "$TASK/logs/cov-build.log" 2>&1; <run all> > "$TASK/logs/cov-run.log" 2>&1; <report> > "$TASK/logs/cov-report.log" 2>&1
```

## 2. Gaps for in-scope files only
One row per function with uncovered lines/branches: file, function, now %, uncovered lines. Then open the card
(`KB_DIR/modules/*.cards.md`) and the source at each gap and set `Why` and `Action`:
| Why | Action |
|-----|--------|
| branch needs a specific input | `test`: write the input |
| error path of a dependency | `test`: mock returns the error |
| needs a state from earlier calls | `test`: list the call sequence |
| static, reached only indirectly | `test` via the public caller (KB Conventions say how statics are reached) |
| defensive code that cannot be reached | `ask` |
| hardware / timeout / infinite loop | `ask` (fake or exclusion) |
Never change production code to make coverage reachable unless Config allows it.
Show the table; `ask` rows → one message: "Justify, exclude or accept these? [accept as uncovered]".
`test` rows become work for the plan. Tick phase 7.
