# Sub-skill: discover-ask (phase 3, mode "ask")

Goal: turn the user's description into concrete code items and candidate work.
Use for: a module, a feature, a ticket, a bug, "improve coverage of X", "fix the test build",
"remove tests of the old driver", or anything not covered by resume or diff mode.

## Step 1 — Interview
Ask (max 5 at a time, record answers in context.md sections 1, 2 and 8):
1. In your own words: what do you want at the end of this task?
2. Which files, modules, functions or features? [none given → I will search]
3. Are there documents to read: ticket, requirement, design doc, test spec, review comments,
   a failing log? Give paths. (record each in context.md section 2)
4. Is it one of these? a) new tests  b) update tests  c) remove tests  d) fix mocks/stubs
   e) fix test build  f) fix failing tests  g) coverage  h) other — several allowed
5. How will you judge it done? (all tests pass, coverage ≥ X %, reviewer checklist, ...)

## Step 2 — Read user files
For each file in context.md section 2: read it, write 3–8 key points in its row, set Read? = yes.

## Step 3 — Resolve to code items
Search for every named module, feature or function:
```sh
grep -rn '<name>' <code paths> | head -20
```
Fill context.md 3.1 with file, function and change kind `targeted` (no code change, the user
just wants work there). If the user named code that changed recently, ask whether to also run
`subskills/discover-diff.md` afterwards.

Special cases:
- Coverage only, no code change: fill 3.1 with the files to cover. Skip Step 4. Add one
  candidate row per file with category G.
- Build or run is broken: add a candidate row (E or F). Details come from phase 4.

## Step 4 — Impact analysis
Load `resources/impact-analysis.md` and follow it for every row of 3.1. Result: context.md 3.2.

## Step 5 — Candidate work
Write context.md section 5 from sections 3.2 and the interview. Show it grouped by category.
Ask: "Anything missing or wrong?" Fix it.

## Finish
Tick phase 3 in status.md, add a Log line.
