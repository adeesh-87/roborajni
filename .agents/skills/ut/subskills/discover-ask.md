# Phase 4 — Discovery, mode "ask"

Goal: turn the request (Config `Request`, context.md section 1) into work items.

## 1. Resolve names to code
For every module, feature or function named in the request:
```sh
grep -rn '<name>' <code paths> | head -20
awk -F'\t' '{print $1}' "$KB_DIR/codemap/functions.tsv" 2>/dev/null | sort -u | grep -i '<name>'   # or: index.sh card "$KB_DIR/index" <file> lists its functions
```
Nothing named, or ambiguous → Ask once: "Which files or functions exactly? [my guess: <list>]".
One work-item row per function (change kind `targeted`), or per file for "test this module" / coverage requests.

## 2. Impact
Load `resources/impact-analysis.md` for the `targeted` rows (existing tests, mocks, proposed work, category).
Coverage-only request → category G rows, no impact analysis. Broken build/run → category E/F rows from
context.md section 4.
Show the table grouped by category. Tick phase 4.
