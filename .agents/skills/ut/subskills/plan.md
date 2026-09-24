# Sub-skill: plan (phase 7)

Goal: small, checkable tasks, grouped in waves so several executors can work in parallel
without touching the same paths. Result: TASK/tasks/Tnn.md files + status.md section 5.

## Step 1 — Complexity check (do this FIRST)
The task is **complex** if ANY of these is true:
- more than 10 tasks would be needed, or more than 3 waves
- one mock, stub, fixture or build file must change and more than 5 test files depend on it
- a header signature change reaches more than 3 modules
- the baseline build is broken and the cause is not clear
- KB code map or conventions are missing for in-scope modules
- context.md section 8 says "complex" (discovery found more than 40 changed functions)
- target is MC/DC, or coverage gaps have more than 30 `test` rows
- you are unsure how to split the work
If complex:
1. Copy `resources/templates/decompose-request.md` to `TASK/decompose-request.md`.
   Replace `<TASK>`, `<KB>`, `<SKILL_DIR>`. Under "Why this was escalated" list the rules that fired.
2. Tell the user: "This task is complex. Please give `TASK/decompose-request.md` to a stronger
   model (for example a larger Claude model) to write the plan. Then start me again with this
   task folder." Record this in status.md `Next steps` and `Log`. STOP here.
If simple, continue.

## Step 2 — Make tasks
One task = one type (`add-tests`, `update-tests`, `remove-tests`, `fix-mocks`, `fix-build`,
`fix-run`, `raise-coverage`) and, as a rule, ONE test file or ONE mock file plus at most
5 functions under test. Split bigger work.
For each task, copy `resources/templates/task.md` to `TASK/tasks/Tnn.md` and fill:
- Goal, Scope items (S#/G#), Inputs (exact paths, the existing test file to imitate).
- **Touches**: every path the task may write. Include test files, mock files, build
  registration files (CMakeLists.txt, Makefile, project.yml). Do NOT include the shared build
  folder; executors lock it only while building.
- Steps: 3–8 concrete steps.
- Done when: commands with expected results (use the single-test command from status.md).

## Step 3 — Order and waves
1. Wave 1: `fix-build` tasks, and changes to SHARED files (common mocks, fixtures, build lists)
   bundled into as few tasks as possible. Nothing can be tested until the build works.
2. Wave 2: `fix-mocks`, `remove-tests`, `update-tests`.
3. Wave 3: `add-tests`, `fix-run`.
4. Wave 4: `raise-coverage` (needs the new tests first).
Rules:
- Two tasks in the same wave must have NO overlapping Touches. A directory overlaps every path
  inside it. If two tasks must write the same file, merge them or put them in different waves.
- `Depends on` lists task IDs that must be DONE first.
- After each wave add a checkpoint: "full build + all tests" (+ coverage report after the last wave).

## Step 4 — Write the plan
Fill status.md section 5: one row per task (Status TODO, Owner empty), the checkpoints,
and `Complexity: simple`.

## Step 5 — Approve and choose execution mode
Show the task table. Ask:
1. "Approve this plan? [yes]"
2. "Will you run several executor agents in parallel? [no]"
   If yes: "How many, and which IDs? [E1, E2, E3]" — record in Config `Parallel executors`.
3. If parallel and the build folder is shared: "Builds will run one at a time (locked). Can each
   executor use its own build folder instead? [no]" — update status.md section 3 if yes.
Write `Plan approved by user on <date>`.

## Step 6 — Hand over
Tick phase 7, set `Current phase: 8`, add a Log line.
- Single executor: load `subskills/executor.md` yourself with ID `E1`.
- Parallel: give the user one line per executor to start a new agent session with, e.g.
  `Use the ut skill. Task folder: <TASK>. You are executor E2.`
  You may run as E1 yourself: load `subskills/executor.md`.
