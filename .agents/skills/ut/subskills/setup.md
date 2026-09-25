# Phase 1 — Setup

Goal: status.md Config complete. The codebase profile (paths, tools, commands) lives in the KB and is
only confirmed here; task policies are asked here.

## A. Detect (no questions yet)
```sh
"$SKILL_DIR/resources/scripts/kb-id.sh" "<repo root>"        # id=..., root=..., remote=...
```
Record `KB dir` = `$SKILL_DIR/resources/kb/<id>` in Config (created in phase 3 if missing).
`<KB dir>/kb.md` exists → read its `Profile` and `Commands` tables. Skip B; go to C.
Otherwise detect from the repo root (keep each output to 20 lines):
```sh
find . -type d \( -iname test -o -iname tests -o -iname 'unittest*' -o -iname ut -o -iname mocks -o -iname stubs -o -iname fakes \) -not -path '*/.git/*' | head -20
"$SKILL_DIR/resources/scripts/testscan.sh" "$TASK/logs/testscan" <test dirs found>      # framework, mocks, names (skip if no test dir)
ls CMakeLists.txt Makefile* makefile* project.yml *.bdf .parasoft .gitlab-ci.yml Jenkinsfile azure-pipelines.yml .github/workflows 2>/dev/null
grep -rnE 'ctest|make .*test|ceedling|cpptestcli|RunAllTests|gtest|--gtest' .gitlab-ci.yml Jenkinsfile azure-pipelines.yml .github/workflows/*.yml *.sh *.bat 2>/dev/null | head -10
find . -name compile_commands.json -not -path '*/.git/*' | head -3
grep -rlE -- '--coverage|-fprofile-arcs|ctcwrap|ctc -i|cpptestcc|gcovr|lcov' --include='*[Mm]akefile*' --include='CMakeLists.txt' --include='*.cmake' --include='*.yml' --include='*.sh' . 2>/dev/null | head -5
```
Read `$TASK/logs/testscan/testscan.md` sections `Framework` and `Mock / stub API` only.

## B. Fill the profile draft
Write into a table (it goes to KB section `Profile` in phase 3; keep it in status.md `Config` until then):
| Row | Value from detection |
|-----|----------------------|
| Code under test paths | dirs with production sources in scope of the request |
| Test paths / mock paths | from find + testscan |
| Test framework / mock style | from testscan (files count per framework) |
| Build system for tests / build & run command | from build files and CI |
| Compile DB (test build) | path or `none` |
| Coverage tool | from grep, else `none` |
| Env before build | anything CI sources or exports, else `none` |
Unknown → write `?`.

## C. Confirm (one message)
Show the profile table (from KB or from B). Then ask:
```
Correct anything wrong in the table (blanks marked ?).
1) Permissions: change production code [no] / delete obsolete tests or mocks [ask each] / commit [no, you commit]
2) Safe to run the build and tests on this machine now? [yes]
3) Docs, design notes or an existing decomposition of this code I should read? [none]
4) Coverage in this task? [no]  If yes: tool, metric and target [from profile, statement 80 %]
```
For a known codebase (KB exists) the message is the same, with the previous answers as defaults.
Record: profile rows → Config; answers 1–4 → Config `Permissions`, `Safe to run`, `Inputs`, `Coverage`;
docs from 3 → context.md section 2. Write `Resources to load` from the table below.

| Profile says | Resources to load |
|--------------|-------------------|
| CppUTest / CppUMock | `tools/cpputest.md` |
| GoogleTest / gMock / FFF | `tools/gtest-gmock.md` |
| Unity / CMock / Ceedling | `tools/unity-cmock.md` |
| Parasoft C/C++test | `tools/parasoft-cpptest.md` |
| Testwell CTC++ | `tools/ctc.md` |
| gcov / lcov / gcovr / llvm-cov | `tools/gcov-lcov.md` |
| CMake / Make / Ceedling / scripts | `tools/build-systems.md` |
| none of the above | write `none: learn from the repo, record in KB Build notes` |
Tick phase 1.
