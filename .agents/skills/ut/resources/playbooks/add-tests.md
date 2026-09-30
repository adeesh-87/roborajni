# Playbook: add-tests
1. Read the card of each function in `Inputs` and its code: `index.sh source "$KB_DIR/index" <function>` (not the whole
   file). Read `exemplars/test.md`. Other code you need: `index.sh refs|defs|find` (`resources/graph-queries.md`).
2. The task file's `Cases` table is the plan: one test per line. Missing a decision the card lists → add a line.
3. `static` / `private` functions: reach them the way KB `Test seams` → `access` says (default A1: through public
   callers). Dependencies: the card's `Calls` says which are mocked (`(mock file)`), which need a mock (`[function: header]`),
   which are pointers to set. A needed mock that is not in `Touches` → write it down, mark the task PARTIAL at the end.
4. New file or existing file per `Conventions`. Copy the exemplar's includes, group/fixture, setup/teardown.
   Write the tests in `Cases` order; happy path first; build after the first one.
5. New file → register it exactly as `exemplars/register.md` shows.
6. Build, run this file only (single-test command). Fix, max 3 attempts per error (`tools/errors/<tool>.md`).
7. All pass → run the module's whole group. Result: test names added, one per line.
