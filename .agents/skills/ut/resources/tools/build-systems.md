# Build systems for unit tests — quick reference

## Where the real commands are (best source first)
1. CI config: `.gitlab-ci.yml`, `Jenkinsfile`, `.github/workflows/*.yml`, `azure-pipelines.yml`, `bitbucket-pipelines.yml`.
2. Scripts: `build*.sh`, `run_tests*.sh`, `*.bat`, `*.ps1`, `tools/`, `scripts/`, `Makefile` targets.
3. README / docs, KB section 5.
Copy the exact commands, including env setup lines (`source env.sh`, `export ...`, docker run).

## CMake + CTest
```sh
cmake -S <src> -B build -DCMAKE_BUILD_TYPE=Debug [-DBUILD_TESTING=ON or repo option]
cmake --build build -j                           # everything
cmake --build build --target sensor_tests -j     # one test target (faster)
ctest --test-dir build --output-on-failure       # CMake >= 3.20; older: cd build && ctest --output-on-failure
ctest --test-dir build -R Sensor -V              # tests matching regex, verbose
```
- Find test targets: `grep -rn 'add_executable\|add_test\|gtest_discover_tests' --include=CMakeLists.txt --include='*.cmake' .`
- New test file: add it to the same `add_executable(...)`/source list as its neighbours.
- Per-executor build folder: `-B build-E1`. Every executor must configure its own once.
- Toolchain for host tests is often a preset: `cmake --list-presets`, `cmake --preset <name>`.

## Make
```sh
make -C tests -j<n>             # or the target the CI uses: make test / make check / make unittest
make -C tests clean
make -n <target>                # print commands without running (see flags, sources, include paths)
```
- Find test rules: `grep -n '^[a-zA-Z_-]*test[a-zA-Z_-]*:' Makefile* tests/Makefile*`
- CppUTest `MakefileWorker.mk` projects: sources come from `SRC_DIRS`/`SRC_FILES`, tests from
  `TEST_SRC_DIRS`, mocks from `MOCKS_SRC_DIRS`.

## Ceedling
`ceedling test:all`, `ceedling test:<module>`, `ceedling clobber`, config in `project.yml`
(see unity-cmock.md).

## Parasoft project
Built and run by C/C++test itself (IDE or `cpptestcli`); see parasoft-cpptest.md.

## Reading build logs
Always handle the FIRST error; many later errors are consequences.
```sh
grep -nE '(error|Error)[: ]|undefined reference|multiple definition|No such file|cannot find -l' build.log | head -20
```
| Error | Meaning | Usual fix |
|-------|---------|-----------|
| `fatal error: x.h: No such file or directory` | include path missing | add `-I`/`target_include_directories`, or fix the include name |
| `implicit declaration of function` (C) | header not included / renamed | include the header |
| `conflicting types for` / `too few arguments` | prototype changed | update test calls / mocks |
| `undefined reference to 'f'` | f's definition not linked | link the source, a mock or a stub |
| `undefined reference to 'f(int)'` (C++ signature shown) | C function declared without `extern "C"` | wrap C headers in `extern "C" { }` |
| `multiple definition of 'f'` | two definitions linked (real + mock) | remove one from this test target |
| `cannot find -lCppUTest` / `GTest not found` | framework not installed / path not set | ask user: env setup step missing |
| `recipe for target ... failed` | only a summary line | scroll up to the real error |

## Parallel executors and builds
- Shared build folder → two builds at once corrupt it. Lock the folder (and coverage data files) for
  the whole build + run, or give each executor its own folder.
- Make's `-j` is fine inside one executor.
- Do not run `clean` in a shared folder while another executor is building (hold the lock).
