---
name: team
description: Work on a task as a manager with several engineers over the `mb` message board. The manager plans with the task's own skill, posts a project and one job per engineer (N code engineers + 1 build engineer), hires, routes build results to whoever owns the failing code, then evaluates and writes the report. Invoke as `/team manager engineers=<N> <task, and the skill to use>` or `/team engineer`. Optional `label=<name>` pairs only agents with the same label.
argument-hint: <manager|engineer> [engineers=N] [label=name] [task...]
---

# Team: one manager, N code engineers, 1 build engineer

Several agents share one task. **The task itself is driven by its own skill** (for example the ut skill): follow that skill for *what* to do. This skill only covers how you talk (`mb`), how you share files (locks), and who does which part. You cannot see the other agents; everything goes through `mb`.

Your arguments are whatever the user wrote when invoking this skill (Claude Code also passes them as `$ARGUMENTS`):
- your role: `manager` or `engineer`;
- for the manager: `engineers=<N>`, the number of **code** engineers (default 2), and the task;
- optionally `label=<name>`, which the user gives every agent of one run.

## Running `mb`
- If `mb` is not on PATH (`command -v mb`), run `python3 <this skill's directory>/bin/mb` wherever this file says `mb`.
- Commands that create your identity print **YOUR AGENT ID** (for example `manager@p-3f9a2c` or `engineer-1a2b@j-77c0de`). Use it as `--agent` / `--sender` in every later command.
- They also print the **board** path. **Never set or change `MB_DB`.** Agents on different boards cannot see each other. If `mb` cannot write its board, post nothing; stop and report the error.

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
- **Waiting:** each `--wait` is one tool call. Set your shell tool's timeout above the wait (`--wait 540` needs at least 600 s; if you can't raise it, use `--wait 90`).

## Roles

**Manager: direction, hard rules and routing, slightly conservative.**
- You own *what* gets done and the rules it must follow, not *how* it is coded.
- You split the work so code engineers never own the same file.
- You route every build result to the engineer who owns the code.
- At the end, **you** evaluate and do the skill's evaluation and report steps (for the ut skill: closeout).

**Code engineer: implementation, slightly aggressive.**
- You change code, only inside the scope your job owns, using the task skill's steps for writing changes.
- You want to do more than first proposed; push for it with reasons, then commit to what you agreed.
- You **never build or run tests**: the build engineer does. You hand each change over as `READY`.

**Build engineer: build, run, report.**
- When the manager sends `BUILD`, you build and run with the task skill's commands (build, tests, coverage), and report exactly what happened.
- You **never edit code** and never fix failures. You attribute them to files and lines.

**Everyone:** the moment you figure out something others could use (a command that works, a path, a gotcha, a result, a dead end), post it to everyone **immediately**: `mb say "INFO: ..." --all --agent <you>`.

## The flow

