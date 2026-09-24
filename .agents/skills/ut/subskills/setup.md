# Sub-skill: setup (phase 1)

Goal: every row of the Config table in TASK/status.md has a value the user confirmed.

## A. Look first, then ask
Find facts yourself so every question can show a default. Run from the repo root.
Do not print long outputs; keep the first 20 lines.
```sh
git rev-parse --show-toplevel                                   # repo root
find . -type d \( -iname test -o -iname tests -o -iname 'unittest*' -o -iname ut -o -iname mocks -o -iname stubs \) -not -path '*/.git/*' | head -20
grep -rlE 'CppUTest/TestHarness.h|CppUTestExt/MockSupport.h' --include='*.c*' . | head -5   # CppUTest
grep -rlE 'gtest/gtest.h|gmock/gmock.h|fff.h' --include='*.c*' --include='*.h*' . | head -5  # GoogleTest / FFF
grep -rlE '"unity.h"|<unity.h>|"mock_' --include='*.c' . | head -5                          # Unity / CMock
grep -rlE 'cpptest.h|CPPTEST_TEST' --include='*.c*' . | head -5                              # Parasoft
ls CMakeLists.txt Makefile* makefile* project.yml *.bdf .parasoft 2>/dev/null
ls .gitlab-ci.yml Jenkinsfile azure-pipelines.yml .github/workflows 2>/dev/null
grep -rlE -- '--coverage|-fprofile-arcs|ctcwrap|ctc -i|cpptestcc|gcovr|lcov' --include='*[Mm]akefile*' --include='*.cmake' --include='CMakeLists.txt' --include='*.yml' --include='*.sh' --include='*.bat' . | head -10
```

## B. Ask in 4 rounds
After EACH round, record the answers in Config before asking the next round.

Round 1 — code and tests
1. Repo root [found value]
2. Path(s) of the code under test [guess]
3. Path(s) of the test code [guess]
4. Path(s) of mocks / stubs / fakes [guess]
5. Language, standard, compiler / toolchain; do tests run on host, simulator or target?

Round 2 — tools
1. Test framework [guess]: CppUTest, GoogleTest, Unity, Parasoft C/C++test, other
2. Mocking: CppUMock, gMock, FFF, CMock, Parasoft stubs, hand-written stubs, link-time substitution
3. Build system for tests [guess]: CMake, Make, Ceedling, Parasoft project, IDE, script
4. How do you build and run the tests today? Command, script, or CI job name. ["I will look in CI files"]
5. Anything needed before building: env script to source, license server, docker, VPN?

Round 3 — coverage
1. Do you want coverage measured or improved in this task? [no]
If yes:
2. Tool [guess]: Testwell CTC++, gcov/lcov/gcovr, Parasoft, llvm-cov, other
3. Metric and target: statement / line, decision / branch, condition, MC/DC, function; target %
4. Where are reports today and how are they made? (command, script, CI artifact, "don't know")
5. Files or code to exclude from coverage (tests, mocks, generated code)?

Round 4 — rules
1. May I change production code? [no — I only report suspected bugs]
2. May I delete tests or mocks? [ask each time]
3. Commit policy [never — you commit]
4. Coding standard or style rules for test code? [same as existing tests]
5. The knowledge base is kept per codebase inside this skill (`resources/kb/<codebase-id>/`), so later
   tasks on the same repo reuse it. OK? [yes] (phase 2 finds or creates it)

## C. Fill `Resources to load`
Write the resource file names that match Config (see the table in SKILL.md). Always add
`resources/test-design.md`. Add `resources/tools/build-systems.md` when the build is CMake,
Make, Ceedling or a script. Example:
`resources/tools/cpputest.md, resources/tools/ctc.md, resources/tools/build-systems.md, resources/test-design.md`
If a tool has no resource file, write `none for <tool> — learn from repo and record in KB section 5`.

## D. Confirm
Show the Config table to the user. Ask: "Is this correct?" Fix what they say.
Leave `Parallel executors` as `decide at plan` if the user does not know yet.
Tick phase 1 in status.md, set `Current phase: 2`, add a Log line. Done.
