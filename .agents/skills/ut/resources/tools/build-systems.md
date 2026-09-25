# Build systems for unit tests — quick reference

## Where the real commands are (best source first)
1. CI config: `.gitlab-ci.yml`, `Jenkinsfile`, `.github/workflows/*.yml`, `azure-pipelines.yml`, `bitbucket-pipelines.yml`.
2. Scripts: `build*.sh`, `run_tests*.sh`, `*.bat`, `*.ps1`, `tools/`, `scripts/`, `Makefile` targets.
3. README / docs, KB `Build notes`.
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

## Parallel executors and builds
- Shared build folder → two builds at once corrupt it. Lock the folder (and coverage data files) for
  the whole build + run, or give each executor its own folder.
- Make's `-j` is fine inside one executor.
- Do not run `clean` in a shared folder while another executor is building (hold the lock).

Build fails → load `resources/tools/errors/build-systems.md` (first error, common messages and fixes).
