# Asking the code index (load when you need one of these answers)
`I="$SKILL_DIR/resources/scripts/index.sh"; GD="$KB_DIR/index"`. The index is the Graphify graph of this codebase with
the ut fixes. Paths are repo-relative, lines are original.

## Order of looking at code (always; grepping and reading code files are the LAST resort)
1. The card / cards file you were given, and the task file.
2. An index query from the tables below (`source` shows exactly the lines of one function, type or macro).
3. A line range the index named: open only those lines.
4. LAST resort, only when the index says `not in the index` or cannot answer (macro bodies, strings, comments, build
   files, generated mocks): `grep` or reading more of a file. Write one Log line saying which question the index
   could not answer, so the index can be fixed.

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
| Callers and callees drawn from the graph, a call chain from A to B | `graphify.sh explain "$GD/graphify" sensor_read` / `graphify.sh path "$GD/graphify" A B` |
| What changed in the code under test and which tests/mocks it hits (the pick-list) | `"$I" impact "$GD" --base origin/main --out "$TASK/impact.md" --context "$TASK/context.md"` |
| Code changed: bring the index, all cards and diagrams up to date, get the delta | `"$I" refresh "$GD"` → `KB_DIR/last-refresh.md` (see `subskills/refresh.md`) |

Card lines: `Decisions` = one test per outcome (loops: 0, 1, many; `?:` both; `switch` every case + default;
`[n sub-conditions]` = each must flip the result alone for MC/DC). `Globals/statics` = reset in setup, check after.
`Calls` with `[function: header]` = mock it; `pure virtual; overridden by X` = an interface, X is an existing double;
`[pointer: may call f]` = set the pointer to a fake in the test or call `f` directly; `static` = reach it through
its callers; `private` / `protected` = the same, a test cannot call it (or use the project's access workaround: `resources/test-seams.md`). `Tests reaching it at run time (trace)` appears after a trace run: `0` means no test executes it.

`deps` kinds, most important first: `function` (declared in a repo header, defined outside the scan → mock/stub),
`interface` (C++ pure virtual → mock the interface; `implemented by` names existing mocks), `pointer`, `macro`,
`in-scope code` (another scanned file, often an existing mock), `library` (usually not mocked), `test-framework`.
Limits: without a compile DB macros are unexpanded and both sides of every `#if` are present; a method called on a
receiver whose type Graphify cannot resolve links by name only (check with `source` when a card looks wrong); a
function pointer filled from data has no `may call`.
