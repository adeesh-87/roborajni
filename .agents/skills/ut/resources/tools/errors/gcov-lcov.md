# gcov / lcov / gcovr / llvm-cov — quick reference: errors and fixes
## Problems
| Symptom | Fix |
|---------|-----|
| `version mismatch` / `cannot open notes file` | gcov tool must match the compiler: `gcov-11` for gcc-11; for clang use `llvm-cov gcov` (gcovr `--gcov-executable`) |
| 0 % everywhere | test binary not built with `--coverage`, or report run on a different build dir |
| numbers include tests/mocks | add `--filter`/`--exclude` (gcovr) or `lcov --remove` |
| stale or doubled numbers | delete `*.gcda` before running |
| branches on lines with no visible decision | compiler-generated branches (C++ exceptions, inlines): gcovr `--exclude-throw-branches` / `--exclude-unreachable-branches` |
| lcov `mismatched end line` error | lcov 2.x: add `--ignore-errors mismatch` |
| `*.gcda` merge errors in parallel runs | each executor needs its own build folder, or lock the build folder |
Exclusion comments (only with user approval): `// LCOV_EXCL_LINE`, `// LCOV_EXCL_START` ... `// LCOV_EXCL_STOP`
(gcovr also accepts `GCOVR_EXCL_*`).
