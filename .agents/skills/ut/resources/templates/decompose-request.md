# Decomposition request for a stronger model

You are asked to split a unit-test task into small, independent tasks that a smaller
model can execute, several in parallel. Do not write test code. Write only the plan.

## Read these files (in this order)
1. <TASK>/status.md — sections Config, Commands, Baseline
2. <TASK>/context.md — all sections
3. <KB> — sections 2, 3, 5, 6
4. <SKILL_DIR>/subskills/plan.md — the rules a plan must follow
5. <SKILL_DIR>/resources/templates/task.md — the task file format

## Why this was escalated
(filled by the planner: which complexity rules fired)

## Output required
1. One file per task: <TASK>/tasks/T01.md, T02.md, ... using the task template.
   Each task: one type, a complete `Touches` list, a verifiable `Done when`, an existing test to imitate.
2. Fill <TASK>/status.md section 5 (Plan) with the task table, waves and checkpoints.
3. Tasks in the same wave must have NO overlapping `Touches` paths (a directory overlaps everything inside it).
4. Put edits to shared files (common mocks, build lists, fixtures used by many tests) in their own
   task in an early wave, so later tasks do not need to touch them.
5. Add to status.md `Log`: "plan written by <model>".
6. Tell the user: plan is ready, ask them to approve it, then start executors.
