# Phase 5 — Scope

Goal: the user approves the work items; decide whether a pilot is needed.

## 1. One message
Show context.md `Work items` grouped by category (A remove, B update tests, C mocks/stubs, D new tests,
E fix build, F fix failing run, G coverage, H cleanup, I production bug → report only). Ask:
```
1) In scope? [all]   (name rows to drop or add)
2) Order? [E, F, C, B, A, D, G]  (the build must work before anything else can be checked)
3) Done when? [build OK, all tests pass, no new warnings]   coverage target if G: [from setup]
4) Deleting (A rows): [ask before each deletion]
```
Record: `In scope`, `Priority`, `Acceptance` columns; `Acceptance for the task`; context.md `Decisions`.
Every I row also goes to status.md `Open issues`.

## 2. Pilot decision (no question)
`Pilot: yes` when ANY holds: KB `Conventions` is `DRAFT` or `greenfield` (first task on this codebase);
an in-scope module has no test file yet; the user asked to agree the style first. Otherwise `Pilot: no`.
Write it in status.md `Config`. Tell the user in one line why.
Tick phase 5.
