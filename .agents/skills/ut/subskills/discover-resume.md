# Sub-skill: discover-resume (phase 3, mode "resume")

Goal: turn what an earlier session left behind into `Candidate work` in context.md.

1. Read from TASK/status.md: `Plan`, `Open issues`, `Next steps`, last 15 `Log` lines.
2. Read TASK/context.md sections 5 and 6.
3. Check that the recorded state is still true:
   - `git status --short` and `git log --oneline -10` — did files change since the last Log date?
   - For each task marked IN_PROGRESS: is an executor still running? Ask the user.
     If not, set it back to TODO and note it in Log.
   - In parallel mode: `"$SKILL_DIR/resources/scripts/lock.sh" "$TASK/locks" status`.
     For each STALE owner: tell the user who, since when, which locks. Only with their approval:
     `lock.sh "$TASK/locks" reap <ID>`, and set that owner's IN_PROGRESS tasks back to TODO.
4. Build the list:
   - Tasks TODO / PARTIAL / BLOCKED → candidate rows (keep their task file).
   - Each `Next steps` bullet and each open issue → candidate row.
   Write them into context.md section 5 with evidence `status.md` or the task file.
5. Show the list. Ask:
   "1) Continue exactly this  2) Add new work (then I also check the git diff or you describe it)  3) Change priorities"
   - Answer 2 with a diff → also load `subskills/discover-diff.md` after this one finishes.
   - Answer 2 described by the user → also load `subskills/discover-ask.md` after this one finishes.
6. Shortcut: if the plan already exists, nothing new was added, and the code did not change,
   tick phases 3–7 that were already done and go straight to phase 8 (executor).
7. Tick phase 3 in status.md, add a Log line.
