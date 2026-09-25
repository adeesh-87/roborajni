# Phase 4 — Discovery, mode "diff"

Goal: every changed code item and what it means for tests and mocks → context.md `Work items`.

## 1. Range
Default: this branch vs its base. If the user did not say, Ask once:
"Which changes? [branch vs origin/main]  (or: uncommitted only / commit range)". Record in context.md section 3 header.
```sh
git fetch origin 2>/dev/null; MB=$(git merge-base <base> HEAD)
git diff --name-status "$MB" -- <code paths> <test paths> <mock paths>
```
Changes inside test or mock paths: read them; someone may have started the work.

## 2. Changed items
```sh
git diff -W "$MB" -- <file>        # whole changed functions; header lines (@@) name the function ABOVE the hunk, not always the right one
```
For each changed function or item, one work-item row: file:function, change kind
(`added`, `modified-logic`, `signature`, `deleted`, `moved/renamed`, `type/macro`, `new-dependency`).
More than 40 changed functions → group by file, write `complex` next to the Work items header (the planner escalates).

## 3. Impact
Load `resources/impact-analysis.md`; fill the `Existing tests`, `Mocks affected`, `Proposed work`, `Cat` columns.
Show the table grouped by category. Tick phase 4.
