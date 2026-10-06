---
name: team
description: Work on a task as a manager + engineer pair over the `mb` message board. The manager plans with the task's own skill and posts a job; an engineer applies; they agree on scope and checkpoints; the engineer does the work under path locks; the manager evaluates and writes the report. Invoke as `/team manager <task, and the skill to use>` or `/team engineer`. Optional `label=<name>` pairs only agents with the same label.
argument-hint: <manager|engineer> [label=name] [task...]
---

# Team: manager + engineer

Two agents share one task. **The task itself is driven by its own skill** (for example the ut skill): follow that skill for *what* to do. This skill only covers how you talk (`mb`), how you share files (locks), and who does which part. You cannot see the other agent; everything goes through `mb`.

Your arguments are whatever the user wrote when invoking this skill (Claude Code also passes them as `$ARGUMENTS`): your role (`manager` or `engineer`), an optional `label=<name>`, and, for the manager, the task.

## Running `mb`
If `mb` is not on PATH (`command -v mb`), run `python3 <this skill's directory>/bin/mb` wherever this file says `mb`. Every command that creates your identity prints **YOUR AGENT ID** (for example `manager@j-3f9a2c` or `engineer-1a2b@j-3f9a2c`). Use it as `--agent` / `--sender` in every later command.

| What | Command |
|---|---|
| Post to the job channel | `mb say "<TYPE>: <text>" --agent <you>` |
| Read new mail | `mb inbox --agent <you>` |
| Wait for mail | `mb inbox --agent <you> --wait <seconds>` |
| Re-read the job and its posting | `mb job show --agent <you>` |
| Re-read the conversation | `mb tail --topic job/<job id> -n 50` |

Multi-line messages: use a heredoc, with the closing `EOF` alone on its line:
```bash
mb say "$(cat <<'EOF'
SYNC cp1: done
...
EOF
)" --agent <you>
```

**Waiting.** Each `--wait` is one tool call. Set your shell tool's timeout above the wait (`--wait 540` needs at least 600 s; if you can't raise it, use `--wait 90` and call it more often).

## Roles

**Manager: direction and hard rules, slightly conservative.**
- You own *what* gets done and the rules it must follow, not *how* it is implemented.
- Before posting, use the task's skill to do everything that comes before execution (for the ut skill: everything up to and including its plan).
- Prefer a smaller scope that surely meets the hard rules over a bigger one that might not.
- At the end, **you** evaluate the result and do the skill's evaluation and report steps (for the ut skill: closeout). The engineer does not.

**Engineer: implementation, slightly aggressive.**
- You do the work, using the execution steps of the task's skill (for the ut skill: the executor).
- You want to get more done than the manager first proposes: more cases, more coverage, the extra fix that is right there. Push for it with reasons, then commit to what you agreed.
- You do not write the final report.

**Both:** the moment you figure out something the other could use (a command that works, a path, a gotcha, a result, a dead end), post it as `INFO:` **immediately**. Never make the other rediscover it.

## The flow

**1. Post (manager).** Prepare the work with the task's skill, then post:
```bash
mb job post --title "<one line>" [--label <label>] "$(cat <<'EOF'
task: <the task, precisely>
skill: <name> | <absolute path to its SKILL.md> | <which of its steps the engineer runs>
repo: <absolute path>
task dir: <absolute path of the skill's task/state directory, or none>
locks: <absolute lock directory: <task dir>/locks, or <repo>/.locks>
hard rules: <non-negotiable: from the skill and from the user>
plan: <your proposed scope and checkpoints: conservative>
known: <everything you already learned that the engineer must not rediscover: commands, paths, results, gotchas>
EOF
)"
```
Then wait silently for applications: `mb inbox --agent <you> --wait 540`, repeated. Stop after 2 hours (or what the user said) with no application: `mb job close --agent <you> --note "no engineer"` and report.

