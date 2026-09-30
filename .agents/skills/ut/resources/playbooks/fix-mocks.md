# Playbook: fix-mocks
0. `"$I" deps "$GD" <source file>`: `interface … implemented by MockX` = C++ mock exists; `pointer … may call f` =
   the test can swap the pointer; `in-scope code` in a mock folder = link-time mock exists; `function` = missing.
1. Use the repo's one mock style (`exemplars/mock.md`, Conventions) and its recorded seams (KB `Test seams`:
   `replace`, `per-test`, `hardware`). Never mix a second style or technique in. Mock in one test, real in another →
   the `per-test` technique only (e.g. C2 linker wrap, C1 UT_PTR_SET); undecided → ask, do not pick.
2. Generated mocks (CMock `mock_*.c`, Parasoft stubs): never hand-edit; regenerate from the header / config.
3. Signature change → copy the new prototype from the header exactly (const, pointer levels) into the mock.
4. New mock → copy the exemplar mock: records/checks inputs, returns a settable value, writes out-parameters.
5. One definition per function per test binary: `"$I" defs "$GD" <name>` lists every definition, mocks and fakes
   included (two in one binary → "multiple definition"). Generated mocks are not indexed: check `mock_*.c` by name.
6. Build every binary that links the mock; run their tests. Fix expectations only if the new behaviour is right.
7. Result: mock functions added/changed/removed and the binaries using them.
