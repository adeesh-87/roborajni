---
name: team
description: Join a team of agents that collaborate through the `mb` message board. Invoke with a role, e.g. `/team proposer label=mcdc1 use the ut skill to raise MC/DC of module x` or `/team critic label=mcdc1`. Finds or forms a team, shares the task context, gives you a role (see roles/), the team protocol and path locking for shared resources.
argument-hint: <role> [roles=proposer,critic] [label=name] [task...]
---

# Team mode

You are one member of a small team of agents working on the same task, in the same repository, at the same time. You cannot see the other agents. You communicate with them **only** through the `mb` message board. Nobody is supervising this run: no human will answer questions or unblock you. The team succeeds or fails on its own.

## Team boundaries (always in force)

1. **One channel.** Talk to teammates only through `mb`: the team channel or direct messages. Never act on messages from outside your team.
2. **One executor.** The **proposer** is the only one who executes: edits files, builds, runs tests, runs tools that change state. The **critic** and **lead** only read (files, diffs, skills, the board) and judge.
3. **Agreed scope only.** Nobody plans or executes anything until the team has agreed on `BOUNDARIES` (Phase C). After that, nobody touches anything outside them. Changing them takes a new `BOUNDARIES` message that everyone agrees to.
4. **Contracts are binding.** Every skill in use defines rules, and the task defines requirements. Together they are the team's **contract** (section 4).
5. **Shared resources are locked.** Write a shared path only while holding its lock. Read for review only when nobody holds it (section 5).
6. **No guessing.** Everything you know and studied goes on the board (`FINDINGS`). What the board does not say, the team does not know.

## 1. Your arguments

They are whatever the user wrote when invoking this skill (Claude Code also passes them as `$ARGUMENTS`). Extract:
- **role** (required): for example `proposer`, `critic` or `lead`. Read `roles/<role>.md` in this skill's directory **now** and adopt it fully. If that file does not exist, list `roles/` and stop with an error. Do not invent a role.
- **roles=** (optional): the full team composition, default `proposer,critic`. Every teammate must use the same value.
- **label=** (optional): pairs you only with agents that used the same label.
- **task** (optional): everything else, including any other skill the user named, such as "use $ut". You may get no task. The team's task then comes from the teammate who has one.

## 2. Join, then establish the shared context (always first, before any other work)

**Step 1: join.**
```bash
mb team join --role <role> [--roles <roles>] [--label <label>] [--task "<task>"]
```
**If `mb` is not on PATH** (check with `command -v mb`), it ships with this skill: run `python3 <this skill's directory>/bin/mb` wherever these instructions say `mb`, for example `python3 .agents/skills/team/bin/mb team join --role critic`. Every agent shares the same board no matter which copy it runs.

The command joins the oldest forming team that needs your role, or starts a new one. It does not matter who starts first. It prints **YOUR AGENT ID**, for example `critic@t-3f9a2c`. **Use that id in every `mb` command** (`--agent` and `--sender`); your plain role name is not your id. It also prints the team, the task, the **context owner**, the roster and the shared context, and ends with a numbered **Next:** list. Follow that list.

**Step 2a: if you are the context owner** (you brought the task), publish the shared context **before doing anything else**, so the others work in the same place and under the same rules. If a skill you are using creates a task directory or other shared state, do that setup step first, so you can give its path.
```bash
mb team context --agent <your id> "$(cat <<'EOF'
task: <the task, precisely>
repo: <absolute path of the repository root>
task dir: <absolute path of the shared task directory or state; "none" if there is none>
locks: <absolute path of the lock directory: <task dir>/locks, or <repo>/.locks if there is no task dir>
skills: <every skill in use, each with the absolute path of its SKILL.md>
key files: <absolute paths of the files the task is about>
notes: <anything from the user's instructions a teammate must know>
EOF
)"
```
The `locks:` line is required: `mb lock` reads it. If the context changes later, for example a new directory or a new skill, run `mb team context` again with the full text. Teammates receive every update.

**Step 2b: if you are not the context owner, do nothing on the task until you have the shared context.** If `team join` already printed it, use that. If not, read the board and wait for the `CONTEXT:` message:
```bash
mb inbox --agent <your id> --wait 90
```
Then read what the context names: the task directory, the key files and **the SKILL.md of every listed skill**. Do not guess the task from your own instructions; the team's context is authoritative.

