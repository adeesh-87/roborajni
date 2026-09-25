# Parallel executors — lock protocol (load only when Config says parallel)

Locks protect PATHS. Anything with a path can be locked, also names that do not exist yet.
```sh
LOCK="$SKILL_DIR/resources/scripts/lock.sh"; LD="$TASK/locks"; ME=E2      # repeat in every shell call
```
| Action | Command | Exit |
|--------|---------|------|
| take paths (all or none) | `"$LOCK" "$LD" acquire $ME <path>...` | 0 got all; 1 busy; 3 only STALE owners |
| wait for paths | `"$LOCK" "$LD" wait $ME 600 <path>...` | same |
| release | `"$LOCK" "$LD" release $ME <path>...` / `release-all $ME` | |
| declare long work | `"$LOCK" "$LD" alive $ME <seconds> "T03 full build"` | |
| who holds what | `"$LOCK" "$LD" status` | |

Rules
1. Lock before you write. Take everything a step needs in ONE `acquire`. Release when done.
2. Claim a task: `acquire $ME "$TASK/tasks/Tnn.md" <its Touches...>`. Exit 1 → next ready task; nothing ready →
   `wait $ME 600` on the first. Re-read the task Status after claiming; not TODO → release-all, pick again.
3. status.md, context.md, KB files: `wait` → re-read the section → edit only your rows → `release` within seconds.
   Never hold these while waiting for another lock.
4. Build/run: `alive $ME <2x expected seconds> "Tnn build"`, `wait $ME 1800` on KB `Paths written by build`
   (use `build-$ME` if each executor has its own folder), build, run, release those paths.
5. Checkpoint: `acquire $ME "$TASK/checkpoint-wave-N"` (exit 1 = someone else runs it). Closeout: `acquire $ME "$TASK/closeout"`.
   Refresh (subskills/refresh.md) locks `KB_DIR/graphify`, `KB_DIR/modules`, `KB_DIR/testscan.md`, `KB_DIR/last-refresh.md`.
6. Every lock call is a heartbeat. Silence longer than `stale_after` makes you STALE to others.
7. `STALE-WARNING` line or exit 3 → STOP, show the user that line, ask "Is <ID> still running? May I remove its
   locks?". Only after yes: `reap <ID>`, set its IN_PROGRESS tasks back to TODO. Never `reap --force` or `break`
   on your own.
8. Finish: `release-all $ME`.
`Permission denied` → `chmod +x "$LOCK"`. Needs bash (Git Bash / WSL on Windows).
