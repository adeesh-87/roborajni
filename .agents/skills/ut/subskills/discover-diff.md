# Phase 4 — Discovery, mode "diff"

Goal: the full list of what changed in the code under test and which tests, mocks and stubs each change touches,
so the user can pick from it. A script produces it; you only present it.

## 1. Range
Default: this branch vs its base. Not said in setup → Ask once:
"Which changes? [branch vs origin/main] (or: uncommitted only / a commit range A..B)".

## 2. Run the impact script
```sh
G="$SKILL_DIR/resources/scripts/graphify.sh"; GD="$KB_DIR/graphify"
"$G" refresh "$GD"                                                   # the graph must match the current code
"$G" impact "$GD" --base origin/main --out "$TASK/impact.md" --context "$TASK/context.md"
#            or:  --uncommitted        or:  --range A..B
```
It writes `TASK/impact.md` (summary, work-item table, details per item) and inserts the table rows into
context.md `Work items`. Each row: file:function, change kind (added, deleted, signature, modified-logic,
new-dependency, moved/renamed, type/macro), tests reaching it, mocks/stubs/fakes of it, proposed work, category.
Rows for test/mock files already changed on the branch are marked H: read them, do not redo that work.
Bash fallback (`MODE: codemap`): `impact` is unavailable; list changed functions with
`git diff -W <base> -- <file>` and fill the columns with `deps`/`tests` from the graph queries.

## 3. Present
Show the summary line and the table grouped by category. Do not read the details unless a row is unclear.
More than 40 rows → write `complex` next to the Work items header (the planner escalates). Tick phase 4.
