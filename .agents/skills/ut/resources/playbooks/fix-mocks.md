# Playbook: fix-mocks
Create, update or delete mocks, stubs or fakes. Load the framework tool file for the exact syntax.

0. Which mocks exist and which are missing for a file: `"$SKILL_DIR/resources/scripts/graphify.sh" deps "$KB_DIR/graphify" <source file>`.
   `interface ... implemented by: MockX` = a C++ mock exists; `pointer ... may call: f` = the test can replace the
   pointer with a fake; `in-scope code` in a mocks folder = a link-time mock exists.
1. Find how this repo mocks (KB section 3 "Mock / stub style"): framework mocks (CppUMock, gMock,
   CMock, Parasoft stubs), hand-written stubs, FFF fakes, link-time substitution or function pointers.
   Use the same way. Never mix a second style into a file.
2. Generated mocks (CMock `mock_*.c`, Parasoft auto stubs): do NOT hand-edit. Regenerate by building,
   or change the source header / generator config.
3. Signature changed: update the mock's parameter list, return type and every parameter it records or
   checks. Copy the new prototype from the header exactly (qualifiers `const`, pointer levels).
4. New mock: copy an existing mock of a similar function in the same file/folder and adapt.
   It must: record/check input parameters, return a controllable value, write out-parameters.
5. Only one definition of each function may be linked into a test binary. Check with
   `grep -rn '<return type>.*\b<name>\s*(' <mock paths> <test paths>` that there is no duplicate
   (duplicate → "multiple definition" link error).
6. Build every test binary that links this mock (a shared mock affects many tests).
7. Run those tests. Tests failing now because the mock behaves differently → fix their expectations
   only if the new behaviour is correct.
8. Result: mock functions added / changed / removed, and which test binaries use them.