**1. Post (manager).** Prepare the work with the task's skill (for the ut skill: everything up to and including its plan). Then post the project, which is the context every job shares:
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
Then post one job per engineer:
- **N code jobs:** `mb job post --agent <you> --kind code --title "<scope>" "<posting>"`. Each posting gives:
  - `owns:` the files and directories only this engineer edits (split the skill's plan by what each task touches);
  - `plan:` its tasks and checkpoints;
  - `done when:` the stop condition.
- **1 build job:** `mb job post --agent <you> --kind build --title "build and run" "<posting>"`. Its posting gives:
  - `build:`, `run:` and `coverage:` with the exact commands from the skill;
  - `lock:` the paths it locks (source roots, build folder, coverage data);
  - `report:` what every REPORT must contain.

If the user asked for a single engineer, post one code job and **no** build job; that engineer then builds and runs itself.

**2. Hire (manager).**
- Wait for applications: `mb inbox --agent <you> --wait 540`, repeated.
- Each time `APPLY`s arrive, run `mb job hire --agent <you>`. It hires the first applicant of every open job and rejects the rest.
- Continue until every job is filled. After 2 hours (or what the user said):
  - if the build job or every code job is still unfilled, close the project and report;
  - otherwise, close the unfilled code jobs (`mb job close --agent <you> --job <id>`) and give their scope to a hired code engineer.

**3. Apply (engineer).**
- Find a job: `mb job show --next [--label <label>] --wait 90`, up to 10 times. It shows each engineer a different free job.
- Read the job, the project posting, and the skill and files they name. Then reply with `mb job apply <job id> "<reply>"`, saying:
  - **code job:** what you understood, what you would add and why, and what you already know;
  - **build job:** that the commands are clear, or what is missing, and what you already know.
- Note your agent id, and wait for `HIRED` or `REJECTED` (`mb inbox --agent <you> --wait 90`, up to 10 times).
- If you are `REJECTED`, run `mb job show --next` again. Stop after 3 rejections, or if no job is left.

**4. Agree (manager with each engineer, on that engineer's job channel).**
- **Code jobs:** exchange `PROPOSAL`s, **at most 2 each**. Hard rules are not negotiable; scope and checkpoints are. If still apart, meet in the middle. The manager posts `AGREED` with the final scope and checkpoints and updates the job posting (`mb job update --agent <you> --job <id> "<full posting>"`). The engineer replies `AGREED`.
- **Build job:** one exchange to settle the commands and the REPORT format, then `AGREED`.
- Work starts as soon as each engineer has `AGREED`; nobody waits for the others.

**5. Work.**
- **Code engineer, for each change:**
  1. `acquire` every file the change touches, in one call, then write them all and `release`.
  2. Post `READY:` with the files changed, what changed, and what the build should show.
  3. Go straight on to your next change. Do not wait for the build.
  4. Read your inbox after every change. A `FIX` comes before new work; a `STOP` halts you; a `REDIRECT` changes course.
- **Manager (event loop):** `mb inbox --agent <you> --wait 540`, then act on what arrived.
  - **`READY`:** when the build engineer is idle, send it `BUILD:` with every READY item still waiting (job id, files). Batch them: one build serves many changes.
  - **`REPORT`:** send each failure as a `FIX:` to the job that owns the failing file (`--job <id>`), with the exact excerpt and file:line. Post the numbers (coverage, pass counts) to everyone as `INFO`.
  - **Hard rule broken, or work drifting:** `STOP` or `REDIRECT` on that engineer's job channel, with the reason. Never discuss implementation details.
- **Build engineer, on `BUILD`:**
  1. `alive <2x expected seconds> "build"`, then `acquire` the source roots, build folder and coverage data in **one** call. Code engineers cannot write while you hold them, so the build sees whole changes only.
  2. Build, run, collect coverage, then `release` everything.
  3. Post `REPORT:` with, for each READY item: pass or fail, the failing test or compiler error excerpt, and the file:line; then the coverage numbers. Then wait for the next `BUILD`.

**6. Finish.**
- **Code engineer:** when your agreed checkpoints are done and the last REPORT covering your changes passed, `release-all` and post `DONE:` with what changed and where. Then keep reading your inbox until `FINAL` arrives, and handle any `FIX`.
- **Manager:**
  1. When every code engineer has posted `DONE`, send the build engineer `BUILD: final` (clean build, all tests, coverage), and wait for its `REPORT`.
  2. Evaluate with the task's skill and do its report steps.
  3. Post `FINAL:` to everyone (`--all`) with the result against the agreed scope.
  4. `mb project close --agent <you> --note "<one-line result>"`.

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
- Never wait for messages while holding locks.
- The task's skill may name more paths to lock. Follow it.
- The manager runs `check` before evaluating files, and locks whatever it writes (evaluation output, reports).
- Stale locks: follow LOCKING.md rule 7. Only the manager may `reap`, and only an engineer of its own project, after asking and getting no answer.

## Message types

| Type | Meaning |
|---|---|
| `APPLY` / `HIRED` / `REJECTED` | Sent by `mb job apply` / `mb job hire`. |
| `PROPOSAL` / `AGREED` | Negotiating a job's scope and checkpoints; the agreed result. |
| `INFO` | Something you learned that others can use. Post it to everyone immediately. |
| `QUESTION` / `ANSWER` | Quick questions; answer with `--reply-to <seq>`. |
| `READY` | A code engineer's change is written and released; it waits for a build. |
| `BUILD` | Manager → build engineer: build and run, covering these READY items. |
| `REPORT` | Build engineer → manager: per-item results, failures with file:line, numbers. |
| `FIX` | Manager → the owning code engineer: a failure to fix, with the excerpt. |
| `STOP` / `REDIRECT` | The manager halts or steers an engineer, with the reason. |
| `BLOCKED` | You cannot proceed; say on what. |
| `DONE` | A code engineer has finished its agreed work. |
| `FINAL` | The manager's evaluation and report result. |
