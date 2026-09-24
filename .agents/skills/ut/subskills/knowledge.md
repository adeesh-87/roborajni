# Sub-skill: knowledge (phase 2)

Goal: the knowledge base (KB) of THIS codebase exists and has (1) knowledge sources, (2) a code map
of the in-scope code, (3) test conventions confirmed by the user.
KBs live inside the skill, one folder per codebase: `$SKILL_DIR/resources/kb/<codebase-id>/`.

## Step 1 — Identify the codebase and find its KB
```sh
"$SKILL_DIR/resources/scripts/kb-id.sh" "<repo root>"          # prints id=..., root=..., remote=...
cat "$SKILL_DIR/resources/kb/INDEX.md"
```
Set `KB_DIR = $SKILL_DIR/resources/kb/<id>` and `KB = $KB_DIR/kb.md`.
- Check the skill folder is writable: `touch "$SKILL_DIR/resources/kb/.w" && rm "$SKILL_DIR/resources/kb/.w"`.
  Not writable → ask the user for another place [TASK/kb/] and use that as KB_DIR instead.
- `$KB` exists → it is THIS codebase's KB. Read only sections 0, 1, 3 and 7. Add the current root to
  `Roots seen` (section 0 and INDEX.md) if it is new.
  Ask: "The knowledge base for <id> exists (last updated <date>). Refresh conventions or code map? [no]"
  No → go to Step 2 to add new sources only, then Step 6.
- `$KB` does not exist →
  ```sh
  mkdir -p "$KB_DIR/codemap" "$KB_DIR/decompositions"
  cp "$SKILL_DIR/resources/templates/kb.md" "$KB"
  ```
  Fill section 0 (id, remote, root). Add a row to `resources/kb/INDEX.md`.
  Ask: "Is there a knowledge base for this codebase somewhere else (older ut task, other machine)? [no]"
  If yes, copy its content into the new sections.
Record `KB path` in status.md Config. Never open a KB folder with a different id.

## Step 2 — Existing knowledge from people or tools
Ask:
"Has anything already documented or decomposed this codebase? For example:
 1) architecture or design docs, requirement specs, test specifications
 2) AGENTS.md, CLAUDE.md, README, CONTRIBUTING, docs/ folder
 3) output of analysis or agentic tools: code maps, repo wikis, call graphs, module summaries,
    Doxygen, cscope/ctags databases, Understand or similar reports
 4) notes written earlier by a model or a person
Give paths or 'none'."
Also check yourself: `ls AGENTS.md CLAUDE.md README* docs doc "$KB_DIR/decompositions" 2>/dev/null`.
For each source: add a row to KB section 1, read only headings and the parts about in-scope modules,
write at most 10 lines per module into KB section 6, each ending with `(source: <path>)`. Link, never copy.

## Step 3 — Knowledge graph with Graphify (first choice when no decomposition exists)
Do this step when Step 2 found no decomposition of the in-scope code. If one exists, ask
"Also build a code graph? It takes a minute and helps navigation. [yes]".
The skill bundles a pinned Graphify (`resources/vendor/graphify/`) plus C/C++ fixes (`graphify_ut.py`).
Everything runs locally; the wrapper removes LLM keys, so nothing leaves the machine.
```sh
G="$SKILL_DIR/resources/scripts/graphify.sh"; GD="$KB_DIR/graphify"
"$G" setup        # once per machine: needs Python 3.10+ and a package index (or an offline wheelhouse)
"$G" selftest     # once per machine: checks the C/C++ fixes with the local compiler; report any FAIL to the user
# with the compile DB recorded in status.md section 3 (best):
"$G" build --cdb <compile_commands.json> "$GD" <code paths> <test paths> <mock paths>
# without one:
"$G" build "$GD" <code paths> <test paths> <mock paths>
```
- `setup` fails (no Python 3.10+, no network, no index): tell the user the exact error and point to
  `resources/vendor/graphify/README.md` (offline wheelhouse). Use Step 3b instead. Record in KB section 5.
- Output lines to check: `preprocessed with compile flags: N translation units` (compile DB used) and
  `augmented: ...` (fixes applied). `not preprocessed` lines and syntax-error warnings name files that are
  only partly in the graph: record them in KB section 5.
- Without a compile DB, macros are not expanded and BOTH sides of every `#if` are in the graph.
What the graph gives you (paths are repo-relative, lines are original source lines):
```sh
"$G" deps    "$GD" src/sensor.c          # what a file or function calls outside itself: mock/stub candidates
"$G" tests   "$GD" sensor_read           # which TEST blocks / test functions reach it (3 call hops)
"$G" explain "$GD" "sensor_read"         # definition, callers, callees
"$G" path    "$GD" "app_main" "sensor_read"   # call chain from A to B
"$G" query   "$GD" "what calls sensor_read" --budget 800
```
`deps` kinds, most important first:
- `function`: declared in a repo header, defined outside the scan: mock or stub it.
- `interface`: C++ pure virtual method: mock the interface (gMock / fake class); `implemented by` names existing mocks.
- `pointer`: called through a variable or struct member (callbacks, driver ops tables, hooks); `may call` lists the
  functions stored in it (from initializers, assignments, or a registration call such as `set_callback(fn)`).
  In a test, set the pointer to a fake, or call the target directly.
