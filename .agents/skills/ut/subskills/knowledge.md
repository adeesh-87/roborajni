# Sub-skill: knowledge (phase 2)

Goal: KB contains (1) external knowledge sources, (2) a map of the in-scope code,
(3) test conventions confirmed by the user.

## Step 1 — Existing KB?
- If the KB file exists: read only sections 1, 3 and 7.
  Ask: "The knowledge base exists (last updated <date>). Refresh conventions or code map? [no]"
  If no: go to Step 5 to only add missing sources, then finish.
- If it does not exist: `cp "$SKILL_DIR/resources/templates/kb.md" "$KB"`.

## Step 2 — Existing knowledge from people or tools
Ask:
"Has anything already documented or decomposed this codebase? For example:
 1) architecture or design docs, requirement specs
 2) AGENTS.md, CLAUDE.md, README, CONTRIBUTING, docs/ folder
 3) output of agentic or analysis tools: code maps, repo wikis, call graphs, module summaries, Doxygen
 4) a kb.md or status.md from an earlier ut task
 5) test plans or test specifications
Give paths or 'none'."
Also check yourself: `ls AGENTS.md CLAUDE.md README* docs doc 2>/dev/null`.

For each source:
1. Add a row to KB section 1.
2. Read only headings and the parts about in-scope modules.
3. Write at most 10 lines per module into KB section 6, each ending with `(source: <path>)`.
Never copy large text. Link it.

## Step 3 — Code map (in-scope part only)
For each in-scope source directory:
```sh
find <code path> -name '*.c' -o -name '*.cpp' -o -name '*.h' | head -50
```
Pair every source file with its tests and mocks by name, then by grep:
```sh
grep -rl '<module_name>' <test paths> <mock paths> | head
```
Fill KB section 2. A source file with no test gets `no tests` in the Test files column.

## Step 4 — Infer conventions
Pick samples:
```sh
git log -n 30 --name-only --pretty=format: -- <test paths> | sort | uniq -c | sort -rn | head
```
Read 3 test files (different modules, recently edited), 1–2 mock/stub files and the file that
registers tests in the build (CMakeLists.txt, Makefile, project.yml, Parasoft project).
Fill every row of KB section 3 with a value and an example `file:line`.
Fill KB section 4 from what you see (indentation, naming, braces, comment headers).

## Step 5 — Confirm with the user
Show KB section 3 as a table. Ask: "Are these your test conventions? Correct anything wrong."
Apply corrections. Write `Confirmed by user on <date>`.
Ask: "Any rules I cannot see in the code? (e.g. one assert per test, requirement IDs in comments, forbidden APIs)"
Record answers in section 3 or 4.

## Finish
Tick phase 2 in status.md, set `Current phase: 3`, add a Log line.
