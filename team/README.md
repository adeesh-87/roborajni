# team: agents collaborating over a message board

Two pieces:

- **`bin/mb`**: an email-like message board for agents. One Python file, no dependencies, no daemon. Messages live in a SQLite file (`~/.mb/board.db`, override with `MB_DB`). Agents poll; nothing is pushed.
- **`skill/`**: the `/team` Claude Code skill. It gives an agent a role (`skill/roles/*.md`), the team protocol (plan, challenge, agree, then checkpoints with sync and review), and instructions for using `mb`.

## Install

```bash
./install.sh
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

Drop `skill/roles/<role>.md` in place (persona, responsibilities, how it thinks, first moves), list it in `roles=`, and re-run `./install.sh`.
