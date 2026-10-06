---
name: team
description: Join a team of agents that collaborate through the `mb` message board. Invoke with a role, e.g. `/team proposer label=mcdc1 use the ut skill to raise MC/DC of module x` or `/team critic label=mcdc1`. Finds or forms a team, shares the task context, gives you a role (see roles/) and the team protocol.
argument-hint: <role> [roles=proposer,critic] [label=name] [task...]
---

# Team mode

You are one member of a small team of agents working on the same task, in the same repository, at the same time. You cannot see the other agents. You communicate with them **only** through the `mb` message board. Nobody is supervising this run: no human will answer questions or unblock you. The team succeeds or fails on its own.

**Who does what:**
- The **proposer** is the only one who executes: edits files, builds, runs tests, uses tools that change state.
- The **critic** and the **lead** never execute anything. They only read: files, diffs, skills and the board. Their job is to hold the plan and the work to the **contracts**, meaning the rules of every skill in use in this session, and to the task.

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
skills: <every skill in use, each with the absolute path of its SKILL.md>
key files: <absolute paths of the files the task is about>
notes: <anything from the user's instructions a teammate must know>
EOF
)"
```
If the context changes later, for example a new directory or a new skill, run `mb team context` again. Teammates receive every update.

**Step 2b: if you are not the context owner, do nothing on the task until you have the shared context.** If `team join` already printed it, use that. If not, read the board and wait for the `CONTEXT:` message:
```bash
mb inbox --agent <your id> --wait 90
```
Then, before anything else, read what the context names: the task directory, the key files and **the SKILL.md of every listed skill**. Do not guess the task from your own instructions; the team's context is authoritative.

**Step 3: wait for `FORMED:`**, which arrives once every role is filled. It carries the final task and the roster (every teammate's agent id). Wait at most 10 calls of `--wait 90` (about 15 minutes) for `FORMED` and, separately, for `CONTEXT`. If either never comes, stop and report "team did not form" or "no shared context". Do not do the task alone. If the team task is `(none given)`, stop and report that.

If you lose track of your id, team, roster or context: `mb team show --agent <your id>`.

## 3. Skills are contracts: announce every skill you load

Each skill in use (the unit-test skill, this one, any other) defines rules: required steps, required outputs, forbidden actions, required evidence. Those rules are the **contract** the team is held to.

**Whenever you load or start following a skill, at any point in the run, immediately announce it:**
```bash
mb say "SKILL: <skill name> | <absolute path to its SKILL.md> | <one line: what you are using it for>" --agent <your id>
```
This matters most for the critic and the lead, who must read every skill to enforce it. A skill they don't know about is a contract nobody checks.

When you receive a `SKILL:` message, read that SKILL.md (and any rule files it points to) before your next review.

## 4. How to use `mb`

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

Rules:
- Every message starts with one **TYPE** tag (section 5).
- Keep messages self-contained: absolute file paths, function names, the concrete reason. A teammate reading only your message must understand it.
- For multi-line bodies use a heredoc so quotes and newlines survive. The closing `EOF` must be alone on its line:
  ```bash
  mb say "$(cat <<'EOF'
  PLAN:
  1. ...
  EOF
  )" --agent proposer@t-3f9a2c
  ```
- `--wait` takes at most 90 seconds per call. To wait longer, call it again. **Wait at most 10 calls (about 15 minutes) in a row.** If you still have nothing, post `BLOCKED:` saying what you are waiting for, then continue with your best judgement. Never stall forever.

## 5. Message types

| Type | Who | Meaning |
|---|---|---|
| `JOIN` / `FORMED` | `mb` | Sent automatically by `mb team join`. Never send these yourself. |
| `CONTEXT` | context owner | Sent by `mb team context`: task, repo, task dir, skills, key files. |
| `SKILL` | anyone | "I loaded skill X, its SKILL.md is at P, I use it for Y." |
| `CONTRACT` | critic | Numbered checklist of every rule from every skill in use, plus the task's own requirements. |
| `PLAN` / `REVISED` | proposer | The plan, or the plan revised to answer each CHALLENGE point by number. |
| `CHALLENGE` | critic, lead | Numbered objections, each citing a CONTRACT rule or a concrete failure. |
| `AGREED` | everyone | "I accept plan seq=N as final." Every roster member must send it. |
| `SYNC` | proposer | A checkpoint report with evidence (format below). |
| `REVIEW` | critic, lead | Verdict on a SYNC: `OK`, or numbered issues citing CONTRACT rules. |
| `NOTE` | anyone | Extra information, such as what your own instructions said. |
| `BLOCKED` | anyone | You cannot proceed. Say on what. |
| `DONE` | proposer | The task is finished and the final review is OK. |

## 6. The protocol

### Phase A: form the team and share context
Do section 2. Then everyone studies the task, the key files and every skill in use. Opinions about code or rules you have not read are worthless.

The critic then posts the `CONTRACT`: a numbered list of every rule that applies, each tagged with its source, for example `C3 [ut SKILL.md] every new test must fail when the branch under test is inverted`. Include the task's own requirements, for example `C7 [task] only module x`. The proposer and the lead may add missing rules with `NOTE`. The critic re-posts the list if it changes.

### Phase B: agree on a plan
- After the `CONTRACT`, the proposer posts the `PLAN`. The critic (and lead) reply with `CHALLENGE` or `AGREED`. The proposer answers with `REVISED`.
- **At most 3 rounds of CHALLENGE.** After round 3 the final call goes to the `lead` if the roster has one, or else to the proposer. Their next plan is final and everyone sends `AGREED`.
- **No execution until every roster member has sent `AGREED`.**

A PLAN must contain:
1. **Goal**: one sentence.
2. **Checkpoints**: numbered, each small enough to finish and verify on its own. Each states what "done" looks like and **which evidence** the SYNC will include, such as a command and its output, a coverage report or a diff.
3. **Contract mapping**: for each CONTRACT rule, which checkpoint satisfies it, or why it does not apply.
4. **Risks**: what could go wrong and how you will notice.

### Phase C: checkpoints (the proposer executes, the reviewers verify)
For each checkpoint:
1. **Proposer:** do the work, run it, then post:
   ```
   SYNC cp<N>: <done | partial | failed>
   files: <absolute paths changed>
   evidence: <exact commands run and their key output, e.g. "ctest: 14 passed, 0 failed">
   contract: <rule ids this checkpoint satisfies, and how>
   notes: <anything a reviewer must know>
   next: cp<M>
   ```
2. **Critic (and lead):** read the actual changed files, the diff and the evidence, not just the summary. Check them against every applicable CONTRACT rule. Do **not** run builds or tests yourself. If evidence is missing or unconvincing, ask for exactly what you need. Then send `REVIEW cp<N>: OK` or numbered issues, each citing a rule id or a concrete failure.
3. **Proposer:** fix the issues, or reply explaining why they are wrong, then re-SYNC.
4. **Sync point:** the proposer does not start the next checkpoint until the current one has `REVIEW ... OK` from every reviewer. A reviewer silent for 10 waits gets a `BLOCKED`, then the proposer proceeds.

### Phase D: finish
- The proposer runs the full verification once more and posts `SYNC final:` with the evidence.
- The critic (and lead) review it against the whole CONTRACT and send `REVIEW final: OK` or issues.
- After every reviewer's OK, the proposer posts `DONE`. Everyone stops.

## 7. Discipline
- Check your inbox at the start of every phase and after every checkpoint, at minimum.
- Announce every skill you load (section 3). No exceptions.
- Critic and lead: never edit files, build, run tests or change state. Reading is your only tool.
- Disagree with evidence: a rule id, a file path, a line number, a failing command. Never just "I'm not sure about this."
- Agree when you are convinced. Endless debate is a failure mode, just like blind agreement.
