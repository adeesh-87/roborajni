# Sub-skill: build-run (phase 4)

Goal: working, recorded commands for build, run (and coverage if wanted), plus a baseline:
what builds and what passes BEFORE we change anything.

Load `resources/tools/build-systems.md` and the framework file from Config `Resources to load`.

## Step 1 — Find the commands
Sources, best first:
1. What the user said in setup (Config).
2. CI files: `.gitlab-ci.yml`, `Jenkinsfile`, `.github/workflows/*.yml`, `azure-pipelines.yml`.
3. Scripts: `grep -rlE 'ctest|make .*test|ceedling|cpptestcli|RunAllTests|gtest' --include='*.sh' --include='*.bat' --include='*.py' . | head`
4. README / docs / KB section 5.
Write the candidate commands in TASK/status.md section 3 with `Verified on` empty.

## Step 2 — Confirm before running
Show the commands. Ask:
1. "Are these right? Anything to source or start first?"
2. "Is it safe to run them here? (no hardware flashing, no deploy, no shared outputs overwritten)"
3. "How long does a full build take? [a few minutes]"
4. "Can each executor use its own build folder (e.g. `build-E1`)? [ask again at plan]"
Do not run anything the user has not confirmed.

## Step 3 — Build
```sh
<env setup> && <build command> > "$TASK/logs/build-baseline.log" 2>&1; echo "exit=$?"
```
If exit is not 0:
```sh
grep -nE 'error|Error|ERROR|undefined reference|multiple definition|No such file' "$TASK/logs/build-baseline.log" | head -30
```
Write each distinct problem in context.md section 4 (problem, `log:line`, likely cause).
Do not fix anything now. Fixing is planned work (category E).
If the build cannot start at all (tool missing, license, wrong command): ask the user to fix
the environment or give the right command. Retry. Record the fix in KB section 5.

## Step 4 — Run tests
Only if the build produced a test executable.
```sh
<run command> > "$TASK/logs/run-baseline.log" 2>&1; echo "exit=$?"
```
Read the summary line (the framework file tells you its format). Record in status.md section 4:
total, passed, failed, crashed or timed out. Each failing test → context.md section 4.
A crash (segfault, abort) with no summary → context.md section 4 as "run crashed after <last test name>".

## Step 5 — Single-test command
Find and verify the command to run one group or one test (filter flag from the framework file).
Executors use it for fast feedback. Record it.

## Step 5b — Compile database of the TEST build (makes the code graph accurate)
A `compile_commands.json` lists the exact compiler flags of every file. The code graph uses it to expand
macros and keep only the active `#if` branches, exactly as the test build sees them.
1. Look for one: `find . -name compile_commands.json -not -path './.git/*' | head`
   It must come from the build that compiles the TESTS (host build), not the target firmware build.
2. None found:
   - CMake: add `-DCMAKE_EXPORT_COMPILE_COMMANDS=ON` to the configure command; it appears in the build folder.
   - Make or scripts: `bear -- <build command>` writes it in the current folder (if `bear` is installed; ask).
   - IAR, Keil, Parasoft project builds, other IDEs: usually not available. Skip this step.
   Ask before changing the build command. Never commit the generated file unless the user wants it.
3. Record its absolute path in status.md section 3, row `Compile DB (test build)`. Write `none` if unavailable.

## Step 6 — Coverage commands (only if Config `Coverage wanted` = yes)
Do NOT generate the report yet; phase 6 does that. Only record in section 3 what is known:
coverage build command, report command, report output path. Mark unknown ones `unknown`.

## Step 7 — Lock list for parallel mode
Write under "Paths to lock while building or running" every path that build or run writes
and that other executors would share: build folder, test executable, coverage data files
(`MON.dat`, `*.gcda`, `.clog`), report folder. If each executor gets its own build folder,
write it with the placeholder `<EXEC_ID>`, e.g. `build-<EXEC_ID>`.

## Finish
Set `Verified on` for every command you ran successfully. Copy the baseline problems into
context.md section 5 as candidate rows (E = build, F = run). Tick phase 4, add a Log line.