- `macro`, `in-scope code` (another scanned file, often an existing mock), `library` (C/C++ library, usually
  not mocked), `test-framework`.
Also in the graph: `static: true` on static functions (also via `STATIC`/`PRIVATE` macros); C++ methods named
`Class::method()` at their definition (`declared_at` = header line); `obj.method()` calls resolved by the declared
type of `obj` (local, parameter or class field, incl. base classes); every `TEST(...)`, `TEST_F(...)`,
`TEST_GROUP(...)` block is its own node. `tests` follows calls through function pointers too.
Known limits: without a compile DB, macros are not expanded and both sides of every `#if` are present; a pointer
filled at run time from data (not from a function name) has no `may call`; templates and `auto` receivers are
only resolved when the method name is unique.
Read `$GD/out/GRAPH_REPORT.md` (overview of main modules and most connected functions, regenerated after the
fixes). Add a row for the graph to KB section 1 and 3-5 lines to KB section 6.

## Step 3b — Code map (fallback, and quick per-file tables)
Run it when Graphify could not be set up; otherwise it is optional (it needs only bash + awk):
```sh
"$SKILL_DIR/resources/scripts/codemap.sh" "$KB_DIR/codemap" <code paths> <test paths> <mock paths>
```
It writes `summary.md` (per file: functions, calls, external dependencies = mock/stub candidates),
`functions.tsv`, `calls.tsv`, `includes.tsv`, `externals.tsv`. It is a heuristic: confirm in the code.
Read only what you need, e.g. one file's part: `grep -A40 '^### src/sensor.c' "$KB_DIR/codemap/summary.md"`.
Useful queries:
```sh
awk -F'\t' '$3=="sensor_read"' "$KB_DIR/codemap/calls.tsv"            # who calls sensor_read, incl. each TEST(...)
awk -F'\t' '$5!="external" && $5!="macro" && $1!=$5 {print $1" -> "$5}' "$KB_DIR/codemap/calls.tsv" | sort | uniq -c   # file dependencies
```
Record in KB section 0 the date, paths and mode (compile DB or not) of the graph and/or code map. Rebuild when
the code changed a lot (seconds to a minute).

## Step 4 — Deeper decomposition when none exists
If Step 2 found no module-level notes for the in-scope code, count the work:
`wc -l < "$KB_DIR/codemap/functions.tsv"`.
Ask (recommend 2 when more than ~150 functions, or the code has state machines, RTOS/ISR logic,
protocol parsing or complex error handling):
"No explanation of this code exists yet. I built a code graph and a code map. Options:
 1) Continue with those only; I learn the logic while working. [default for small scopes]
 2) You run a stronger model once with a prepared request; it writes module notes into the KB that I
    and later tasks reuse. I can continue meanwhile and pick the notes up when they appear.
 3) You have another tool's output (Doxygen with call graphs, cscope, clangd index, Understand...):
    give me the path.
 4) Skip."
Option 2: copy `resources/templates/decompose-codebase.md` to `TASK/decompose-codebase.md`, replace
`<KB_DIR>` and `<MODULES / PATHS>`, and tell the user which file to give to the stronger model.
Add to status.md `Next steps`: "read KB decompositions/ when present". Do not wait unless the user asks.

## Step 5 — Code map table and conventions
1. Fill KB section 2 from the graph (`deps` per source file, `tests` for key functions) or the code map:
   one row per module, pairing each source file with its test and mock files. A source file with no test gets `no tests`.
2. Pick samples: `git log -n 30 --name-only --pretty=format: -- <test paths> | sort | uniq -c | sort -rn | head`.
   Read 3 test files (different modules, recently edited), 1–2 mock/stub files and the file that registers
   tests in the build (CMakeLists.txt, Makefile, project.yml, Parasoft project).
3. Fill every row of KB section 3 with a value and an example `file:line`, and section 4 from what you see.

## Step 6 — Confirm with the user
Show KB section 3 as a table. Ask: "Are these your test conventions? Correct anything wrong."
Apply corrections. Write `Confirmed by user on <date>`.
Ask: "Any rules I cannot see in the code? (e.g. one assert per test, requirement IDs in comments, forbidden APIs)"
Record answers in section 3 or 4. Update `Last updated` in the KB and INDEX.md.

## Finish
Tick phase 2 in status.md, set `Current phase: 3`, add a Log line.
