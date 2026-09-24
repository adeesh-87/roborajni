# Sub-skill: executor (phase 8)

Goal: carry out tasks from the approved plan, one at a time, and leave status.md, the task
files and KB up to date so anyone can continue.

## 0. Setup (once)
1. Know `TASK`, `SKILL_DIR` and your executor ID `ME` (E1, E2, ...). If the user did not
   give an ID, ask. Never use an ID another running executor uses.
2. Read ONLY: status.md sections 1 (Config), 3 (Commands), 5 (Plan); KB section 3 (conventions)
   and 5 (build notes); the tool files in Config `Resources to load`; `resources/test-design.md`.
3. Mode: Config `Parallel executors` = yes → **parallel mode** (use locks). Otherwise single mode.
4. Define for all shell calls (repeat these lines in each call, shell state is not kept):
   ```sh
   LOCK="$SKILL_DIR/resources/scripts/lock.sh"; LD="$TASK/locks"; ME=E1
   ```
   `Permission denied` → run `chmod +x "$SKILL_DIR/resources/scripts/lock.sh"` once. The script needs
   bash (on Windows: Git Bash or WSL). Test it: `"$LOCK" "$LD" status` must print a table.
5. Add or update your row in status.md section 6 (Executors). In parallel mode lock status.md first (see 2).

## 1. Lock rules (parallel mode only)
- Anything with a path can be locked: source, test, mock, build file, folder, executable,
  script, report, and also names that do not exist yet (e.g. `$TASK/checkpoint-wave-1`).
- Lock BEFORE you write a path. Release it when you are done with it.
- Take all paths you need in ONE `acquire` call. It gets all or none, so there is no deadlock.
- Never write a path you have not locked. Never release or break another executor's lock.
- Leaf locks: while you hold status.md, KB, context.md or the build paths, do NOT acquire or wait
  for any other lock. Take them last, hold them briefly, release them. This keeps waiting deadlock-free.
- Locks only say "busy now". Results (task done, checkpoint passed) are written in status.md.
- Every lock.sh call with your ID is a heartbeat. If you are silent longer than `stale_after`
  (default 30 min, set in `$TASK/locks/config`) other executors see you as STALE.
  Before anything long (full build, whole test run, coverage) declare it:
  `"$LOCK" "$LD" alive $ME <seconds, about 2x the expected time> "T03 full build"`.
- Exit codes of `acquire` / `wait`: `0` got all; `1` held by an ACTIVE or BUSY executor: pick other
  work or wait; `3` held only by STALE owners: see below.
- Any output line `STALE-WARNING: owner E2 ...` or exit code 3: STOP and tell the user exactly that line,
  e.g. "E2 was last seen 2h ago and still holds 3 locks. Is E2 still running? May I remove its locks?"
  Only after the user says yes: `"$LOCK" "$LD" reap E2`, then set E2's IN_PROGRESS tasks in status.md
  back to TODO with a Log line. Never reap on your own. Never use `reap --force` or `break` unless
  the user explicitly asks.

| Action | Command |
|--------|---------|
| Claim a task | `"$LOCK" "$LD" acquire $ME "$TASK/tasks/T03.md"` |
| Take task paths | `"$LOCK" "$LD" acquire $ME <path1> <path2> ...` |
| Wait for a shared file | `"$LOCK" "$LD" wait $ME 300 "$TASK/status.md"` |
| Release one path | `"$LOCK" "$LD" release $ME <path>` |
| Release everything | `"$LOCK" "$LD" release-all $ME` |
| Heartbeat / declare long work | `"$LOCK" "$LD" alive $ME 3600 "T03 coverage run"` |
| Who holds what, who is stale | `"$LOCK" "$LD" status` |

## 2. Editing shared files (status.md, KB, context.md)
Parallel mode: `wait` for the lock → re-read the section (another executor may have changed it)
→ edit only your rows → `release`. Keep the lock for seconds, not minutes.
Single mode: just edit.

## 3. Task loop
Repeat until no task is left for you.

