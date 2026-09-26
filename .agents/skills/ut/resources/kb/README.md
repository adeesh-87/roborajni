# Knowledge bases, one per codebase

Each folder here belongs to exactly ONE codebase:
```
kb/
  INDEX.md                 one row per codebase: id, remote, where it was seen
  <codebase-id>/
    kb.md                  ≤ 120 lines: identity, profile, VERIFIED build/run commands, conventions (with counts), build notes, module table
    exemplars/test.md      one real, approved test file, annotated, plus the skeleton to copy  (what every test writer reads)
    exemplars/mock.md      one real mock/stub with the test lines that drive it
    exemplars/register.md  the exact lines that add a test file to the build
    testscan.md            generated: framework, asserts, mock API, naming patterns with counts (scripts/testscan.sh)
    modules/<name>.md      per module: purpose, files, tests, facts, how to test, learnings
    modules/<name>.cards.md generated: one card per function (decisions, globals, calls, callers, tests)
    index/                 generated code index (scripts/index.sh): index.json exported from the Graphify graph
                           (graphify/), BUILD_ARGS, coverage.json, traces.json
    diagrams/              generated Mermaid text: flow/, seq/, scenarios/, traces/, SCENARIOS.md, INDEX.md
    decompositions/        notes written by a stronger model (optional)
```
When the `ut` tool builds the KB it also keeps `kb.json` (machine-readable truth) and renders `kb.md` from it;
hand-written notes then go to `notes.md` and `modules/<name>.md`, which the tool never overwrites.
`<codebase-id>` comes from `scripts/kb-id.sh <repo>` (based on the git `origin` URL), so every clone,
branch and machine of the same repository finds the same folder.

Rules:
- Never read or use a KB folder whose id differs from the current codebase's id.
- When you update the ut skill, KEEP this `kb/` folder (copy it over to the new version).
- If this skill folder lives inside a repository, the KB is committed with it unless you ignore it.
