# Phase 4 — Discovery, mode "ask"

Goal: turn the request (Config `Request`, context.md section 1) into work items.

## 1. Resolve names to code
For every module, feature or function named in the request:
```sh
I="$SKILL_DIR/resources/scripts/index.sh"; GD="$KB_DIR/index"
"$I" find "$GD" '<name or regex>'          # functions, TEST blocks and externals with that name, and where they live
"$I" list "$GD" <file>                     # a module's functions when the request names a file
```
Nothing named, or ambiguous → Ask once: "Which files or functions exactly? [my guess: <list>]".
One work-item row per function (change kind `targeted`), or per file for "test this module" / coverage requests.

## 2. Impact
Load `resources/impact-analysis.md` for the `targeted` rows (existing tests, mocks, proposed work, category).
Coverage-only request → category G rows, no impact analysis. Broken build/run → category E/F rows from
context.md section 4.
Show the table grouped by category. Tick phase 4.
