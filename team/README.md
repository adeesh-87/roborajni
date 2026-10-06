# team: agents collaborating over a message board

This folder is a self-contained skill. Copy the whole `team/` folder into your skills directory, for example `.agents/skills/team/` (or `.claude/skills/team/` for Claude Code).

```
team/
├── SKILL.md        # entry point: rendezvous, mb how-to, team protocol
├── roles/          # one file per role: proposer, critic, lead
├── bin/mb          # the message board CLI (Python 3, no dependencies)
├── install.sh      # optional: symlink mb onto PATH
└── README.md
```

- **`bin/mb`**: an email-like message board for agents. No daemon. Messages live in one SQLite file (`~/.mb/board.db`, override with `MB_DB`). Agents poll; nothing is pushed. An agent never receives its own messages.
- **`SKILL.md` + `roles/`**: gives an agent a role and the team protocol: plan, challenge, agree, then checkpoints with sync and review.

## Install

Copy the folder. That's it: agents fall back to `python3 <skill>/bin/mb` when `mb` isn't on PATH. To get a plain `mb` command (handy for watching runs yourself):

```bash
bash .agents/skills/team/install.sh
```

## Run a team

Start each agent in its own terminal. The order does not matter.

```
/team proposer write unit tests for src/foo.cpp using the /ut skill
/team critic
```

`mb team join` pairs them automatically: each agent joins the oldest forming team that still needs its role, or starts a new one. Each agent gets a unique id such as `critic@t-3f9a2c` and a private channel `team/t-3f9a2c`. When every role is filled, `mb` posts `FORMED` with the task and the roster.

- Three-member team: add `roles=proposer,critic,lead` to every agent's command.
- Pair specific agents when several teams start at once: add the same `label=<name>` to each of them.
- Teams that are still forming after 30 minutes are abandoned, so a dead run cannot capture the next run's agents.

## Watch

```bash
mb team list                      # teams and their members
mb tail --topic lobby             # teams opening, forming, being abandoned
mb tail --topic team/<id> -n 100  # the team's conversation
```

## `mb` commands

| Command | Purpose |
|---|---|
| `mb team join --role R [--roles a,b] [--label L] [--task T]` | Find or start a team and get your agent id |
| `mb team show --agent ID` / `mb team list` | Show your team / all recent teams |
| `mb say "<text>" --agent ID` | Post to your team's private channel |
| `mb pub <topic> "<text>" --sender ID` | Post to any topic (`agent/<id>` for a direct message, `all` to broadcast) |
| `mb inbox --agent ID [--wait SECS] [--peek]` | Read unread mail: your direct messages, `all`, and subscribed topics |
| `mb sub <topic> --agent ID` / `mb ack ID SEQ` | Subscribe to a topic / move your read cursor |
| `mb tail [--topic T] [-n N]` | Recent messages, ignoring cursors |

## Adding a role

Add `roles/<role>.md` (persona, responsibilities, how it thinks, first moves) and list it in `roles=`.
