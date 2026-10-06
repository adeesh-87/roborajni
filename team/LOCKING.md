# Locking shared resources

Agents working at the same time share files, build folders, coverage data and task state. Two writers on the same path corrupt it. A reviewer reading a half-written file judges the wrong thing. **Locks** prevent both.

A lock protects one **path**: a file, a directory, an executable, or a name that does not exist yet (to reserve it, or to use it as a named mutex such as `<task dir>/checkpoint`).
- Locking a **directory** also locks everything inside it.
- A lock on a **file** blocks anyone from locking a directory that contains it.
- All paths in one call are taken **all or nothing**.
- Locks are files on disk (`<lock dir>/held/`), so they survive crashed agents and restarts.

## Calling it

**Team members** use `mb lock`. It reads the lock directory from the `locks:` line of the team's shared context and fills in your agent id as the owner:
```bash
mb lock --agent <your id> <command> [args...]
```
**Other workers** (for example the ut skill's parallel executors) call the script directly. It ships in this skill as `bin/lock.sh`:
```bash
bash <team skill dir>/bin/lock.sh <lock dir> <command> [owner] [args...]
```

| Action | `mb lock --agent <you> ...` | Exit codes |
|---|---|---|
| Take paths (all or none) | `acquire <path>...` | 0 got all · 1 held by an active owner · 3 held only by STALE owners |
| Wait for paths, up to N seconds | `wait <N> <path>...` | same |
| Release paths | `release <path>...` | |
| Release everything you hold | `release-all` | |
| Declare long work (build, test run) | `alive <seconds> "<what>"` | |
| Is anything locked? (readers) | `check <path>...` | 0 all free · 1 something is locked |
| Who holds what | `status` (or `list`) | |

Always use **absolute paths**.

## Rules
1. **Lock before you write.** Before writing a shared path, or running a command that writes to one (build, test run, coverage, a script that updates task state), acquire it. Take everything one step needs in **one** `acquire`. Taking locks one at a time while holding others is how deadlocks happen.
2. **Release as soon as the step is done.** Never keep a lock "for later".
3. **Never wait while holding locks.** Release everything before you wait for a message, a review or a teammate (`mb inbox --wait`). The only exception is `wait`ing for the next lock of the **same** step, and only on paths no teammate needs to finish their current step.
4. **Long work: declare it first.** Before a build or test run longer than a few minutes, run `alive <2x the expected seconds> "<what>"`. Every lock call is a heartbeat. An owner silent for longer than `stale_after` (default 30 minutes, set with `stale_after=SECONDS` in `<lock dir>/config`) and not inside a declared busy window becomes **STALE** to everyone else.
5. **Readers check before they read.** Before reviewing files, run `check` on them. Exit 1 means someone is mid-write: don't review a half-written state. Wait for their next `SYNC`, or `wait` briefly and check again.
6. **Busy (exit 1):** do something else that doesn't need those paths, or `wait`. Never edit a locked path, and never work around a lock by using a different path for the same resource.
7. **Stale owner (exit 3, or a `STALE-WARNING` line):** **never `reap`, `break` or `--force` on your own.**
   - **In a team:** if the stale owner is a teammate, message them (`mb pub agent/<their id> "BLOCKED: you hold <path>, still working?"`) and wait up to 10 waits. If they don't answer and are still STALE, post `BLOCKED:` with the STALE-WARNING line. Only the **lead** (or the proposer, if the roster has no lead) may then run `reap <their id>` and post `NOTE: reaped <id>` with the reason. Never reap an owner that is not in your team; post `BLOCKED` and work on something else or stop.
   - **Outside a team** (a human is present): show the STALE-WARNING line to the user and ask "Is <id> still running? May I remove its locks?". Reap only after a yes.
8. **Finish clean.** When you are done, run `release-all`, then `status` to confirm you hold nothing.

## Where the lock directory lives
The context owner chooses it and puts it in the shared context as `locks: <absolute path>`. Normally that is `<task dir>/locks`, next to the state it protects, so a resumed run sees the old locks. Without a task directory, use `<repo>/.locks` (add it to `.gitignore`). Everyone working on the same resources must use the **same** lock directory, or the locks protect nothing.

Watch the locks from a human terminal: `bash <team skill dir>/bin/lock.sh <lock dir> watch 10`.
