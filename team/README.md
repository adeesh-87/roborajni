# team: a manager with N code engineers and a build engineer, over a message board

This folder is a self-contained skill. Copy the whole `team/` folder into your skills directory next to the task skills it works with, for example `.agents/skills/team/` beside `.agents/skills/ut/` (or under `.claude/skills/` for Claude Code).

```
team/
├── SKILL.md        # roles, the flow, mb and lock usage
├── LOCKING.md      # path locks for shared resources: commands and rules
├── bin/mb          # launcher: runs mb from this folder with plain python3 (no uv needed)
├── bin/lock.sh     # launcher: path locks with heartbeats and stale detection (bash)
├── mb/             # the mb uv project: pyproject.toml, uv.lock, src/mb/{cli.py,lock.sh}
├── install.sh      # optional: symlink mb onto PATH
└── README.md
```

The task itself is driven by its own skill (for example `ut`). This skill only adds the roles, the messages and the locks:

- **Manager:** sets direction and the hard rules, and is slightly conservative. Prepares the work with the task's skill, posts a **project** (the shared context) and **one job per engineer**, hires, routes every build result to the engineer who owns the code, and at the end evaluates and writes the report.
- **N code engineers:** each owns a disjoint part of the code, is slightly aggressive (wants to do more), and hands every change over as `READY`. They never build.
- **1 build engineer:** builds and runs when the manager asks (`BUILD`) and posts a `REPORT`. It never edits code.

Everyone posts anything useful they learn to the whole project (`INFO`) the moment they learn it.

## Run

Start every agent in its own terminal, in any order. Use one label per run.

```
/team manager engineers=2 label=mcdc3 use the ut skill to increase MC/DC coverage of module x
/team engineer label=mcdc3      # three times: 2 code engineers + 1 build engineer
```

1. The manager prepares the work, then runs `mb project post`. The posting holds the task, the skill, the paths, the `locks:` dir, the hard rules and what the manager already knows. It then posts N code jobs, each owning disjoint files, and 1 build job holding the exact build, run and coverage commands.
2. Engineers are launched identically. `mb job show --next` shows each one a different free job; they read it and `mb job apply`. `mb job hire` hires the first applicant of every job, and rejected engineers look for the next free job.
3. The manager agrees scope and checkpoints with each code engineer (at most 2 proposals each, meeting in the middle) and the commands with the build engineer.
4. The routing loop:
   - A code engineer writes a change under lock and posts `READY`. It carries on with its next change.
   - The manager batches READYs into a `BUILD` for the build engineer.
   - The build engineer locks the sources and build folder, builds, runs and posts a `REPORT`.
   - The manager sends each failure as a `FIX` to the engineer who owns the file, and the numbers to everyone as `INFO`.
5. When every code engineer is `DONE`, the manager asks for a final build, evaluates, writes the report, posts `FINAL` and closes the project.

For a single engineer that builds itself: `engineers=1`, and launch one engineer. The manager posts no build job.

## Where the board lives

Every agent of a run must use the **same** board (one SQLite file). `mb` picks it in this order:

1. `MB_DB`, if it is set in the environment the session was launched with (`MB_DB=/path/board.db codex`);
2. `board` in `~/.config/mb/config.json`, set once with `mb config set board <file or directory>`;
3. `~/.mb/board.db`.

```bash
mb config show                          # the board in effect, where it came from, and whether its folder is writable
mb config set board ~/boards/           # every later mb call, in every session, uses ~/boards/board.db
mb config unset board
```

Configure the board yourself, before launching the agents. Don't ask an agent to set `MB_DB`: each shell call is separate, and one call that misses it lands on a different board. The skill tells agents never to change it.

- **Sandboxes:** SQLite must be able to create files in the board's folder. Under Codex's workspace-write sandbox, `~/.mb` is not writable. Either give the session write access to the board's folder or full access, or choose a board inside a folder the session may write to.
- **WSL:** keep the board on the Linux side (`~/...`). SQLite's locking is unreliable on Windows drives (`/mnt/c/...`), and `mb config set` warns if you pick one.

If `mb` cannot open the board, its error names the path, where the setting came from, and the usual causes.

## Install mb with uv (optional)

`mb/` is a uv project with no runtime dependencies (Python 3.9+). Agents don't need it, because `bin/mb` runs the same code with plain `python3`. For your own terminal:

```bash
uv tool install .agents/skills/team/mb          # `mb` on PATH
uv run --project .agents/skills/team/mb mb --help
```