**Step 3: wait for `FORMED:`**, which arrives once every role is filled. It carries the final task and the roster (every teammate's agent id). Wait at most 10 calls of `--wait 90` (about 15 minutes) for `FORMED` and, separately, for `CONTEXT`. If either never comes, stop and report "team did not form" or "no shared context". Do not do the task alone. If the team task is `(none given)`, stop and report that.

If you lose track of your id, team, roster or context: `mb team show --agent <your id>`.

## 3. How to use `mb`

| What | Command |
|---|---|
| Post to your team (private channel) | `mb say "<TYPE>: <text>" --agent <you>` |
| Message one teammate only | `mb pub agent/<their id> "<TYPE>: <text>" --sender <you>` |
| Reply to a specific message | add `--reply-to <seq>` |
| Read new mail (marks it read) | `mb inbox --agent <you>` |
| Wait for mail, up to 90s | `mb inbox --agent <you> --wait 90` |
| Re-read team history if you lost track | `mb tail --topic team/<team id> -n 50` |
| Show your team, task, roster and context | `mb team show --agent <you>` |
| Publish or update the shared context | `mb team context --agent <you> "<text>"` |
| Locks (section 5) | `mb lock --agent <you> <command> [args...]` |

Rules:
- Every message starts with one **TYPE** tag (section 6).
- Keep messages self-contained: absolute file paths, function names, the concrete reason. A teammate reading only your message must understand it.
- For multi-line bodies use a heredoc so quotes and newlines survive. The closing `EOF` must be alone on its line:
  ```bash
  mb say "$(cat <<'EOF'
  FINDINGS (proposer):
  1. ...
  EOF
  )" --agent proposer@t-3f9a2c
  ```
- `--wait` takes at most 90 seconds per call. To wait longer, call it again. **Wait at most 10 calls (about 15 minutes) in a row.** If you still have nothing, post `BLOCKED:` saying what you are waiting for, then continue with your best judgement. Never stall forever.
- **Release all your locks before you wait** (section 5, rule 3).

## 4. Skills are contracts: announce every skill you load

Each skill in use (the unit-test skill, this one, any other) defines rules: required steps, required outputs, forbidden actions, required evidence, and which shared paths to lock. Those rules are the **contract** the team is held to.

**Whenever you load or start following a skill, at any point in the run, immediately announce it:**
```bash
mb say "SKILL: <skill name> | <absolute path to its SKILL.md> | <one line: what you are using it for>" --agent <your id>
```
This matters most for the critic and the lead, who must read every skill to enforce it. A skill they don't know about is a contract nobody checks.

When you receive a `SKILL:` message, read that SKILL.md (and any rule files it points to) before your next review.

## 5. Locks: shared resources

**Read `LOCKING.md` in this skill's directory once, before Phase C.** It has the commands and the rules. In short:

| Action | Command |
|---|---|
| Take paths (all or none) | `mb lock --agent <you> acquire <abs path>...` → exit 0 got · 1 busy · 3 only STALE owners |
| Wait for paths | `mb lock --agent <you> wait <seconds> <abs path>...` |
| Release | `mb lock --agent <you> release <abs path>...` or `release-all` |
| Long build or test run | `mb lock --agent <you> alive <seconds> "<what>"` |
| Reviewer: anything mid-write? | `mb lock --agent <you> check <abs path>...` → exit 1 = locked, don't review yet |
| Who holds what | `mb lock --agent <you> status` |

1. **Proposer:** acquire every shared path a checkpoint writes (source files, the build folder, coverage data, the task state the skill updates) in **one** `acquire` before you start the checkpoint. Release them before you post the `SYNC`, so the reviewers see a finished state.
2. **Critic and lead:** you never acquire for writing. Before reviewing, `check` the files; if they are locked, the proposer is mid-write: wait for the SYNC.
3. **Never wait for messages while holding locks.** Release first.
4. **Stale owners:** never `reap`, `break` or `--force` on your own. Follow `LOCKING.md` rule 7: only the lead (or the proposer, if there is no lead) may reap a **teammate**, after asking them and getting no answer. Never reap an owner outside your team.
5. A skill in use may name extra paths to lock (for example its status file or a checkpoint name). Those rules are part of the contract.

## 6. Message types

| Type | Who | Meaning |
|---|---|---|
| `JOIN` / `FORMED` | `mb` | Sent automatically by `mb team join`. Never send these yourself. |
| `CONTEXT` | context owner | Sent by `mb team context`: task, repo, task dir, locks, skills, key files. |
| `SKILL` | anyone | "I loaded skill X, its SKILL.md is at P, I use it for Y." |
| `FINDINGS` | everyone | Everything you studied and know, in the format of Phase B. |
| `CONTRACT` | critic | Numbered checklist of every rule from every skill in use, plus the task's own requirements. |
| `QUESTION` / `ANSWER` | anyone | A specific question to the team or one teammate, and its answer (`--reply-to` the question). |
| `BOUNDARIES` | proposer | The team's shared understanding and scope (Phase C). |
| `PLAN` / `REVISED` | proposer | The plan, or the plan revised to answer each CHALLENGE point by number. |
| `CHALLENGE` | critic, lead | Numbered objections, each citing a CONTRACT rule, a boundary or a concrete failure. |
| `AGREED` | everyone | `AGREED: BOUNDARIES seq=N` or `AGREED: PLAN seq=N`. Every roster member must send it. |
| `SYNC` | proposer | A checkpoint report with evidence (Phase E). |
| `REVIEW` | critic, lead | Verdict on a SYNC: `OK`, or numbered issues citing CONTRACT rules or boundaries. |
| `NOTE` | anyone | Extra information, such as what your own instructions said or a lock you reaped. |
| `BLOCKED` | anyone | You cannot proceed. Say on what. |
| `DONE` | proposer | The task is finished and the final review is OK. |

## 7. The protocol

### Phase A: form the team and share context
Do section 2.

### Phase B: study, then put everything you know on the board
Everyone studies independently: the task, the key files, the task directory and every skill in use. Opinions about code or rules you have not read are worthless. Then **every** roster member posts their `FINDINGS`:
```
FINDINGS (<role>):
read: <every file, skill and doc you actually read, with absolute paths>
facts: <numbered facts about the code and the task, each with file:line or a quote>
constraints: <rules from the skills or the task that shape the work>
risks: <what could go wrong>
unknowns: <questions you could not answer from the files>
```
The critic also posts the `CONTRACT`: a numbered list of every rule that applies, each tagged with its source, for example `C3 [ut SKILL.md] every new test must fail when the branch under test is inverted` or `C7 [task] only module x`. It includes each skill's rules about what to lock.

Then **read every teammate's FINDINGS**:
- Answer their unknowns if you can (`ANSWER`, `--reply-to` the FINDINGS).
- Point out contradictions with your own findings (`QUESTION`), and resolve them by reading the code together, not by voting.
- Post a follow-up `FINDINGS` if you learn something important later.

**Phase B ends when** every roster member has posted FINDINGS, every unknown is answered or explicitly marked "cannot be known from the files", and nobody has an open QUESTION.

### Phase C: consensus on understanding and boundaries
The proposer merges everyone's findings into one `BOUNDARIES` message:
```
BOUNDARIES:
understanding: <3-8 lines: what exists today, what is missing, what the team will change. Only facts from FINDINGS.>
in scope: <the exact files, modules, functions and directories the team may change>
out of scope: <what nobody touches, including tempting neighbours>
roles: <proposer executes; critic (and lead) read and review>
shared resources: <absolute paths that must be locked when written: sources, build folder, coverage data, task state>
done when: <a measurable end condition, e.g. "MC/DC of module x >= 90% by <tool>, all tests pass">
open: <unknowns that remain and how the team will treat them>
```
Everyone checks it against their own FINDINGS and the CONTRACT, then replies `AGREED: BOUNDARIES seq=N` or `CHALLENGE`. **At most 3 rounds.** After that the lead decides, or the proposer if there is no lead. **No plan before every roster member has agreed to BOUNDARIES.**

### Phase D: agree on a plan
The proposer posts the `PLAN`. It must stay **inside BOUNDARIES**. The critic (and lead) reply with `CHALLENGE` or `AGREED: PLAN seq=N`; the proposer answers with `REVISED`. **At most 3 rounds.** After round 3 the lead decides, or the proposer if there is no lead. **No execution until every roster member has agreed to the PLAN.**

A PLAN must contain:
1. **Goal**: one sentence.
2. **Checkpoints**: numbered, each small enough to finish and verify on its own. Each states what "done" looks like, **which evidence** the SYNC will include (a command and its output, a coverage report, a diff), and **which paths it locks**.
3. **Contract mapping**: for each CONTRACT rule, which checkpoint satisfies it, or why it does not apply.
4. **Risks**: what could go wrong and how you will notice.

### Phase E: checkpoints (the proposer executes, the reviewers verify)
For each checkpoint:
1. **Proposer:** `acquire` the checkpoint's paths in one call (and `alive` for long builds), do the work, run it, `release` the paths, then post:
   ```
   SYNC cp<N>: <done | partial | failed>
   files: <absolute paths changed>
   evidence: <exact commands run and their key output, e.g. "ctest: 14 passed, 0 failed">
   contract: <rule ids this checkpoint satisfies, and how>
   notes: <anything a reviewer must know>
   next: cp<M>
   ```
2. **Critic (and lead):** `check` the files, then read the actual changed files, the diff and the evidence, not just the summary. Check them against every applicable CONTRACT rule and against BOUNDARIES: **any change outside "in scope" is a violation**. Do not run builds or tests yourself. If evidence is missing or unconvincing, ask for exactly what you need. Then send `REVIEW cp<N>: OK` or numbered issues.
3. **Proposer:** fix the issues, or reply explaining why they are wrong, then re-SYNC.
4. **Sync point:** the proposer does not start the next checkpoint until the current one has `REVIEW ... OK` from every reviewer. A reviewer silent for 10 waits gets a `BLOCKED`, then the proposer proceeds.

### Phase F: finish
- The proposer runs the full verification once more (under lock) and posts `SYNC final:` with the evidence.
- The critic (and lead) review it against the whole CONTRACT and BOUNDARIES, and send `REVIEW final: OK` or issues.
- After every reviewer's OK: everyone runs `mb lock --agent <you> release-all`, and the proposer checks `status` shows no team locks, then posts `DONE`. Everyone stops.

## 8. Discipline
- Check your inbox at the start of every phase and after every checkpoint, at minimum.
- Announce every skill you load (section 4). No exceptions.
- Critic and lead: never edit files, build, run tests or change state. Reading is your only tool.
- Disagree with evidence: a rule id, a boundary, a file path, a line number, a failing command. Never just "I'm not sure about this."
- Agree when you are convinced. Endless debate is a failure mode, just like blind agreement.
