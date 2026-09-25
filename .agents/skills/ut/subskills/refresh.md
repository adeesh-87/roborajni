# Refresh the knowledge base (any time)

When: the user asks; after the pilot is approved; after every PASSED wave checkpoint; on resume when the code
changed since KB `Identity` → last graph build; before planning if that date is older than the branch's last commit.
It rebuilds the code index with the backend and arguments of the last build, rescans the tests and regenerates every module's cards and the diagrams.
Hand-written notes (`modules/<name>.md`, `exemplars/`, `kb.md`) are never touched by the script.

1. (parallel) `"$LOCK" "$LD" wait $ME 900 "$KB_DIR/index" "$KB_DIR/modules" "$KB_DIR/diagrams" "$KB_DIR/testscan.md" "$KB_DIR/last-refresh.md"`
2. `"$SKILL_DIR/resources/scripts/index.sh" refresh "$KB_DIR/index"`   (seconds to a minute; rebuilds the index with the same backend, regenerates cards and diagrams, prints the delta)
3. Read `$KB_DIR/last-refresh.md`:
   - functions added/removed → new work items in context.md if they are in scope (category D / A); tell the user;
   - a card changed → nothing to do, the executor reads cards fresh; an open task whose card changed → note it in the task file;
   - `could not regenerate` → the file left the scan paths: fix `BUILD_ARGS` by running `build` again with the right paths.
4. KB `Identity` → last graph build date; one Log line `refresh: <n> functions added/removed`. (parallel) release the locks.