## Watch

```bash
mb project show <id>              # the project, its jobs and who holds them
mb job list                       # jobs: open / filled / closed / expired
mb tail --topic lobby             # jobs being posted, filled, closed
mb tail --topic job/<id> -n 100   # the conversation
bash .agents/skills/team/bin/lock.sh <locks dir> watch 10   # live lock status
```

## Stats

Every agent action bumps a counter: messages sent (by type, with bytes), inbox calls, empty polls and time spent waiting, lock calls by outcome with time spent waiting, and job actions. Jobs record when they were posted, hired and closed.

```bash
mb stats                     # board summary + recent projects
mb stats --project <id>      # staffing, time to first build and to final, READY/BUILD/REPORT/FIX counts, per-agent costs
mb stats --job <id>          # timeline, message mix, per-agent costs
mb stats --agent <id>        # one agent's summary and raw counters
mb stats --job <id> --json   # the same as JSON, for scripts and comparisons between runs
```

`mb stats --job` splits the run into phases: **waiting for engineer** (posted → hired), **negotiation** (hired → first `AGREED`), **work** (`AGREED` → `DONE`) and **evaluation** (`DONE` → `FINAL`/closed). It also counts SYNCs and STOP/REDIRECTs, and for each agent shows how much of its inbox polling came back empty.

## Logging

Off by default. The setting lives in the board's database, so it switches on or off for every agent at once:

```bash
mb log on [--level error|warn|info|debug] [--file PATH]   # default: info, ~/.mb/mb.log
mb log off
mb log status
```

| Level | Logs |
|---|---|
| `error` | failed `mb` commands (with their arguments) |
| `warn` | + busy or stale locks, expired jobs, rejected applicants |
| `info` | + every message sent (seq, topic, type, size), job events, lock actions |
| `debug` | + full message bodies and postings, every inbox poll, every message read, lock checks |

Each line has a timestamp, the level, `event=...`, `agent=...` and key=value fields. A logging failure never breaks an `mb` command.

## `mb` commands

| Command | Purpose |
|---|---|
| `mb project post --title T [--label L] "<posting>"` | Manager: post the project, the shared context (prints the manager id) |
| `mb project show [ID] [--agent ID]` / `mb project close --agent ID [--note N]` | Show a project and its jobs / close it with all its jobs |
| `mb job post --agent ID --kind code\|build --title T [--ttl MIN] "<posting>"` | Manager: post one job (one engineer) in the project |
| `mb job show [ID] [--next] [--label L] [--kind K] [--wait S]` / `--agent ID` | Read a posting: by id, the next free one, or your own |
| `mb job apply ID "<reply>"` | Engineer: reply to a posting (prints the engineer id) |
| `mb job hire --agent ID [--job J] [APPLICANT]` | Manager: hire the first applicant of every open job (or of one job, or a named applicant) |
| `mb job update --agent ID [--job J] "<posting>"` / `mb job close --agent ID [--job J] [--note N]` | Manager: replace a job's posting / close one job |
| `mb job list` | Recent jobs |
| `mb say "<text>" --agent ID [--job J \| --all]` | Post to your job channel, to one job (manager), or to the whole project |
| `mb pub <topic> "<text>" --sender ID` | Post to any topic (`agent/<id>` for a direct message) |
| `mb inbox --agent ID [--wait SECS] [--peek]` | Read unread mail |
| `mb tail [--topic T] [-n N]` | Recent messages, ignoring cursors |
| `mb lock --agent ID <acquire\|wait\|release\|release-all\|alive\|check\|status> ...` | Path locks in the job's `locks:` dir; see LOCKING.md |
| `mb stats [--project ID \| --job ID \| --agent ID] [--json]` | Statistics (see above) |
| `mb log on\|off\|status [--level L] [--file F]` | File logging (see above) |
| `mb config show` / `set board <path>` / `unset board` | Where the board lives (see above) |

`mb` keeps everything in one SQLite file (see "Where the board lives"). An agent never receives its own messages. Open jobs expire after `--ttl` minutes (default 240) if nobody is hired.

## With the ut skill
- The manager does ut's phases up to and including the plan, splits the plan's tasks across the code jobs by what they touch, and does closeout at the end.
- Code engineers write the tests with ut's executor steps but hand every build and run to the build engineer.
- The build engineer runs the build, test and coverage commands recorded in ut's KB.
- ut's parallel executors use this skill's `bin/lock.sh` too, so they and a manager/engineer pair respect each other's locks.
