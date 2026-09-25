# Asking the code index (load when you need one of these answers)
`I="$SKILL_DIR/resources/scripts/index.sh"; GD="$KB_DIR/index"`. Paths are repo-relative, lines are original.
The same commands work for every backend (clang, gcc, graphify); with the bash fallback (`MODE: codemap`) only
card, deps and tests work. Which backend built the index: `"$I" stats "$GD"` or KB `last_graph_build`.

Ask the index instead of reading or grepping source files: it answers from the compiler's (or tree-sitter's) view,
knows overloads, tests, mocks and call lines, and prints only what you asked for.

| Question | Command | Instead of |
|----------|---------|------------|
| Where is X defined? Functions, tests, types, enum values, macros, globals with "X" in their name | `"$I" find "$GD" 'sensor_(read|init)'` (regex) | `grep -rn X src/` |
| Every definition of one name: overloads, mocks, fakes | `"$I" defs "$GD" sensor_read` | `grep -rn 'sensor_read\s*(' tests/` |
| What is in this file (header too)? | `"$I" list "$GD" src/sensor.c` (types, macros, globals, functions, line ranges) | reading the file |
| The code of one function or test | `"$I" source "$GD" sensor_read` / `"$I" source "$GD" "TEST(Sensor, Read_Timeout)"` / `name@LINE` | reading the file |
| A struct / class / enum / typedef / macro / constant (fields, values) | `"$I" source "$GD" sensor_cfg_t` / `SENSOR_MAX` / `Status::QUEUE_FULL` | reading the header |
| Who calls X, which tests, which pointers, what overrides it | `"$I" refs "$GD" sensor_read` (call lines included) | `grep -rnw sensor_read .` |

| Question | Command |
|----------|---------|
| Everything I need to plan tests for a function or a file | `"$I" card "$GD" sensor_read` / `"$I" card "$GD" src/sensor.c` |
| One overload of a name | `"$I" card "$GD" src/pool.cpp` and pick the card whose line range fits; diagrams take `name@LINE` |
| What must be mocked or stubbed | `"$I" deps "$GD" src/sensor.c` (or a function) |
| Which tests already reach a function (through callers and function pointers) | `"$I" tests "$GD" sensor_read` |
| The branches of a function, with what the last coverage run hit | `"$I" flow "$GD" sensor_read` (Mermaid text, see `resources/diagrams.md`) |
| The calls a function makes, in order, and the test doubles that exist | `"$I" seq "$GD" sensor_read` |
| Which decision outcomes no test takes | `"$I" uncovered "$GD" src/sensor.c` (after `cov-import`) |
| What the tests REALLY call at run time | `"$I" trace "$GD" --run "<test binary>" ...` → `KB_DIR/diagrams/traces/` |
| Callers / callees / references from the compiler's language server | `"$I" lsp "$GD" callers sensor_read` (clangd; interactive) |
| What changed in the code under test and which tests/mocks it hits (the pick-list) | `"$I" impact "$GD" --base origin/main --out "$TASK/impact.md" --context "$TASK/context.md"` |
| Code changed: bring the index, all cards and diagrams up to date, get the delta | `"$I" refresh "$GD"` → `KB_DIR/last-refresh.md` (see `subskills/refresh.md`) |

Card lines: `Decisions` = one test per outcome (loops: 0, 1, many; `?:` both; `switch` every case + default;
`[n sub-conditions]` = each must flip the result alone for MC/DC). `Globals/statics` = reset in setup, check after.
`Calls` with `[function: header]` = mock it; `pure virtual; overridden by X` = an interface, X is an existing double;
`[pointer: may call f]` = set the pointer to a fake in the test or call `f` directly; `static` = reach it through
its callers; `private` / `protected` (clang index) = the same, a test cannot call it. `Tests reaching it at run time (trace)` appears after a trace run: `0` means no test executes it.

`deps` kinds, most important first: `function` (declared in a repo header, defined outside the scan → mock/stub),
`interface` (C++ pure virtual → mock the interface; `implemented by` names existing mocks), `pointer`, `macro`,
`in-scope code` (another scanned file, often an existing mock), `library` (usually not mocked), `test-framework`.
Limits by backend: see `resources/index-backends.md`. Graphify only: `graphify.sh explain|path|query "$KB_DIR/index/graphify" ...`.
