---
name: ut-<project>
description: Unit tests for <project> (<repo>; <3-6 component or product names>; test binaries <names>). Use when writing, updating, fixing or removing unit tests, stubs or mocks in <project>, raising its coverage (<official tool>), or checking what a code change does to its tests. Drives the generic ut skill with this project's knowledge base.
---

# <project>: unit tests

Use the `ut` skill (`<absolute path of ut/SKILL.md>`) with `KB_DIR = <absolute path of the KB folder>`.
This file holds only what is specific to <project>. Where it differs from the ut skill or its playbooks, this file
wins.

## Always
At most 12 rules. Each rule is a fact from the KB and ends with its source, for example `(KB Commands)` or
`(workarounds.md #3)`.
1. Build `<cmd>`; run `<cmd>`; one group `<cmd>` (KB Commands).
2. A new test file copies `exemplars/test.md` (`<file>`) and is registered as `exemplars/register.md` shows.
3. Seams: access `<ID>`, replace `<ID>`, per-test `<ID>`, hardware `<ID>`, state `<ID>` (KB Test seams).
4. Stubs: `<mode>`. A test that wants the real function `<how>`. `<__typeof__ rule>` (notes.md Stubs).
5. <the workaround every new test must follow> (workarounds.md #n).
6. <the change hazard that bites most often> (change-impact.md <ID>).
7. <...>

## Load when
| Situation | Read |
|---|---|
| Writing tests for a component | `codebase.md` (its row, Rules), `modules/<name>.md` |
| A build, link or run error | `workarounds.md` (search the error text), then `resources/tools/errors/<framework>.md` |
| A diff, or "what does my change break" | `change-impact.md` (this codebase's study), notes.md `Change hazards` |
| Coverage or MC/DC | notes.md `Coverage`, `resources/tools/llvm-mcdc.md` |
| A generic ut rule seems wrong here | `learnings.md` (the project verdict wins) |

## Project playbooks
`<KB_DIR>/playbooks/<type>.md` holds only what differs from `resources/playbooks/<type>.md`, and is read after it:
<list, e.g. `fix-mocks.md` (the shared --wrap stubs), or "none: the generic playbooks fit">.
