# `ut` — the tool around the agent

Everything in the unit-test workflow that a script can do is done by this tool: detection, questions with
defaults, the baseline build, the knowledge base (graph, test scan, exemplars, per-function cards), the impact
list of a code change, scope, the plan with a Cases table per task, the executor loop (build, run, first error,
retry, checkpoint, refresh) and the close-out. The agent is called only to write or fix test code, once per task,
with a prompt of about 1,500–1,800 words that contains only that task's inputs.

Requirements: Python 3.10+ (the skill venv is used when present: run `index.sh setup clang` once), git, bash.
The skill (`SKILL.md`) stays the path for driving an agent without the tool; both read the same resource files.

```sh
UT=.agents/skills/ut/resources/scripts/ut
$UT init     --task .ut/2026-09-25-uart --repo .            # phase 1: shows the detected profile, asks 5 questions (--yes = defaults)
$UT baseline --task .ut/2026-09-25-uart                     # phase 2: build + run, compile DB, commands into the KB
$UT kb       --task .ut/2026-09-25-uart [--files src/uart.c] # phase 3: code index (backend chosen here), testscan, exemplars, conventions, cards, diagrams
$UT discover --task .ut/2026-09-25-uart --base origin/main   # phase 4: impact list (or --uncommitted, --range A..B, --names f1 f2)
$UT scope    --task .ut/2026-09-25-uart                     # phase 5: which items, acceptance; decides the pilot
$UT pilot    --task .ut/2026-09-25-uart --agent "claude -p ..." # phase 6: two tests, reviewed by you, become the exemplar
$UT coverage --task .ut/2026-09-25-uart --cmd "<coverage build+run>" --gcov-dir build-cov   # phase 7: import (or --lcov / --ctc profile.txt), gaps -> work items
$UT plan     --task .ut/2026-09-25-uart                     # phase 8: tasks/Tnn.md with Cases from the cards (coverage tasks: the missing outcomes)
$UT run      --task .ut/2026-09-25-uart --agent "claude -p ..." # phase 9: the loop; --dry-run writes the prompts only; --diagrams auto|on|off
$UT close    --task .ut/2026-09-25-uart                     # phase 10: final build, summary, refresh
$UT index    --task .ut/2026-09-25-uart --backend gcc       # rebuild the code index with another backend (--compare gcc: diff only)
$UT trace    --task .ut/2026-09-25-uart                     # runtime sequence per TEST; cards gain "reached at run time"
```
Code index: `ut kb` runs `index.sh detect` and uses `clang` when libclang parses the code cleanly, otherwise asks once
between `gcc` and `graphify` when both work (`resources/index-backends.md`). Set `index_backend=<name>` in the profile
to skip detection. Diagrams: the prompt gets a flowchart for coverage tasks and branchy functions (>= 4 decisions) and a
sequence for functions with >= 2 mockable collaborators, at most 900 words; `diagrams=off` in the profile disables them.
`--answers answers.json` makes any phase non-interactive; `--yes` takes every default.

The agent command receives the prompt on stdin (or use `{prompt}` for the file path). Default:
`claude -p --permission-mode acceptEdits --allowedTools Read,Edit,Write,MultiEdit,Glob,Grep`.
Any CLI that can edit files works (Codex, Gemini CLI, aider); the prompt tells it which files it may write and to
end with `RESULT: DONE` or `RESULT: PARTIAL <reason>`. The tool ignores claims and checks the build and tests itself.

What the tool guarantees per task: only the task's `Touches` are expected to change; a new test file must be
registered in the build (else the agent is asked again); at most 3 attempts, each with the first error and the
matching rows of the framework's error table; a BLOCKED task's files are restored and the broken attempt is kept
in `<task>/blocked/<id>/`; a wave checkpoint (full build + all tests) runs when the wave is finished, then the KB
is refreshed so the next wave's cards see the new tests.

Files: `state.json` (truth), `status.md` and `context.md` (rendered), `impact.md`, `tasks/*.md`, `prompts/*.md`,
`logs/`. The KB (`resources/kb/<codebase-id>/`) holds `kb.json` + rendered `kb.md`, `exemplars/`, `modules/*.cards.md`,
`testscan.md`, `index/` (the code index, coverage.json, traces.json), `diagrams/`; hand-written notes go to `notes.md`
and `modules/<name>.md`.
