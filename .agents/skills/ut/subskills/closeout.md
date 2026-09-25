# Phase 10 — Close out

1. Parallel → `lock.sh "$TASK/locks" status`: only your locks may remain (others → ask; `reap` only with approval).
2. Clean build + all tests (+ coverage if in scope) with KB `Commands` → `$TASK/logs/final-*.log`. Compare with `Baseline`.
3. status.md `Final summary` (after `Log`):
   ```
   Date | Tasks: done/total, partial, blocked, dropped | Build: OK/FAILED | Tests: passed/total (baseline p/t)
   Coverage: before → after (target) | Acceptance met: yes/no (reason) | Open issues: n | Production bugs reported: ...
   ```
   Rewrite `Next steps` so a new session needs nothing else. Tick phase 10.
4. KB: move task learnings into the right place (module file, Conventions, Build notes); load `subskills/refresh.md`
   (graph, testscan and cards include the new tests); set `Last updated` in KB and INDEX.md.
5. Report: the summary numbers, files changed (tests / mocks / build), open issues, next steps. Remind the user
   nothing was committed if Config says so. Parallel → `release-all`.
