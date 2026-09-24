---
name: ut
description: Plan, write, fix, remove and maintain C/C++ unit tests (CppUTest, GoogleTest/gMock, Unity/CMock/Ceedling, Parasoft C/C++test) and raise code coverage (Testwell CTC++, gcov/lcov/gcovr, Parasoft). Use when the user asks for unit tests, test updates after a code change, fixing a broken unit-test build or failing tests, removing obsolete tests, or improving coverage. Keeps all state in a task folder (status.md, context.md, kb.md) so work can be resumed later and split across parallel executor agents using path locks.
---

# ut — unit test task driver

You are the ORCHESTRATOR. Follow the steps below in order.
Load a sub-skill ONLY when a step tells you to. Read it fully, do it, then move on.
Never load two sub-skills at the same time.

## Names used in all ut files
- `SKILL_DIR` = absolute path of the folder that holds this SKILL.md.
- `TASK` = the task folder the user gives you.
- `KB` = the kb.md path written in status.md Config, normally `$SKILL_DIR/resources/kb/<codebase-id>/kb.md`.
  `KB_DIR` = its folder. A KB belongs to ONE codebase: never use another codebase's KB folder.
- Ask = ask the user and WAIT for the answer. Never invent an answer.
- Record = write it into the named file NOW, before doing anything else.
- In shell commands, write the real absolute paths for `$TASK`, `$SKILL_DIR`, `$KB`
  (or set them at the start of every command: shell variables are not kept between calls).

## Rules that are always on
1. The files in TASK are your memory. Record every answer, command and finding right away.
2. Do not change production code (code under test) unless Config says it is allowed.
3. Ask before you delete files, commit, push, or run anything that flashes or talks to hardware.
4. Copy the style of existing tests. Never invent a new style.
5. Ask short numbered questions, at most 5 per message, each with a suggested default in [brackets].
6. Read only the file sections you need. Do not paste big files into the chat.
7. Before you stop for any reason, update `Next steps` and `Log` in TASK/status.md.

## Step 0 — Task folder
1. Find SKILL_DIR (the directory of this file) as an absolute path.
2. Ask: "Path to the task folder? It will be created if missing."
3. If `TASK/status.md` exists, go to **Step R**.
4. Otherwise run:
   ```sh
   mkdir -p "$TASK/tasks" "$TASK/logs" "$TASK/locks"
   cp "$SKILL_DIR/resources/templates/status.md"  "$TASK/status.md"
   cp "$SKILL_DIR/resources/templates/context.md" "$TASK/context.md"
   ```
5. Record `Task folder` and `Skill dir` in the Config table of TASK/status.md.

## Step 1..9 — Phases
Do the phases in this order. For each phase: load the sub-skill, do it, then in TASK/status.md
tick the phase in `Phase tracker`, set `Current phase`, and add one line to `Log`.

| # | Phase | Load | Finished when |
|---|-------|------|---------------|
| 1 | Setup | `subskills/setup.md` | Config table is complete and confirmed |
| 2 | Knowledge | `subskills/knowledge.md` | KB has sources, code map, confirmed conventions |
| 3 | Discovery | ONE of the three files below | context.md `Candidate work` is filled |
| 4 | Build & run baseline | `subskills/build-run.md` | Commands verified, baseline recorded |
| 5 | Scope | `subskills/scope.md` | context.md `Confirmed scope` approved by user |
| 6 | Coverage | `subskills/coverage.md` — ONLY if scope has category G | context.md `Coverage gaps` filled |
| 7 | Plan | `subskills/plan.md` | Plan approved, task files written |
| 8 | Execute | `subskills/executor.md` | Every task is DONE, PARTIAL, BLOCKED or DROPPED |
| 9 | Close out | `subskills/closeout.md` | Final summary in status.md and KB updated |

Skip phase 6 when scope has no coverage work: tick it and write "skipped" after it.

### Choosing the discovery file (phase 3)
Ask: "What should I work on? 1) continue what status.md says  2) the code changes in git  3) I will tell you".
Pick the default like this:

| Situation | Load |
|-----------|------|
| status.md has `Next steps` or open tasks from an earlier session | `subskills/discover-resume.md` |
| User says "my changes", "the diff", "this branch", "after refactoring" | `subskills/discover-diff.md` |
| Anything else: a module, a feature, a ticket, a bug, "improve coverage of X", "fix the build" | `subskills/discover-ask.md` |

Record the choice in Config `Discovery mode`.

## Step R — Resume
1. Read TASK/status.md sections `Config`, `Phase tracker`, `Next steps`, `Open issues` only.
2. Tell the user in 3–5 lines: current phase, what is done, what is next.
3. If Config says parallel executors: run `"$SKILL_DIR/resources/scripts/lock.sh" "$TASK/locks" status`.
   Report every STALE owner to the user. Remove its locks only if the user approves (`reap <ID>`).
4. If the user says they are an **executor** (e.g. "executor E2"), load `subskills/executor.md` now.
5. Otherwise continue at the first unticked phase in the table above.
   If phases 1–7 are ticked and new work is requested, go back to phase 3 and pick a discovery file.

## Resource files (loaded by sub-skills, listed in Config `Resources to load`)
| Config says | Load |
|-------------|------|
| CppUTest / CppUMock | `resources/tools/cpputest.md` |
| GoogleTest / gMock / FFF | `resources/tools/gtest-gmock.md` |
| Unity / CMock / Ceedling | `resources/tools/unity-cmock.md` |
| Parasoft C/C++test (tests, stubs or coverage) | `resources/tools/parasoft-cpptest.md` |
| Testwell CTC++ | `resources/tools/ctc.md` |
| gcov, lcov, gcovr, llvm-cov | `resources/tools/gcov-lcov.md` |
| CMake, Make, Ceedling, scripts, CI files | `resources/tools/build-systems.md` |
| Writing any test | `resources/test-design.md` |
| Diff or user-described change analysis | `resources/impact-analysis.md` |
| Codebase id / KB folder (phase 2) | `resources/scripts/kb-id.sh` (run it) |
| Code map of functions, calls, dependencies | `resources/scripts/codemap.sh` (run it; read its output in `KB_DIR/codemap/`) |
| A task of type `<type>` (executor only) | `resources/playbooks/<type>.md` |
| Parallel executors | `resources/scripts/lock.sh` (run it, do not read it; `status` shows who holds what) |
