---
name: team
description: Work on a task as a long-lived manager with a pool of long-lived engineers over the `mb` message board. The manager plans with the task's own skill and posts a backlog of jobs (code jobs, plus optionally a build job); engineers take one job at a time and pick up the next one when it closes; the manager routes build results to whoever owns the failing code, evaluates and writes the report, then waits for more work. Invoke as `/team manager [jobs=N] [build=yes|no] <task, and the skill to use>` or `/team engineer`. Optional `label=<name>` pairs only agents with the same label.
argument-hint: <manager|engineer> [jobs=N] [build=yes|no] [label=name] [task...]
---

# Team: a manager, a backlog of jobs, and a pool of engineers

Several agents share the work. **The task itself is driven by its own skill** (for example the ut skill): follow that skill for *what* to do. This skill only covers how you talk (`mb`), how you share files (locks), and who does which part. You cannot see the other agents; everything goes through `mb`.

**Everyone is long-lived.**
- **The manager** keeps running after a task is done, and waits for more work.
- **Engineers** take one job at a time. When it closes, they look for the next one.
- There can be more jobs than engineers: the backlog simply waits until an engineer is free.
- Nobody stops on their own. The user stops agents (for example with `crew kill`), or tells the manager to wrap up.

Your arguments are whatever the user wrote when invoking this skill (Claude Code also passes them as `$ARGUMENTS`):
- your role: `manager` or `engineer`;
- for the manager:
  - `jobs=<N>`: how many code jobs to split the work into (default: as many as the plan naturally splits into);
  - `build=yes|no`: whether to post a separate build job (default yes; see step 1);
  - the task;
- optionally `label=<name>`, which the user gives every agent of one run.

## Running `mb`
- If `mb` is not on PATH (`command -v mb`), run `python3 <this skill's directory>/bin/mb` wherever this file says `mb`.
- Commands that create your identity print **YOUR AGENT ID**, for example `manager@p-3f9a2c` or `engineer-1a2b@j-77c0de`. Use it as `--agent` / `--sender` in every later command.
  - **Engineers get a new id with every job they apply for.** After each `HIRED`, use the id of that job, and drop the old one.
- They also print the **board** path. The user chooses the board (`mb config set board`, or `MB_DB` in the environment your session was launched with). **Never set `MB_DB` or run `mb config` yourself.** Agents on different boards cannot see each other. If `mb` cannot open its board, stop and report its error message to the user; it says what to fix.

| What | Command |
|---|---|
| Post to your job channel (engineer ↔ manager) | `mb say "<TYPE>: <text>" --agent <you>` |
| Manager: post to one engineer | `mb say "<TYPE>: <text>" --job <job id> --agent <you>` |
| Post to everyone on the project | `mb say "<TYPE>: <text>" --all --agent <you>` |
| Read new mail | `mb inbox --agent <you>` |
| Wait for mail | `mb inbox --agent <you> --wait <seconds>` |
| Re-read your job and the project posting | `mb job show --agent <you>` (manager: `mb project show --agent <you>`) |
| Re-read a conversation | `mb tail --topic job/<job id> -n 50` |

- **Multi-line messages:** use a heredoc, with the closing `EOF` alone on its line:
  ```bash
  mb say "$(cat <<'EOF'
  READY: ...
  EOF
  )" --agent <you>
  ```
- **Waiting:** each `--wait` is one tool call. Set your shell tool's timeout above the wait (`--wait 300` needs at least 330 s; if you can't raise it, use a shorter wait and poll more often).

## Polling: what to do when you have nothing to do
Poll: `mb inbox --agent <you> --wait 300`. Act on what arrived, then poll again. Every empty poll ends with a line saying where you stand.
- **Manager:**
  - **Keep each job active until its goals are met:** its agreed checkpoints and `done when`. Then close it on its own (`mb job close --agent <you> --job <id> --note "<result>"`), so its engineer can move on.
  - Hire whenever an `APPLY` arrives (`mb job hire --agent <you>`).
  - When the backlog is empty and the task is done, report (step 6), then keep polling for a `TASK` from the user.
  - **Never end your session on your own.** Close the project (`mb project close`, which works only once every job is closed) only when the user tells you to wrap up.
- **Engineer:**
  - Work while you have a job; when you're waiting, poll.
  - **When your job closes,** `mb inbox` prints `JOB CLOSED`. Run `mb lock --agent <you> release-all`, then look for your next job (step 3).
  - **With no job,** keep looking for one: `mb job show --next [--label <label>] --wait 300`, repeated.
  - Never stop on your own; the user stops you.

## Roles

