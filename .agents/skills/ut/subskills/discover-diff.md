# Phase 4 — Discovery, mode "diff"

Goal: the full list of what changed in the code under test and which tests, mocks and stubs each change touches,
so the user can pick from it. A script produces it; you only present it.

## 1. Range
Default: this branch vs its base. Not said in setup → Ask once:
"Which changes? [branch vs origin/main] (or: uncommitted only / a commit range A..B)".

## 2. Run the impact script
```sh
I="$SKILL_DIR/resources/scripts/index.sh"; GD="$KB_DIR/index"
"$I" refresh "$GD"                                                   # the index must match the current code
"$I" impact "$GD" --base origin/main --out "$TASK/impact.md" --context "$TASK/context.md"
#            or:  --uncommitted        or:  --range A..B
```
It writes `TASK/impact.md` (summary, work-item table, details per item) and inserts the table rows into
context.md `Work items`. Each row: file:function, change kind (added, deleted, signature, modified-logic,
new-dependency, moved/renamed, type/macro), tests reaching it, mocks/stubs/fakes of it, proposed work, category.
Rows for test/mock files already changed on the branch are marked H: read them, do not redo that work.
`impact` failed (index missing or stale) → `"$I" refresh "$GD"` and run it again.

## 3. Present
Show the summary line and the table grouped by category. Do not read the details unless a row is unclear.
More than 40 rows → write `complex` next to the Work items header (the planner escalates). Tick phase 4.
