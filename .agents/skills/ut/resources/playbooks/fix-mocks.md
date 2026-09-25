# Playbook: fix-mocks
0. `"$G" deps "$GD" <source file>`: `interface … implemented by MockX` = C++ mock exists; `pointer … may call f` =
   the test can swap the pointer; `in-scope code` in a mock folder = link-time mock exists; `function` = missing.
1. Use the repo's one mock style (`exemplars/mock.md`, Conventions). Never mix a second style into a file.
2. Generated mocks (CMock `mock_*.c`, Parasoft stubs): never hand-edit; regenerate from the header / config.
3. Signature change → copy the new prototype from the header exactly (const, pointer levels) into the mock.
4. New mock → copy the exemplar mock: records/checks inputs, returns a settable value, writes out-parameters.
5. One definition per function per test binary: `grep -rn '\b<name>\s*(' <mock paths> <test paths>` (duplicate → "multiple definition").
6. Build every binary that links the mock; run their tests. Fix expectations only if the new behaviour is right.
7. Result: mock functions added/changed/removed and the binaries using them.
