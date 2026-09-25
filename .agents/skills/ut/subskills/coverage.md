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
Put the report into the code index; it maps every count onto the decisions of each function:
```sh
I="$SKILL_DIR/resources/scripts/index.sh"; GD="$KB_DIR/index"
"$I" cov-import "$GD" --gcov-dir <coverage build dir>     # or --lcov file.info | --ctc profile.txt (ctcpost -p) | --json file
"$I" uncovered "$GD" > "$TASK/coverage-gaps.md"           # never-run functions + never-taken outcomes, per function
"$I" diagrams "$GD" "$KB_DIR/diagrams"                     # flowcharts now show "Nx" / "NOT HIT" on every edge
```
(The ut tool does all of this with `ut coverage --cmd "<coverage build+run>" --gcov-dir <dir>` and adds the work items.)
One row per function with gaps: file, function, the gap lines from `coverage-gaps.md`. For each gap open the card and
`"$I" flow "$GD" <function>` (the path from `start` to the NOT HIT edge = the conditions a test must set) and set `Why` and `Action`:
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
