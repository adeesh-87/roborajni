# Phase 4 — Discovery, mode "resume"

Goal: continue an earlier session correctly.

1. Read status.md `Plan`, `Open issues`, `Next steps`, last 15 `Log` lines; context.md `Work items`.
2. Check reality: `git status --short`, `git log --oneline -10` since the last Log date. Code or tests changed since
   KB `Identity` → last graph build → load `subskills/refresh.md` first. Tasks IN_PROGRESS with
   no running executor (parallel: `lock.sh ... status`, STALE owners) → back to TODO with a Log line; `reap` only
   with approval.
3. Work items still open (TODO / PARTIAL / BLOCKED tasks, `Next steps`, open issues) stay as they are.
   The user added new work → also run `discover-diff.md` or `discover-ask.md` for it.
4. Plan exists, nothing new, code unchanged → tick phases 4–8 as done and go to phase 9.
Tick phase 4.
