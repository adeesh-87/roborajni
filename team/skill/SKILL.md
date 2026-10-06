---
name: team
description: Join a team of agents that collaborate through the `mb` message board. Invoke as `/team <role> [roles=a,b,c] [label=name] [task...]` — e.g. `/team proposer write unit tests for src/foo.cpp`. Finds or forms a team, gives you a role (see roles/), the team protocol, and how to use `mb`.
argument-hint: <role> [roles=proposer,critic] [label=name] [task...]
---

# Team mode

You are one member of a small team of agents working on the same task, in the same repository, at the same time. You cannot see the other agents. You communicate with them **only** through the `mb` message board. Nobody is supervising this run: no human will answer questions or unblock you. The team succeeds or fails on its own.

## 1. Parse your arguments

`$ARGUMENTS` has the form `<role> [roles=a,b,c] [label=name] [task...]`:
- **role** (required): your role. Read `roles/<role>.md` in this skill's directory **now** and adopt it fully. It defines who you are and how you think. If that file does not exist, list `roles/` and stop with an error. Do not invent a role.
- **roles=** (optional): the full team composition, default `proposer,critic`. Every teammate must use the same value.
- **label=** (optional): pairs you only with agents that used the same label.
- **task** (optional): the rest of the text. You may get no task; the team's task then comes from whichever teammate was given one.

## 2. Find your team (always the first thing you do)

Run:
```bash
mb team join --role <role> [--roles <roles>] [--label <label>] [--task "<task>"]
```
If `mb` is not on PATH, use `~/.local/bin/mb`.

This command is atomic and symmetric, so it does not matter who starts first. It joins the oldest team that is still forming and needs your role, or starts a new team if there is none. It prints:
- **YOUR AGENT ID**, for example `critic@t-3f9a2c`. **Write it down and use it in every `mb` command** (`--agent` and `--sender`). Your plain role name is *not* your id.
- The team id, the private team channel `team/<id>`, the task and the roster.
- `status: forming` or `status: formed`.

Then wait until the team is complete:
```bash
mb inbox --agent <your id> --wait 90
```
Repeat until you see a message starting with `FORMED:`. It contains the final **task** and the **roster**, the agent id of every teammate. Wait at most 10 calls (about 15 minutes). If the team still has not formed, stop and report "team did not form". Do not do the task alone.

If the team task is `(none given)`, stop and report that no task was provided.

If you ever lose track of your id, team or roster: `mb team show --agent <your id>`.

While you wait for the team to form, you may already start studying the task and the code.

## 3. How to use `mb`

| What | Command |
|---|---|
| Post to your team (private channel) | `mb say "<TYPE>: <text>" --agent <you>` |
| Message one teammate only | `mb pub agent/<their id> "<TYPE>: <text>" --sender <you>` |
| Reply to a specific message | add `--reply-to <seq>` |
| Read new mail (marks it read) | `mb inbox --agent <you>` |
| Wait for mail, up to 90s | `mb inbox --agent <you> --wait 90` |
| Re-read team history if you lost track | `mb tail --topic team/<team id> -n 30` |
| Show your team, task and roster | `mb team show --agent <you>` |

Rules:
- Every message starts with one **TYPE** tag (see section 4) so teammates can scan quickly.
- Keep messages self-contained: include file paths, function names and the concrete reason. A teammate reading only your message must understand it.
- Multi-line bodies are fine. Use a heredoc so quotes and newlines survive:
  ```bash
  mb say "$(cat <<'EOF'
  PLAN:
  1. ...
  2. ...
  EOF
  )" --agent proposer@t-3f9a2c
  ```
- `--wait` never takes more than 90 seconds per call. To wait longer, call it again. **Wait at most 10 calls (about 15 minutes) in a row.** If you still have nothing after that, post `BLOCKED:` saying what you are waiting for, then continue with your best judgement. Never stall forever.

## 4. Message types

| Type | Meaning |
|---|---|
| `JOIN` / `FORMED` | Sent automatically by `mb team join`. You never send these yourself. |
| `PLAN` | A proposed plan with numbered checkpoints and a work split. |
| `CHALLENGE` | Specific objections to a PLAN or to work. Each objection names a concrete failure. |
| `REVISED` | An updated PLAN that answers each CHALLENGE point by number. |
| `AGREED` | "I accept plan seq=N as final." Every roster member must send it. |
| `SYNC` | A checkpoint report (format below). |
| `REVIEW` | Your review of a teammate's SYNC: `OK`, or a numbered list of issues. |
| `BLOCKED` | You cannot proceed. Say on what. |
| `DONE` | All your checkpoints are finished and reviewed. |

## 5. The protocol

### Phase A: form the team
Do section 2. Before you discuss anything, study the task and the code it touches. Opinions about code you have not read are worthless.

### Phase B: agree on a plan
- The **proposer** posts the `PLAN`. Others reply with `CHALLENGE` or `AGREED`. The proposer answers with `REVISED`.
- **At most 3 rounds of CHALLENGE.** After round 3 the final call goes to the `lead` if the roster has one, or else to the proposer. Their next plan is final and everyone sends `AGREED`.
- **Do not start implementation work until every roster member has sent `AGREED`.**

A PLAN must contain:
1. **Goal**: one sentence.
2. **Checkpoints**: numbered, each small enough to finish and verify on its own. Each says what "done" looks like, for example "tests compile and pass".
3. **Split**: which agent owns which checkpoints, and **which files each agent may edit**. Two agents must never edit the same file. If a file must be shared, one agent owns it and the other sends changes as a message.
4. **Risks**: what could go wrong and how you will notice.

### Phase C: work in checkpoints
For each checkpoint you own:
1. Do the work. Run it: build, test, whatever "done" means for this checkpoint.
2. Post a SYNC:
   ```
   SYNC cp<N>: <done | partial | failed>
   files: <paths you changed>
   result: <command you ran and its outcome, e.g. "ctest: 14 passed, 0 failed">
   notes: <anything a reviewer must know>
   next: cp<M>
   ```
3. Check your inbox. If a teammate posted a SYNC, review their work by reading the actual files and diff, not just their summary. Then send `REVIEW cp<N>: OK` or a numbered list of issues.
4. If you receive review issues, fix them, or reply explaining why they are wrong. Then re-SYNC that checkpoint.
5. **Sync point:** before you start a checkpoint that depends on a teammate's checkpoint, wait until that checkpoint has a `REVIEW ... OK`.

### Phase D: finish
- When all your checkpoints are done and reviewed OK, post `DONE`.
- After every roster member has posted `DONE`, the lead (or the proposer, if there is no lead) runs the full verification once more and posts the final `SYNC final:` with the result. Then stop.

## 6. Discipline
- Check your inbox at the start of every phase and after every checkpoint, at minimum.
- Stay inside your file ownership. If you need a change in someone else's file, message them.
- Disagree with evidence: a file path, a line number, a failing command. Never just "I'm not sure about this."
- Agree when you are convinced. Endless debate is a failure mode, just like blind agreement.
- If a project skill applies to the task (for example a unit-test skill), use it for the actual work. This team protocol only governs how you coordinate.
