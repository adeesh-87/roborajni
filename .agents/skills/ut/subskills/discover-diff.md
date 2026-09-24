# Sub-skill: discover-diff (phase 3, mode "diff")

Goal: know every code change and what it means for tests and mocks. Result: context.md
sections 3 and 5.

## Step 1 — Agree on the range
Ask: "Which changes? [branch vs its base]"
 1) this branch vs base branch — which base? [origin/main or origin/master]
 2) uncommitted changes only
 3) a commit range or list of commits
 4) branch + uncommitted
Record the answer in context.md section 3 `Base ref`.

Commands (pick what matches; `BASE` = base ref):
```sh
git fetch origin 2>/dev/null
MB=$(git merge-base BASE HEAD)
git diff --stat "$MB" -- <code paths> <test paths> <mock paths>     # branch vs base
git diff --stat HEAD -- <code paths> <test paths> <mock paths>      # uncommitted (staged + unstaged)
git diff --name-status "$MB" -- <code paths>
```

## Step 2 — List changed items
For each changed source or header file:
```sh
git diff -U0 "$MB" -- <file> | grep -E '^@@' | head -40   # hunk headers usually name the function
```
The name in a hunk header is the last function-like line ABOVE the hunk. It is often wrong
(e.g. when the change is on the function's first line). ALWAYS open the file at the new line numbers
(`+<line>` in the header) and read which function contains them. For whole changed functions:
`git diff -W "$MB" -- <file>` shows each changed function completely. Fill context.md 3.1.
Change kinds: `added`, `modified-logic`, `signature` (params/return/qualifiers changed),
`deleted`, `moved/renamed`, `type/macro` (struct, enum, #define, typedef), `new-dependency`
(the function now calls something it did not call before).
Also list changes inside test and mock paths: someone may have started the work already.

If more than 40 functions changed: stop listing details. Group by file, tell the user, and
mark the task "complex" in context.md section 8 (the planner will escalate).

## Step 3 — Impact analysis
Load `resources/impact-analysis.md` and follow it for every row of 3.1. Result: context.md 3.2.

## Step 4 — Candidate work
Turn each impact row into one or more rows in context.md section 5 with a category letter.
Show the list grouped by category. Ask: "Anything missing or wrong?" Fix it.

## Finish
Tick phase 3 in status.md, add a Log line.