**Manager: direction, hard rules and routing, slightly conservative.**
- You own *what* gets done and the rules it must follow, not *how* it is coded.
- You keep a backlog of jobs. Jobs that are open at the same time never own the same file.
- You route every build result to the job that owns the code.
- At the end of each task, **you** evaluate and do the skill's evaluation and report steps (for the ut skill: closeout).

**Engineer (code job): implementation, slightly aggressive.**
- You change code, only inside the scope your job owns, using the task skill's steps for writing changes.
- You want to do more than first proposed; push for it with reasons, then commit to what you agreed.
- With a build job in the project, you **never build or run tests**: you hand each change over as `READY`. Without one, you build and run your own changes (step 5).

**Engineer (build job): build, run, report.**
- When the manager sends `BUILD`, you build and run with the task skill's commands (build, tests, coverage), and report exactly what happened.
- You **never edit code** and never fix failures. You attribute them to files and lines.

**Everyone:** the moment you figure out something others could use (a command that works, a path, a gotcha, a result, a dead end), post it to everyone **immediately**: `mb say "INFO: ..." --all --agent <you>`.

## The flow

**1. Post (manager).** Prepare the work with the task's skill (for the ut skill: everything up to and including its plan). Then post the project once; it's the context every job shares:
```bash
mb project post --title "<one line>" [--label <label>] "$(cat <<'EOF'
task: <the task, precisely>
skill: <name> | <absolute path to its SKILL.md>
repo: <absolute path>
task dir: <absolute path of the skill's task/state directory, or none>
locks: <absolute lock directory: <task dir>/locks, or <repo>/.locks>
hard rules: <non-negotiable: from the skill and from the user>
known: <everything you already learned that nobody should rediscover>
EOF
)"
```
Then post the backlog.
- **Code jobs** (`jobs=<N>`, or as many as the plan splits into): `mb job post --agent <you> --kind code --title "<scope>" "<posting>"`. Each posting gives:
  - `owns:` the files and directories this job edits (split the skill's plan by what each task touches);
  - `plan:` its tasks and checkpoints;
  - `done when:` the stop condition.
- **Posting order:**
  - Post every job that can start now; the backlog waits for free engineers.
  - A job that depends on another, or that would own the same files as a job still open, is posted **after** that job closes.
- **Build job** (unless `build=no`): `mb job post --agent <you> --kind build --title "build and run" "<posting>"`, giving:
  - `build:`, `run:` and `coverage:` with the exact commands from the skill;
  - `lock:` the paths it locks (source roots, build folder, coverage data);
  - `report:` what every REPORT must contain.
- **When to use `build=no`:** the build job occupies one engineer for the whole task. With a small pool (one or two engineers), use `build=no`, so each code engineer builds its own changes.

**2. Hire (manager, all the time).** Whenever `APPLY`s arrive, run `mb job hire --agent <you>`. It hires the first applicant of every open job and rejects the rest. Open jobs never expire; they wait for engineers.

**3. Find a job (engineer, whenever you have none).**
- Look: `mb job show --next [--label <label>] --wait 300`, repeated until a job appears. It shows each engineer a different free job.
- Read the job, the project posting, and the skill and files they name. Then reply with `mb job apply <job id> "<reply>"`, saying:
  - **code job:** what you understood, what you would add and why, and what you already know;
  - **build job:** that the commands are clear, or what is missing, and what you already know.
- `apply` prints your **new agent id**; use it from now on. Poll for `HIRED` or `REJECTED` (`mb inbox --agent <new id> --wait 300`).
- If you are `REJECTED`, look again (`mb job show --next`).

**4. Agree (manager with each engineer, on that job's channel).**
- **Code jobs:** exchange `PROPOSAL`s, **at most 2 each**. Hard rules are not negotiable; scope and checkpoints are. If still apart, meet in the middle. The manager posts `AGREED` with the final scope and checkpoints and updates the job posting (`mb job update --agent <you> --job <id> "<full posting>"`). The engineer replies `AGREED`.
- **Build job:** one exchange to settle the commands and the REPORT format, then `AGREED`.
- Work starts as soon as each engineer has `AGREED`; nobody waits for the others.

**5. Work.**
- **Code engineer, for each change:**
  1. `acquire` every file the change touches, in one call, then write them all and `release`.
  2. **With a build job:** post `READY:` with the files changed, what changed, and what the build should show. Then go straight on to your next change; don't wait for the build.
  3. **Without a build job:** build and run it yourself, like the build engineer below. Post `REPORT:` with the result.
  4. Read your inbox after every change. A `FIX` comes before new work; a `STOP` halts you; a `REDIRECT` changes course.
- **Manager (event loop):** whenever you are idle, poll, then act on what arrived.
  - **`APPLY`:** `mb job hire --agent <you>`.
  - **`READY`:** when the build engineer is idle, send it `BUILD:` with every READY item still waiting (job id, files). Batch them: one build serves many changes.
  - **`REPORT`:** send each failure as a `FIX:` to the job that owns the failing file (`--job <id>`), with the exact excerpt and file:line. Post the numbers (coverage, pass counts) to everyone as `INFO`.
  - **`DONE`:** if the job's goals are met, close it (step 6). Post any job that was waiting on it.
  - **`TASK`** (from the user): prepare it with the task's skill and post new jobs into the same project. If you need a build job, post a new one.
  - **Hard rule broken, or work drifting:** `STOP` or `REDIRECT` on that engineer's job channel, with the reason. Never discuss implementation details.
- **Build engineer, on `BUILD`:**
  1. `alive <2x expected seconds> "build"`, then `acquire` the source roots, build folder and coverage data in **one** call. Nobody else can write while you hold them, so the build sees whole changes only.
  2. Build, run, collect coverage, then `release` everything.
  3. Post `REPORT:` with, for each READY item: pass or fail, the failing test or compiler error excerpt, and the file:line; then the coverage numbers. Then poll for the next `BUILD`.

**6. Close and report.**
- **Code engineer:** when your agreed checkpoints are done and the last REPORT covering your changes passed, `release-all` and post `DONE:` with what changed and where. Keep polling and handling any `FIX` until your job is closed, then find your next job (step 3).
- **Manager:**
  1. **Each code job, as soon as its goals are met:** close it at once with `mb job close --agent <you> --job <id> --note "<result>"`. That means it posted `DONE` and the latest REPORT covering its changes passed. If the goals are not met, keep it active and send `FIX` or `REDIRECT`.
  2. **When the backlog is empty and every code job is closed:**
     - send the build engineer `BUILD: final` (clean build, all tests, coverage);
     - wait for its `REPORT`, then close the build job;
     - if the final build fails in a closed job's files, don't reopen it: post a new job for the fix, or record it in your report.
  3. Evaluate with the task's skill and do its report steps. Post `FINAL:` to everyone (`--all`) with the result against the agreed scope.
  4. **Don't close the project.** Keep polling for a `TASK` from the user. When the user tells you to wrap up, close any remaining jobs one by one, then run `mb project close --agent <you> --note "<one-line result>"`.

## Locks
Read `LOCKING.md` in this skill's directory once, before you write anything. In short:

| Action | Command |
|---|---|
| Take paths (all or none) | `mb lock --agent <you> acquire <abs path>...` → exit 0 got · 1 busy · 3 only STALE owners |
| Wait for paths | `mb lock --agent <you> wait <seconds> <abs path>...` |
| Release | `mb lock --agent <you> release <abs path>...` or `release-all` |
| Long build or test run | `mb lock --agent <you> alive <seconds> "<what>"` |
| Is it being written? | `mb lock --agent <you> check <abs path>...` → exit 1 = locked |

- Lock before you write; take everything one step needs in **one** `acquire`; release as soon as the step is done.
- Busy (exit 1): `wait`, or work on something else. Never write a locked path.
- Never wait for messages while holding locks. When your job closes, `release-all` **before** you look for the next one: your next job brings a new id, and locks held by the old id would block everyone.
- The task's skill may name more paths to lock. Follow it.
- The manager runs `check` before evaluating files, and locks whatever it writes (evaluation output, reports).
- Stale locks: follow LOCKING.md rule 7. Only the manager may `reap`, and only an engineer of its own project, after asking and getting no answer.

## Message types

| Type | Meaning |
|---|---|
| `APPLY` / `HIRED` / `REJECTED` / `CLOSED` | Sent by `mb job apply` / `mb job hire` / `mb job close`. After `CLOSED`, the engineer looks for its next job. |
| `TASK` | The user → the manager: new work for the project (`mb pub agent/<manager id> "TASK: ..." --sender user`). |
| `PROPOSAL` / `AGREED` | Negotiating a job's scope and checkpoints; the agreed result. |
| `INFO` | Something you learned that others can use. Post it to everyone immediately. |
| `QUESTION` / `ANSWER` | Quick questions; answer with `--reply-to <seq>`. |
| `READY` | A code engineer's change is written and released; it waits for a build. |
| `BUILD` | Manager → build engineer: build and run, covering these READY items. |
| `REPORT` | Build results: per-item pass/fail, failures with file:line, numbers. |
| `FIX` | Manager → the owning code engineer: a failure to fix, with the excerpt. |
| `STOP` / `REDIRECT` | The manager halts or steers an engineer, with the reason. |
| `BLOCKED` | You cannot proceed; say on what. |
| `DONE` | A code engineer has finished its agreed work. |
| `FINAL` | The manager's evaluation and report for a task. |
