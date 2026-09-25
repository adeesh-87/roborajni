# gcov / lcov / gcovr / llvm-cov — quick reference

## GCC coverage (gcov family)
Build the code under test with coverage flags, no optimisation:
```sh
CFLAGS += --coverage -O0 -g      # --coverage = -fprofile-arcs -ftest-coverage (also on link: --coverage)
```
CMake: `target_compile_options(t PRIVATE --coverage -O0)` + `target_link_options(t PRIVATE --coverage)`
(or the repo's COVERAGE option). Compiling creates `*.gcno`; running tests creates/updates `*.gcda`.

Fresh data before each measured run:
```sh
find <build dir> -name '*.gcda' -delete        # or: lcov --zerocounters --directory <build dir>
```

### gcovr (simplest)
```sh
gcovr -r <repo root> <build dir> --filter 'src/' --exclude 'tests/' --txt           # summary table
gcovr -r <repo root> <build dir> --filter 'src/' --txt --txt-metric branch          # branches (newer gcovr, e.g. 7.x)
gcovr -r <repo root> <build dir> --filter 'src/' --html-details -o cov/index.html
gcovr -r <repo root> <build dir> --json-summary cov/summary.json
```
Text output columns: `File  Lines  Exec  Cover  Missing` — `Missing` lists uncovered line numbers.

### lcov + genhtml
```sh
lcov --version                                   # 1.x or 2.x: options differ, see below
# lcov 2.x:
lcov --capture --directory <build dir> --output-file cov.info --rc branch_coverage=1 --ignore-errors mismatch
lcov --remove cov.info '/usr/*' '*/tests/*' '*/mocks/*' -o cov.info --rc branch_coverage=1
# lcov 1.x: same commands with --rc lcov_branch_coverage=1 and without --ignore-errors mismatch
lcov --list cov.info
genhtml cov.info --branch-coverage -o cov_html
```
`--ignore-errors mismatch`: lcov 2.x otherwise stops with `mismatched end line` on test files full of
framework macros (TEST, TEST_F). It only affects test files, not the code under test.
In `cov.info`: `DA:<line>,<count>` (count 0 = uncovered line), `BRDA:<line>,<block>,<branch>,<count>` (`0` or `-` = branch never taken).
```sh
awk -F'[:,]' '/^SF:/{f=$2} /^DA:/ && $3==0 {print f":"$2}' cov.info | head -50                       # uncovered lines
awk -F'[:,]' '/^SF:/{f=$2} /^BRDA:/ && ($5=="0"||$5=="-") {print f":"$2}' cov.info | sort -u | head -50   # lines with an untaken branch
```

### Plain gcov (per file)
```sh
cd <dir with .gcda> && gcov -b -c sensor.c      # writes sensor.c.gcov
grep -n '#####' sensor.c.gcov                    # never executed lines
grep -nE 'branch +[0-9]+ (taken 0( |$)|never executed)' sensor.c.gcov   # untaken branches (with -c; without -c it prints "taken 0%")
```

## Clang source-based coverage (llvm-cov)
```sh
clang -fprofile-instr-generate -fcoverage-mapping ...           # build
LLVM_PROFILE_FILE="tests-%p.profraw" ./tests                    # run
llvm-profdata merge -sparse tests-*.profraw -o tests.profdata
llvm-cov report ./tests -instr-profile=tests.profdata src/       # summary
llvm-cov show   ./tests -instr-profile=tests.profdata src/sensor.c -show-branches=count
```
(Clang can also emit gcov data with `--coverage`; then use `llvm-cov gcov` in place of `gcov`.)


Build or run fails → load `resources/tools/errors/gcov-lcov.md` (error messages and fixes).
