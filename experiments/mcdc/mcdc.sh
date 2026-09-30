#!/bin/bash
# Build the unit tests with clang 18 MC/DC instrumentation, run them, and print the MC/DC gaps of src/.
# MCDC_VIEW=suggest : the ut index's gap list (condition values of the test that completes each pair)
# MCDC_VIEW=raw     : llvm-cov show -show-mcdc blocks of the decisions below 100%
cd "$(dirname "$0")"
ROOT=$PWD; B=$ROOT/build-mcdc; S=${UT_SCRIPTS:?}
if [ ! -f "$B/build.ninja" ]; then
  mkdir -p "$B" && (cd "$B" && CC=clang CXX=clang++ cmake -G Ninja -DBUILD_UNIT_TESTS=ON \
    -DCMAKE_CXX_FLAGS="-O0 -fprofile-instr-generate -fcoverage-mapping -fcoverage-mcdc" .. > /dev/null) || exit 1
fi
if ! ninja -C "$B" unit_tests > "$B/build.log" 2>&1; then
  echo "BUILD FAILED"; grep -E "error" "$B/build.log" | head -30; exit 1; fi
rm -f "$B"/*.profraw
LLVM_PROFILE_FILE="$B/ut-%p.profraw" "$B/tests/unit_tests" > "$B/run.log" 2>&1; rc=$?
grep -E "^(OK|Errors) \(" "$B/run.log" || tail -3 "$B/run.log"; [ $rc -eq 0 ] || { grep -A3 "Failure in" "$B/run.log" | head -30; }
llvm-profdata merge -sparse "$B"/*.profraw -o "$B/ut.profdata" || exit 1
if [ "${MCDC_VIEW:-suggest}" = suggest ]; then
  [ -f "$ROOT/.ix/index.json" ] || "$S/index.sh" build --cdb "$B/compile_commands.json" "$ROOT/.ix" include src client/include client/src > /dev/null
  "$S/index.sh" cov-import "$ROOT/.ix" --llvm "$B/ut.profdata" --object "$B/tests/unit_tests" | grep "MC/DC"
  "$S/index.sh" uncovered "$ROOT/.ix" | grep -E "^- " | grep "MC/DC" | grep "src/" \
    | python3 -c "import sys,re
for l in sys.stdin:
    head, _, rest = l.partition('): ')
    for g in rest.split('; '):
        if 'MC/DC' in g: print(head + '): ' + g.strip())"
else
  llvm-cov report "$B/tests/unit_tests" -instr-profile="$B/ut.profdata" -show-mcdc-summary "$ROOT"/src/*.cpp | tail -1 | awk '{print "MC/DC of src/: " $(NF-2) " conditions, " $(NF-1) " not shown independent, " $NF " covered"}'
  for f in "$ROOT"/src/*.cpp; do
    llvm-cov show "$B/tests/unit_tests" -instr-profile="$B/ut.profdata" -show-mcdc "$f" \
      | python3 -c "import sys
lines = sys.stdin.read().split('\n'); out=[]; i=0; src=''
while i < len(lines):
    l = lines[i]
    if '|---> MC/DC Decision Region' in l:
        blk=[]
        while i < len(lines) and 'MC/DC Coverage for Decision' not in lines[i]: blk.append(lines[i]); i+=1
        if i < len(lines): blk.append(lines[i])
        if '100.00%' not in blk[-1]: out.append(src); out += blk
    elif l[:10].strip().isdigit() or '|' in l[:8] and l.split('|')[0].strip().isdigit(): src = l
    i += 1
if out: print('== $(basename $f)'); print('\n'.join(out))"
  done
fi
exit $rc