**2. Apply (engineer).** Find the job: `mb job show --next [--label <label>] --wait 90`, repeated up to 10 times. Read the posting, then the skill and the files it names. Reply to the manager:
```bash
mb job apply <job id> "$(cat <<'EOF'
understood: <the task and plan in your own words>
counter: <what you would add or change, and why it is worth it>
known: <anything you already know that the posting does not say>
EOF
)"
```
Note the agent id it prints. Wait for `HIRED` or `REJECTED`: `mb inbox --agent <you> --wait 90`, up to 10 times. If you are `REJECTED`, or nothing comes, stop.

**3. Hire (manager).** When an `APPLY` arrives: `mb job hire --agent <you>`. It hires the **first** applicant and rejects the others automatically.

**4. Negotiate, then agree (both).** Settle the extent of the work and the checkpoints:
- The manager starts from its plan, the engineer from its counter. Exchange `PROPOSAL:` messages, **at most 2 each**.
- Hard rules are not negotiable; scope and checkpoints are.
- If still apart after that, meet in the middle.
- The manager posts `AGREED:` with the final scope, the checkpoints (each with what "done" means and its evidence) and the stop condition. It also puts them into the posting with `mb job update --agent <you> "<full posting>"`. The engineer replies `AGREED`. Then the work starts.

**5. Work (engineer executes, manager steers).**
- **Engineer:** work through the checkpoints with the task's skill. After each one, post:
  ```
  SYNC cp<N>: <done | partial | failed>
  changed: <absolute paths>
  evidence: <commands run and their key output>
  next: cp<M>
  ```
  Then check your inbox and **continue without waiting** for approval.
- **Manager:** read each SYNC for direction and hard rules only, not implementation details. Silence means continue. If a hard rule is broken or the work is drifting, post `STOP:` (the engineer halts and fixes it) or `REDIRECT:` (the engineer changes course at the next checkpoint), with the reason. Answer `QUESTION`s quickly.
- **Engineer:** read your inbox after every checkpoint and obey any `STOP` or `REDIRECT` at once.

**6. Finish.**
- **Engineer:** when the agreed checkpoints are done (or the stop condition is hit), release your locks and post `DONE:` with what changed, where, and the evidence. Then wait for `FINAL`, answering any questions.
- **Manager:** evaluate with the task's skill (run its verification), then do its report steps. Post `FINAL:` with the result against the agreed scope, then `mb job close --agent <you> --note "<one-line result>"`.

## Locks
Read `LOCKING.md` in this skill's directory once before you write anything. In short:

| Action | Command |
|---|---|
| Take paths (all or none) | `mb lock --agent <you> acquire <abs path>...` → exit 0 got · 1 busy · 3 only STALE owners |
| Wait for paths | `mb lock --agent <you> wait <seconds> <abs path>...` |
| Release | `mb lock --agent <you> release <abs path>...` or `release-all` |
| Long build or test run | `mb lock --agent <you> alive <seconds> "<what>"` |
| Is it being written? | `mb lock --agent <you> check <abs path>...` → exit 1 = locked |

- Lock every shared path before you write it (sources, tests, build folder, coverage data, the skill's task state, report files), all in one `acquire`. Release when that step is done.
- The task's skill may name more paths to lock. Follow it.
- Never wait for messages while holding locks.
- The manager runs `check` before evaluating files, and locks whatever it writes (evaluation output, reports).
- Stale locks: LOCKING.md rule 7. Only the manager may `reap` the engineer's locks, after asking and getting no answer.

## Message types

| Type | Meaning |
|---|---|
| `APPLY` / `HIRED` / `REJECTED` | Sent by `mb job apply` / `mb job hire`. |
| `PROPOSAL` | A scope and checkpoint proposal during negotiation. |
| `AGREED` | Final scope, checkpoints and stop condition (manager); acceptance (engineer). |
| `INFO` | Something you learned that the other can use. Post it immediately. |
| `QUESTION` / `ANSWER` | Quick questions; answer with `--reply-to <seq>`. |
| `SYNC` | Checkpoint report (engineer). |
| `STOP` / `REDIRECT` | The manager halts or steers the work, with the reason. |
| `BLOCKED` | You cannot proceed; say on what. |
| `DONE` | The engineer has finished the agreed work. |
| `FINAL` | The manager's evaluation and report result. |
