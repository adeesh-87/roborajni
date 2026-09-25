# Asking the code graph (load when you need one of these answers)
`G="$SKILL_DIR/resources/scripts/graphify.sh"; GD="$KB_DIR/graphify"`. Paths are repo-relative, lines are original.
Works the same when the bash fallback is in use (`MODE: codemap`), except `explain`/`path`/`query`.

| Question | Command |
|----------|---------|
| Everything I need to plan tests for a function or a file | `"$G" card "$GD" sensor_read` / `"$G" card "$GD" src/sensor.c` |
| What must be mocked or stubbed | `"$G" deps "$GD" src/sensor.c` (or a function) |
| Which tests already reach a function (through callers and function pointers) | `"$G" tests "$GD" sensor_read` |
| Callers and callees of one function | `"$G" explain "$GD" sensor_read` |
| Call chain from A to B | `"$G" path "$GD" app_main sensor_read` |

Card lines: `Decisions` = one test per outcome (loops: 0, 1, many; `?:` both; `switch` every case + default;
`[n sub-conditions]` = each must flip the result alone for MC/DC). `Globals/statics` = reset in setup, check after.
`Calls` with `[function: header]` = mock it; `[pointer: may call f]` = set the pointer to a fake in the test or
call `f` directly; `(mock file)` = a mock exists; `static` = reach it through its callers.

`deps` kinds, most important first: `function` (declared in a repo header, defined outside the scan → mock/stub),
`interface` (C++ pure virtual → mock the interface; `implemented by` names existing mocks), `pointer`, `macro`,
`in-scope code` (another scanned file, often an existing mock), `library` (usually not mocked), `test-framework`.
Limits: without a compile DB macros are unexpanded and both sides of every `#if` are present; a pointer filled from
data has no `may call`; templates and `auto` receivers resolve only when the method name is unique.
