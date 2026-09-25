# Phase 9 — Executor

Goal: do the plan's tasks one at a time; leave status.md, the task files and the KB current.

## 0. Once
- Know `TASK`, `SKILL_DIR`, `KB_DIR` (Config) and your ID `ME` (E1 unless the user gave one).
- Read ONLY: status.md `Config` and `Plan`; KB `Commands` and `Conventions`; `KB_DIR/exemplars/test.md`.
- Config `Parallel executors: yes` → load `subskills/parallel.md` now and follow its lock rules in every step below.
  Otherwise ignore every "(parallel)" note.
- Add your row to status.md `Executors`.

## 1. Pick
Ready = Status TODO, all `Depends on` DONE, earlier waves' checkpoints PASSED. Take the lowest ID.
None ready but some IN_PROGRESS → (single) they are yours: continue them; (parallel) wait per parallel.md.
Mark it IN_PROGRESS with Owner ME in status.md and in the task file; one Log line. (parallel: claim first.)

## 2. Load exactly the task's Inputs
The card file for its functions, `exemplars/test.md` (+ `mock.md` if the task mocks), the tool file, and
`resources/playbooks/<type>.md`. Nothing else, unless the playbook says so. Graph questions (`"$I" card|deps|tests`):
`I="$SKILL_DIR/resources/scripts/index.sh"; GD="$KB_DIR/index"` (details: `resources/graph-queries.md`).
Diagrams (`"$I" flow|seq "$GD" <function>`) help when the card is not enough: a coverage gap to reach (flow shows the
path and what is NOT HIT), or collaborators to fake (seq names the existing test doubles). How to read them: `resources/diagrams.md`.

## 3. Work
Follow the playbook. Write one test per `Cases` line, copying the exemplar's shape. Register new files like
`exemplars/register.md` shows. (parallel: only write paths in `Touches`; a missing path → PARTIAL, note it.)

## 4. Build and check
```sh
<build>             > "$TASK/logs/$ME-Tnn-build.log" 2>&1; echo "exit=$?"
<single-test cmd>   > "$TASK/logs/$ME-Tnn-run.log"   2>&1; echo "exit=$?"
```
Failure → read the FIRST error; load `resources/tools/errors/<tool>.md` (once); fix; retry. Max 3 attempts per
distinct error, then BLOCKED / PARTIAL with the error text in the task file. Never weaken an assertion.
Expected value disagrees with the code → do not change the test; open issue (category I); PARTIAL.
All pass → run the whole group of that module once.

## 5. Finish the task
Task file `Result`; status.md row DONE / PARTIAL / BLOCKED + Log line + new `Open issues`; learnings that a
later task needs → `KB_DIR/modules/<module>.md` `Learnings` (one line each, with file:line), build quirks → KB `Build notes`.

## 6. Checkpoint
All tasks of the current wave finished and no result recorded → full build + all tests → status.md `Checkpoints`:
`wave N: PASSED/FAILED (<tests>) <date> by ME`. FAILED → open issue, tell the user, do not start the next wave.
PASSED → load `subskills/refresh.md` once, so the next wave's cards show the tests and mocks this wave added.
(parallel: take the checkpoint lock first, see parallel.md.)

## 7. Stop
No task left → update your `Executors` row and `Next steps`. Every task finished and the last checkpoint ran →
load `subskills/closeout.md` (parallel: only the executor holding the `closeout` lock). Otherwise report: tasks
done, outcomes, open issues.