**3.1 Pick.** A task is ready when: Status = TODO; every `Depends on` task is DONE; every
earlier wave's checkpoint is PASSED. Take the ready task with the lowest ID.
No ready task but others are IN_PROGRESS → wait 2 minutes, re-read the plan, try again (max 10 times),
then report "waiting on <tasks>" to the user and stop.

**3.2 Claim.** Parallel: `acquire` the task file. Exit 1 → pick the next ready task.
Then `acquire` every path in the task's `Touches` in one call. Exit 1 → `release` the task file,
pick another task. If every ready task is blocked, wait for the first one, all paths in one call:
`"$LOCK" "$LD" wait $ME 600 "$TASK/tasks/Tnn.md" <touch1> <touch2> ...`
After claiming, re-read the task's Status in status.md: if it is no longer TODO, release-all and pick again.

**3.3 Mark started.** status.md: Status = IN_PROGRESS, Owner = ME. Task file: same. Log line.
Parallel: `"$LOCK" "$LD" alive $ME 0 "Tnn <title>"` so `status` shows what you are doing.

**3.4 Do the work.** Load `resources/playbooks/<Type>.md` for the task's Type and follow it.
Read only the task's Inputs. Imitate the existing test named in Inputs.
If you must write a path that is not in Touches: parallel → try `acquire` it; if it fails,
write down what you need in the task Result and go to 3.6 with PARTIAL.

**3.5 Build and check.**
Parallel: `alive $ME <2x build+run seconds> "Tnn build"`, then `wait $ME 1800` on every path in
status.md "Paths to lock while building or running"
(replace `<EXEC_ID>` with ME). Build, run the task's tests with the single-test command, then
release those paths right away.
```sh
<build command> > "$TASK/logs/$ME-Tnn-build.log" 2>&1; echo "exit=$?"
<single-test command> > "$TASK/logs/$ME-Tnn-run.log" 2>&1; echo "exit=$?"
```
Failure → read the first error, fix, retry. At most **3 fix attempts per distinct error**.
Still failing → stop this task with BLOCKED or PARTIAL. Never weaken or delete an assertion to
make a test pass. If a test shows the production code is wrong, record it (category I) and ask.

**3.6 Finish the task.**
1. Fill the task file `Result`: outcome, files changed, tests added/changed/removed, build + run
   result, notes, open issues.
2. status.md (locked): Status = DONE / PARTIAL / BLOCKED, one Log line, new rows in `Open issues`.
3. KB (locked): add useful learnings to section 7, one line each, e.g. "mock of `spi_write` must
   set the out-buffer, see tests/mocks/spi_mock.c:40". New module facts → section 6.
4. Parallel: `"$LOCK" "$LD" release-all $ME`.

**3.7 Checkpoint.** If every task of your wave is now DONE, PARTIAL, BLOCKED or DROPPED and
status.md has no result yet for this wave's checkpoint:
- Parallel: `acquire $ME "$TASK/checkpoint-wave-<N>"`. Exit 1 → someone else is running it; go to 3.1.
  Got it → re-read Checkpoints in status.md; if a result is already there, release and go to 3.1.
- Take the build lock paths, run the FULL build and ALL tests, release the build paths.
- Write `wave N: PASSED <date> by <ME>` or `wave N: FAILED (<failing tests>) <date> by <ME>` under
  Checkpoints in status.md. FAILED → add a row to `Open issues`, tell the user, do not start the next wave.
- Release the checkpoint lock.

## 4. Stop
When no task is left for you:
1. Update your row in status.md section 6 and write `Next steps`.
2. If every task in the plan is DONE, PARTIAL, BLOCKED or DROPPED and the last checkpoint ran:
   parallel → `acquire $ME "$TASK/closeout"`; if you get it AND phase 9 in status.md is not ticked
   and has no "closeout by" note, write "closeout by <ME>" next to phase 9 and load `subskills/closeout.md`.
   Single mode → load `subskills/closeout.md`.
3. Otherwise report to the user: tasks you did, their outcome, open issues. Release all locks.
