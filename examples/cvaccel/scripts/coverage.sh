#!/usr/bin/env bash
# Coverage build for cvaccel.
#
# Testwell CTC++ is this project's actual coverage tool (instrumentation + MC/DC-capable
# reporting used in the real SoC toolchain). It is not always installed on a dev machine,
# so when `ctcwrap` is missing this script falls back to gcov/gcovr, which gives ordinary
# line/branch coverage as a stand-in with the standard, freely available GNU toolchain.
set -eu

cd "$(dirname "$0")/.."

if command -v ctcwrap >/dev/null 2>&1; then
    echo "== Testwell CTC++ coverage =="
    rm -f MON.dat
    mkdir -p coverage

    # Exclude simulation and test code from instrumentation: we only want coverage of the
    # service (src/) itself.
    ctcwrap -i m -C "EXCLUDE+*/tests/*" -C "EXCLUDE+*/sim/*" \
        cmake -S . -B build-ctc -DBUILD_UNIT_TESTS=ON

    ctcwrap -i m -C "EXCLUDE+*/tests/*" -C "EXCLUDE+*/sim/*" \
        cmake --build build-ctc

    # Run the unit-test binary if the tests subdirectory has produced one.
    ctest --test-dir build-ctc --output-on-failure

    ctcpost MON.sym MON.dat -p coverage/profile.txt
    ctc2html -i coverage/profile.txt -o coverage/CTCHTML
    echo "CTC++ HTML report: coverage/CTCHTML/index.html"
else
    echo "== ctcwrap not found; falling back to gcov/gcovr =="
    mkdir -p coverage

    cmake -S . -B build-cov -DCOVERAGE=ON -DCMAKE_CXX_FLAGS="--coverage -O0" -DBUILD_UNIT_TESTS=ON
    cmake --build build-cov -j

    # Run every registered test (the harness names the binary; ctest does not care)
    ctest --test-dir build-cov --output-on-failure

    gcovr -r . build-cov --filter 'src/' --txt
    gcovr -r . build-cov --filter 'src/' --html-details coverage/index.html
    echo "gcov HTML report: coverage/index.html"
fi
