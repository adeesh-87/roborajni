---
name: ut
description: Plan, write, fix, remove and maintain C/C++ unit tests (CppUTest, GoogleTest/gMock, Unity/CMock/Ceedling, Parasoft C/C++test) and raise code coverage (Testwell CTC++, gcov/lcov/gcovr, Parasoft). Use when the user asks for unit tests, test updates after a code change, fixing a broken unit-test build or failing tests, removing obsolete tests, or improving coverage. Keeps a per-codebase knowledge base and a task folder (status.md, context.md) so work can be resumed and split across parallel executor agents.
---

# ut — unit test task driver

You are the ORCHESTRATOR. Do the phases in order. Load ONE sub-skill at a time, follow it, then
continue here. Everything you learn goes into files; your memory is those files.

## Names
- `SKILL_DIR` absolute path of the folder holding this file. `TASK` the task folder. `KB_DIR` the
  codebase's knowledge folder (`SKILL_DIR/resources/kb/<codebase-id>/`, found in phase 3). `KB` = `KB_DIR/kb.md`.
- In shell commands write real absolute paths; shell variables are not kept between calls.
- **Ask** = ask the user and wait. **Record** = write it to the named file now.

## Rules
1. Never change production code (code under test) unless status.md Config allows it.
2. Ask before deleting files, committing, pushing, or running anything that flashes or talks to hardware.
3. Copy the approved exemplar (`KB_DIR/exemplars/test.md`) for every test you write. Never invent a style.
4. Never weaken or delete an assertion to make a test pass. A test that shows the code is wrong is
   reported as an open issue (category I), not "fixed".
5. Read only the file sections a step names. Never paste whole files into the chat.
6. Code questions go to the code index, not to the source files: `index.sh find|defs|list|source|refs|card|deps|tests`
   (`resources/graph-queries.md`). Open a source file only for a line range the index gave you, or when the index
   says `not in the index`. `grep` is for logs, build files, generated mocks and one text check before deleting code.
7. Before you stop for any reason, update `Next steps` and `Log` in TASK/status.md.

## Asking the user (question budget)
- Look first, then ask. Show what you found in a table and ask the user to correct it; do not ask
  what a file can tell you (paths, framework, build system, CI command).
- At most 4 numbered questions per message, each with a default in `[brackets]`. Silence or "ok" = default.
- Never ask the same thing twice: check status.md Config and context.md `Decisions` first.
- Prefer "review this concrete test file" over "describe your rules". The pilot phase exists for that.
- Questions are allowed only where a phase says so.

## Phases
| # | Phase | Load | Asks | Done when |
|---|-------|------|------|-----------|
| 1 | Setup | `subskills/setup.md` | 2 messages | status.md Config confirmed |
| 2 | Baseline | `subskills/baseline.md` | 0–1 | KB has verified commands; baseline recorded |
| 3 | Knowledge | `subskills/knowledge.md` | 0–1 | KB has code index, testscan, exemplar draft, module cards, diagrams |
| 4 | Discovery | one of `subskills/discover-{resume,diff,ask}.md` | 0–1 | context.md work items filled |
| 5 | Scope | `subskills/scope.md` | 1 | work items approved; pilot need decided |
| 6 | Pilot | `subskills/pilot.md` — only if scope says `Pilot: yes` | 1–3 reviews | exemplar approved, 2 tests pass |
| 7 | Coverage | `subskills/coverage.md` — only if a work item has category G or the user wants coverage | 0–1 | coverage gaps listed |
| 8 | Plan | `subskills/plan.md` | 1 | plan approved, task files written |
| 9 | Execute | `subskills/executor.md` | only on blockers | every task DONE / PARTIAL / BLOCKED / DROPPED |
| 10 | Close out | `subskills/closeout.md` | 0 | final summary; KB updated |

After each phase: tick it in status.md `Phases`, set `Current phase`, add one `Log` line.
Skipped phases (6, 7): tick and write `skipped`.
Any time the code or the tests changed (a finished round, a new commit, the user asks): load `subskills/refresh.md`
so the index, the cards and the diagrams match the code again. One command.

## Code index and diagrams
All code facts come from ONE index (`KB_DIR/index/index.json`) built by `resources/scripts/index.sh` with the backend
that works best on this machine: `clang` (compiler AST, default), `gcc` (your own compiler's call graph), `graphify`
(tree-sitter, no compile needed) or `codemap` (bash). Phase 3 picks it (`resources/index-backends.md`). Every query
(`card`, `deps`, `tests`, `impact`) and view is the same whatever the backend. Views are Mermaid TEXT for agents:
`flow` (branches of a function, with coverage counts), `seq` (calls in order, with existing test doubles),
`scenarios` (one sequence per entry point), `trace` (what a test really called). Reading them: `resources/diagrams.md`.

### Discovery file (phase 4)
| The user's answer in setup | Load |
|----------------------------|------|
| "continue", or status.md has `Next steps` / open tasks from an earlier session | `discover-resume.md` |
| "my changes", "the diff", "this branch", "after the refactoring" | `discover-diff.md` |
| a module, feature, ticket, bug, "coverage of X", "fix the build" | `discover-ask.md` |

## Two ways to run this skill
- **Tool-driven (fewest tokens):** `resources/scripts/ut` runs phases 1–5, 7, 8, 10 as scripts, asks the user the
  same questions with defaults, and calls an agent per task with a prompt that holds only that task's inputs
  (see `resources/scripts/README-ut-tool.md`). When the user runs the tool, you are that per-task agent: follow the
  prompt you receive, nothing below applies.
- **Agent-driven:** the phases below, for an agent session without the tool.

## Start
1. Ask (one message): "1) Task folder? [`<repo>/.ut/<YYYYMMDD>-<short-name>`, created if missing]
   2) What should I work on? (the changes on this branch / a module, feature or ticket / continue the last task)"
2. `TASK/status.md` exists → **Resume** below. Otherwise:
   ```sh
   mkdir -p "$TASK/tasks" "$TASK/logs" "$TASK/locks"
   cp "$SKILL_DIR/resources/templates/status.md" "$TASK/status.md"; cp "$SKILL_DIR/resources/templates/context.md" "$TASK/context.md"
   ```
   Record the answers (Config `Task folder`, `Skill dir`, `Request`; context.md section 1). Go to phase 1.

## Resume
1. Read status.md `Config`, `Phases`, `Next steps`, `Open issues` only.
2. Tell the user in 3 lines: current phase, done, next.
3. Parallel executors in Config → `"$SKILL_DIR/resources/scripts/lock.sh" "$TASK/locks" status`; report STALE owners;
   `reap` only with approval.
4. User says they are an executor (e.g. "executor E2") → load `subskills/executor.md`.
5. Otherwise continue at the first unticked phase. New work on a finished task → phase 4 again.
