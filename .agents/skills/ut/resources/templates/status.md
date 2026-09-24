# UT Task Status

> Single source of truth for this task. Keep the sections in this order.
> Edit sections in place. Only append to `Log`. In parallel mode lock this file before editing it.

## 1. Config
| Key | Value |
|-----|-------|
| Task folder | |
| Skill dir | |
| Repo root | |
| Code under test (paths) | |
| Test code (paths) | |
| Mocks / stubs / fakes (paths) | |
| Language and standard | e.g. C99, C++14, mixed |
| Compiler / toolchain | |
| Tests run on | host / simulator / target |
| Test framework | |
| Mock / stub approach | |
| Build system for tests | |
| Env setup needed | script to source, license server, docker image |
| Coverage wanted | yes / no |
| Coverage tool | |
| Coverage metric and target | e.g. statement 100 %, decision 90 %, MC/DC |
| Coverage report location / format | |
| Production code changes allowed | no |
| Test deletion allowed | ask each time |
| Commit policy | never, user commits |
| Coding standard for tests | |
| KB path | `<SKILL_DIR>/resources/kb/<codebase-id>/kb.md` (set in phase 2) |
| Parallel executors | no / yes, ids |
| Resources to load | |
| Discovery mode | resume / diff / ask |

## 2. Phase tracker
Current phase: 1
- [ ] 1 Setup
- [ ] 2 Knowledge
- [ ] 3 Discovery
- [ ] 4 Build & run baseline
- [ ] 5 Scope
- [ ] 6 Coverage
- [ ] 7 Plan
- [ ] 8 Execute
- [ ] 9 Close out

## 3. Commands (verified by running them)
Run every command from `Run from`. Write commands exactly, copy-paste ready.
| Purpose | Command | Run from | Verified on | Notes |
|---------|---------|----------|-------------|-------|
| Env setup | | | | |
| Clean | | | | |
| Build tests | | | | |
| Run all tests | | | | |
| Run one group / test | | | | |
| Compile DB (test build) | path to compile_commands.json, or none | | | |
| Coverage build | | | | |
| Coverage report | | | | |
| Coverage report output path | | | | |

Paths to lock while building or running (parallel mode):
- 

## 4. Baseline
Date:
Build: OK / FAILED (log: logs/build-baseline.log)
Tests: total / passed / failed / crashed (log: logs/run-baseline.log)
Coverage: (if measured)

## 5. Plan
Plan approved by user on:
Complexity: simple / complex (see plan.md rules)
Status values: TODO, IN_PROGRESS, DONE, PARTIAL, BLOCKED, DROPPED

| ID | Title | Type | Wave | Depends on | Status | Owner | Task file |
|----|-------|------|------|------------|--------|-------|-----------|

Checkpoints:
- After wave 1: full build + all tests pass
- 

## 6. Executors
| ID | Started | Current task | Last seen | Notes |
|----|---------|--------------|-----------|-------|

## 7. Open issues
| # | Issue | Found by | Blocking? | Owner |
|---|-------|----------|-----------|-------|

## 8. Next steps (read this first when resuming)
- 

## 9. Log
- YYYY-MM-DD HH:MM [who] message
