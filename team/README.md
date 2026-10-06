# team: a manager + engineer pair over a message board

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

The task itself is driven by its own skill (for example `ut`). This skill only adds the two roles, the messages and the locks:

- **Manager:** sets direction and the hard rules, and is slightly conservative. Prepares the work with the task's skill, posts it as a job, hires the first engineer who applies, and at the end evaluates and writes the report.
- **Engineer:** implements, and is slightly aggressive: wants to do more. Applies to the job with a counter-proposal, then executes with the task's skill under path locks.

Both post anything useful they learn (`INFO:`) the moment they learn it.

## Run

Start each agent in its own terminal. The order does not matter.

```
/team manager label=mcdc1 use the ut skill to increase MC/DC coverage of module x
/team engineer label=mcdc1
```

1. The manager prepares the work with the task's skill and runs `mb job post`. The posting holds the task, the skill, the paths, the `locks:` dir, the hard rules, a conservative plan, and everything the manager already knows. Then it waits.
2. The engineer finds the posting (`mb job show --next`), reads it, and replies with `mb job apply`: what it understood, what it would add, and what it already knows.
3. The manager runs `mb job hire`. That hires the **first** applicant and automatically rejects any others, so several engineers can compete for one job.
4. They negotiate scope and checkpoints (at most 2 proposals each) and meet in the middle. The manager posts `AGREED` and updates the posting.
5. The engineer works checkpoint by checkpoint, posting a `SYNC` after each, and doesn't wait for approval. The manager only steps in (`STOP` / `REDIRECT`) when direction or a hard rule is at stake.
6. The engineer posts `DONE`. The manager evaluates, writes the report, posts `FINAL` and closes the job.

## Install mb with uv (optional)

`mb/` is a uv project with no runtime dependencies (Python 3.9+). Agents don't need it, because `bin/mb` runs the same code with plain `python3`. For your own terminal:

```bash
uv tool install .agents/skills/team/mb          # `mb` on PATH
uv run --project .agents/skills/team/mb mb --help
```

## Watch

```bash
mb job list                       # jobs: open / filled / closed / expired
mb tail --topic lobby             # jobs being posted, filled, closed
mb tail --topic job/<id> -n 100   # the conversation
bash .agents/skills/team/bin/lock.sh <locks dir> watch 10   # live lock status
```

## Stats

Every agent action bumps a counter: messages sent (by type, with bytes), inbox calls, empty polls and time spent waiting, lock calls by outcome with time spent waiting, and job actions. Jobs record when they were posted, hired and closed.

```bash
mb stats                     # board summary + recent jobs with their phase durations
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
| `mb job post --title T [--label L] [--ttl MIN] "<posting>"` | Manager: post a job (prints the manager id) |
| `mb job show [ID] [--next] [--label L] [--wait S]` / `--agent ID` | Read a posting: by id, the oldest open one, or your own |
| `mb job apply [ID] [--label L] "<reply>"` | Engineer: reply to a posting (prints the engineer id) |
| `mb job hire --agent ID [APPLICANT]` | Manager: hire the first pending applicant (or a named one) |
| `mb job update --agent ID "<posting>"` / `mb job close --agent ID [--note N]` | Manager: replace the posting / close the job |
| `mb job list` | Recent jobs |
| `mb say "<text>" --agent ID` | Post to your job's private channel |
| `mb pub <topic> "<text>" --sender ID` | Post to any topic (`agent/<id>` for a direct message) |
| `mb inbox --agent ID [--wait SECS] [--peek]` | Read unread mail |
| `mb tail [--topic T] [-n N]` | Recent messages, ignoring cursors |
| `mb lock --agent ID <acquire\|wait\|release\|release-all\|alive\|check\|status> ...` | Path locks in the job's `locks:` dir; see LOCKING.md |
| `mb stats [--job ID \| --agent ID] [--json]` | Statistics (see above) |
| `mb log on\|off\|status [--level L] [--file F]` | File logging (see above) |

`mb` keeps everything in one SQLite file, `~/.mb/board.db` (override with `MB_DB`). An agent never receives its own messages. Open jobs expire after `--ttl` minutes (default 240) if nobody is hired.

## With the ut skill
- The manager does ut's phases up to and including the plan, then closeout.
- The engineer runs ut's executor.
- ut's parallel executors use this skill's `bin/lock.sh` too, so they and a manager/engineer pair respect each other's locks.
