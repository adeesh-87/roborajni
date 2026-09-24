# Playbook: add-tests
New tests for functions or behaviour that have none. Read `resources/test-design.md` first.

1. Read the function(s) under test fully, and the header that declares them.
2. Open the test file to imitate (task Inputs). Decide: add to an existing test file or create one?
   Follow KB section 3: usually one test file per source file.
3. Write the case table (test-design.md) into the task file under Steps. Keep it short.
4. List the dependencies the function calls: `"$SKILL_DIR/resources/scripts/graphify.sh" deps "$KB_DIR/graphify" <function>`
   (or the code map: `grep -A40 '^### <file>' "$KB_DIR/codemap/summary.md"`). Confirm in the code.
   `in-scope code` in a mock folder = a mock already exists. For each other dependency: does a mock/stub exist?
   - Yes → use it as other tests do.
   - No → if it is in Touches, create it following the mock style in KB; otherwise record as
     needed work and mark the task PARTIAL at the end.
5. Write the tests, one per case row. Start with the simplest (happy path) and build it right away.
6. New file → register it in the build (CMakeLists.txt / Makefile / project.yml / Parasoft project),
   exactly like the neighbouring files are registered.
7. Build, run only these tests (single-test command). Fix, max 3 attempts per error.
8. All pass → run the whole test group of this module to see you broke nothing.
9. Result: list test names added, one line each.
