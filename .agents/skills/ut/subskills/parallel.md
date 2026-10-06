# Parallel executors — what to lock (load only when Config says parallel)

The lock **mechanism** lives in the **team** skill, installed next to this one: the script `$SKILL_DIR/../team/bin/lock.sh`
and its rules in `$SKILL_DIR/../team/LOCKING.md`. **Read LOCKING.md now.** This file only says WHAT the ut skill
locks; that is part of the ut contract.
```sh
LOCK="$SKILL_DIR/../team/bin/lock.sh"; LD="$TASK/locks"; ME=E2      # repeat in every shell call
```
`$LOCK` missing → the team skill is not installed next to this one: tell the user that parallel mode needs it, or
run as a single executor. On a team job (`/team` is driving this run), use `mb lock --agent <your id> <command>`
instead of `bash "$LOCK" "$LD" <command> $ME`, with the same paths; the job posting's `locks:` dir should be `$TASK/locks`.

| Action | Command | Exit |
|--------|---------|------|
| take paths (all or none) | `bash "$LOCK" "$LD" acquire $ME <path>...` | 0 got all; 1 busy; 3 only STALE owners |
| wait for paths | `bash "$LOCK" "$LD" wait $ME 600 <path>...` | same |
| release | `bash "$LOCK" "$LD" release $ME <path>...` / `release-all $ME` | |
| declare long work | `bash "$LOCK" "$LD" alive $ME <seconds> "T03 full build"` | |
| who holds what | `bash "$LOCK" "$LD" status` | |

What the ut skill locks
1. Claim a task: `acquire $ME "$TASK/tasks/Tnn.md" <its Touches...>`. Exit 1 → next ready task; nothing ready →
   `wait $ME 600` on the first. Re-read the task Status after claiming; not TODO → release-all, pick again.
2. status.md, context.md, KB files: `wait` → re-read the section → edit only your rows → `release` within seconds.
   Never hold these while waiting for another lock.
3. Build/run: `alive $ME <2x expected seconds> "Tnn build"`, `wait $ME 1800` on KB `Paths written by build`
   (use `build-$ME` if each executor has its own folder), build, run, release those paths.
4. Checkpoint: `acquire $ME "$TASK/checkpoint-wave-N"` (exit 1 = someone else runs it). Closeout: `acquire $ME "$TASK/closeout"`.
   Refresh (subskills/refresh.md) locks `KB_DIR/index`, `KB_DIR/modules`, `KB_DIR/diagrams`, `KB_DIR/testscan.md`, `KB_DIR/last-refresh.md`.
5. Stale owner (`STALE-WARNING` or exit 3): LOCKING.md rule 7. Outside a team, ask the user "Is <ID> still running?
   May I remove its locks?"; only after yes: `reap <ID>`, then set its IN_PROGRESS tasks back to TODO.
6. Finish: `release-all $ME`.
