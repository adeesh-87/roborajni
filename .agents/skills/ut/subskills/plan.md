# Phase 8 — Plan

Goal: small checkable tasks in waves → `TASK/tasks/Tnn.md` + status.md `Plan`.

## 1. Complexity (first)
Escalate if ANY: > 10 tasks or > 3 waves; a shared mock/fixture/build file change reaches > 5 test files; a header
signature change reaches > 3 modules; the baseline build is broken for an unclear reason; the cards for in-scope
modules are missing; context.md says `complex`; MC/DC target or > 30 coverage `test` rows; you are unsure how to split.
Escalate = copy `resources/templates/decompose-request.md` to `$TASK/decompose-request.md`, fill the placeholders,
list the rules that fired, write it in `Next steps`, tell the user to run a stronger model on that file, STOP.

## 2. Tasks
One task = one type (`add-tests`, `update-tests`, `remove-tests`, `fix-mocks`, `fix-build`, `fix-run`,
`raise-coverage`), ONE test or mock file, ≤ 5 functions. Copy `resources/templates/task.md` to `TASK/tasks/Tnn.md`:
- `Inputs`: the card file + function names, `exemplars/test.md` (+ `mock.md` when mocking), the tool file, the
  playbook. Nothing else.
- `Touches`: every path the task may write (test file, mock file, build registration file). Not the build folder.
- `Cases`: from the card's `Decisions` plus the table in `resources/test-design.md` (boundaries, loop counts,
  dependency errors): one line per case `inputs | mock setup | expected`. The executor writes one test per line.
  Keep 3–12 lines; split the task if more.
- `Done when`: the single-test command and the expected summary line.

## 3. Waves
Wave 1 `fix-build` + shared-file changes (common mocks, fixtures, build lists) bundled; wave 2 `fix-mocks`,
`remove-tests`, `update-tests`; wave 3 `add-tests`, `fix-run`; wave 4 `raise-coverage`.
No two tasks in one wave may share a `Touches` path (a folder covers its contents). `Depends on` = tasks that must
be DONE first. Checkpoint after each wave: full build + all tests.

## 4. Approve (one message)
Fill status.md `Plan` (rows TODO, Owner empty; checkpoints). Show it. Ask:
```
1) Approve the plan? [yes]
2) Parallel executors? [no]   if yes: how many / IDs [E1 E2 E3], own build folder per executor? [no]
```
Parallel → Config `Parallel executors: yes, E1..En`; `echo "stale_after=<2x full build+run seconds, min 1800>" > "$TASK/locks/config"`;
tell the user they can watch with `lock.sh "$TASK/locks" watch 10` and start each executor with:
`Use the ut skill. Task folder: <TASK>. You are executor E2.`
Tick phase 8. Single mode → load `subskills/executor.md` as E1.
