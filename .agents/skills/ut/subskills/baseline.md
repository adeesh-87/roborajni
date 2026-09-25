# Phase 2 — Baseline

Goal: verified build / run / single-test commands (in the KB, reused by every later task) and the state
before any change. Load `resources/tools/build-systems.md` and the framework file from `Resources to load`.

## 1. Commands
KB `Commands` table has rows with `Verified on` → reuse them; go to 3.
Otherwise build the table from Config (CI command, build system). Unknown build command → Ask once:
"How do you build and run the unit tests? (command, script or CI job) [I will try: <best guess>]".
Rows: Env setup, Clean, Build tests, Run all tests, Run one group/test, Compile DB, Coverage build, Coverage report.

## 2. Compile database of the TEST build
The graph (phase 3) needs it to expand macros and pick the active `#if` branches.
- Found in setup → record its path.
- CMake without one → add `-DCMAKE_EXPORT_COMPILE_COMMANDS=ON` to the configure command (a flag, not a code change).
- Make/scripts → `bear -- <build command>` if `bear` exists. Otherwise record `none`.
Never commit the generated file.

## 3. Build and run
Config `Safe to run` must be yes. Run from the repo root; keep logs in `$TASK/logs/`:
```sh
<env setup> ; <build> > "$TASK/logs/build-baseline.log" 2>&1; echo "exit=$?"
<run all>              > "$TASK/logs/run-baseline.log"   2>&1; echo "exit=$?"
```
- Build fails → `grep -nE '(error|Error)[: ]|undefined reference|multiple definition|No such file' <log> | head -20`.
  Record each distinct problem in context.md section 4. Do not fix now (it becomes work item category E).
  Tool missing / license / wrong command → Ask the user for the fix, retry once.
- Run: read the summary line (format in the framework file). Record total / passed / failed / crashed in
  status.md `Baseline`. Failing tests → context.md section 4 (category F).
- Verify the single-test command on one existing test (filter flag from the framework file).

## 4. No tests yet?
- No test directory, no test binary, no framework detected → status.md `Baseline`: `Tests: none (greenfield)`.
  Phase 6 (pilot) will set up the first test with the user. Continue.
- Tests exist but the build has no target for the in-scope module → note it; phase 5 decides the pilot.

## 5. Record
Write every command that worked into the KB `Commands` table with `Verified on <date>` (create the KB
skeleton now if phase 3 has not run: `mkdir -p "$KB_DIR" && cp "$SKILL_DIR/resources/templates/kb.md" "$KB"`),
including the paths that a build writes (build folder, test binary, coverage data) under `Paths written by build`.
Task-specific overrides (e.g. a build folder per executor) go to status.md `Baseline`. Tick phase 2.
