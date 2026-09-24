# Sub-skill: closeout (phase 9)

Goal: prove the final state, record it, and leave the task folder and KB ready for the future.

## Step 1 — Final verification
1. Parallel mode: `"$SKILL_DIR/resources/scripts/lock.sh" "$TASK/locks" status`. Only your own
   locks may remain. Others → ask the user whether those executors are still running (STALE ones
   are reported as such; `reap` only with approval).
2. Clean build and run all tests (commands from status.md section 3):
   ```sh
   <clean> ; <build> > "$TASK/logs/final-build.log" 2>&1; echo "exit=$?"
   <run all> > "$TASK/logs/final-run.log" 2>&1; echo "exit=$?"
   ```
3. If coverage is in scope: coverage build, run, report → `logs/final-cov-*.log`.
   Compare with the baseline, per in-scope file.

## Step 2 — Update status.md
Add a section `## 10. Final summary` directly after `Log`:
```
Date:
Tasks: <done>/<total> done, <n> partial, <n> blocked, <n> dropped  (<percent> % done)
Build: OK / FAILED     Tests: <passed>/<total> (baseline: <passed>/<total>)
Coverage: <metric> <before> % → <after> % (target <x> %)   per file: ...
Scope items met: S1 ✔, S2 ✔, S3 ✘ (reason)
Open issues: <count> — see section 7
Production bugs reported (category I): ...
```
Rewrite `Next steps` so a new session can continue with no other context.
Set `Current phase: 9 (done)` and tick phase 9. Add a Log line.

## Step 3 — Update KB (durable knowledge)
1. Merge duplicate lines in section 7 (Learnings). Keep them short, with a source.
2. Move learnings that describe a convention into section 3 or 4, build facts into section 5,
   module logic into section 6.
3. Rebuild the code map (and the code graph, if `KB_DIR/graphify` exists) so they include the new tests and mocks:
   `"$SKILL_DIR/resources/scripts/codemap.sh" "$KB_DIR/codemap" <code paths> <test paths> <mock paths>`
   `"$SKILL_DIR/resources/scripts/graphify.sh" build [--cdb <compile DB>] "$KB_DIR/graphify" <code paths> <test paths> <mock paths>`
   Update section 2 (code map table) with new test and mock files.
4. Set `Last updated` in the KB and in `resources/kb/INDEX.md`.
5. Tell the user the KB lives in the skill folder: keep `resources/kb/` when they update the skill.

## Step 4 — Report to the user
Give: the final summary numbers, files changed (grouped: tests, mocks, build), open issues,
suggested next steps. Remind them nothing was committed if Config says the user commits.
Parallel: `"$SKILL_DIR/resources/scripts/lock.sh" "$TASK/locks" release-all <your ID>`.
