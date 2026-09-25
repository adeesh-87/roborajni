#!/usr/bin/env bash
# testscan.sh - learn HOW the existing tests are written (bash + grep + awk only).
#
#   testscan.sh OUT_DIR TEST_PATH...        -> OUT_DIR/testscan.md
#
# Counts what the test code actually uses: framework, assertion macros, mock API, fixtures,
# test-name and file-name patterns, includes. Picks exemplar candidates (small, typical, with mocks).
# Facts only; every number is a count over the given paths.
set -u
[ $# -ge 2 ] || { sed -n '2,9p' "$0"; exit 2; }
OUT=$1; shift
mkdir -p "$OUT" || exit 2
LIST="$OUT/.files"
for p in "$@"; do
  if [ -d "$p" ]; then find "$p" -type f \( -name '*.c' -o -name '*.cc' -o -name '*.cpp' -o -name '*.cxx' \) -not -path '*/.git/*'
  elif [ -f "$p" ]; then echo "$p"; fi
done | sort -u > "$LIST.all"
# vendored frameworks are not the user's tests
grep -viE '(^|/)(unity|cmock|cpputest|googletest|gtest|gmock|fff|catch2|doctest|ceedling|vendor|third[_-]?party|external)/' "$LIST.all" > "$LIST"
SKIPPED=$(( $(wc -l < "$LIST.all") - $(wc -l < "$LIST") )); rm -f "$LIST.all"
N=$(wc -l < "$LIST" | tr -d ' ')
[ "$N" -gt 0 ] || { echo "testscan: no C/C++ files under: $*" >&2; rm -f "$LIST"; exit 1; }
FILES=$(tr '\n' ' ' < "$LIST")

cnt() { # cnt REGEX -> total matches over all files
  xargs -d '\n' grep -ohE "$1" < "$LIST" 2>/dev/null | wc -l | tr -d ' '
}
files_with() { xargs -d '\n' grep -lE "$1" < "$LIST" 2>/dev/null | wc -l | tr -d ' '; }
top() { # top REGEX N  -> "count  token" lines
  xargs -d '\n' grep -ohE "$1" < "$LIST" 2>/dev/null | sed -E 's/[[:space:]]*\($//' | sort | uniq -c | sort -rn | head -"$2" | awk '{c=$1; $1=""; sub(/^ +/, ""); printf "  %5d  %s\n", c, $0}'
}

{
echo "# Test code scan"
echo "Generated $(date '+%Y-%m-%d %H:%M') over $N test source files: $*"
[ "$SKIPPED" -gt 0 ] && echo "($SKIPPED files inside vendored framework folders were skipped)"
echo
echo "## Framework (files using it)"
printf '| Framework | Files |\n|---|---|\n'
printf '| CppUTest (CppUTest/TestHarness.h or TEST_GROUP) | %s |\n' "$(files_with 'CppUTest/TestHarness\.h|^[[:space:]]*TEST_GROUP[[:space:]]*\(')"
printf '| GoogleTest (TEST/TEST_F/TEST_P) | %s |\n' "$(files_with 'gtest/gtest\.h')"
printf '| gMock (MOCK_METHOD/EXPECT_CALL) | %s |\n' "$(files_with 'MOCK_METHOD|EXPECT_CALL')"
printf '| Unity (unity.h, RUN_TEST) | %s |\n' "$(files_with '[<"]unity\.h[>"]|RUN_TEST[[:space:]]*\(')"
printf '| CMock (_ExpectAndReturn etc.) | %s |\n' "$(files_with '_(Expect|ExpectAndReturn|IgnoreAndReturn|ExpectAnyArgs)[A-Za-z]*\(')"
printf '| CppUMock (mock().) | %s |\n' "$(files_with 'mock\(\)\.')"
printf '| FFF (FAKE_*_FUNC) | %s |\n' "$(files_with 'FAKE_(VALUE|VOID)_FUNC')"
printf '| Parasoft (CPPTEST_) | %s |\n' "$(files_with 'CPPTEST_')"
printf '| Catch2/doctest (TEST_CASE) | %s |\n' "$(files_with 'TEST_CASE[[:space:]]*\(')"
echo
echo "## Test-case names (how tests are named)"
echo "Sample of real names, then the pattern classes:"
xargs -d '\n' grep -ohE '^[[:space:]]*(TEST|TEST_F|TEST_P|IGNORE_TEST|TYPED_TEST)[[:space:]]*\([^)]*\)|^[[:space:]]*(static[[:space:]]+)?void[[:space:]]+test_[A-Za-z0-9_]+[[:space:]]*\(|RUN_TEST[[:space:]]*\([[:space:]]*[A-Za-z0-9_]+|CPPTEST_TEST[[:space:]]*\([^)]*\)' < "$LIST" 2>/dev/null \
  | sed -E 's/^[[:space:]]*//; s/^static[[:space:]]+//; s/[[:space:]]*\($//; s/^RUN_TEST[[:space:]]*\([[:space:]]*/void /' | sort -u > "$OUT/.names"
NN=$(wc -l < "$OUT/.names" | tr -d ' ')
echo "Total test cases found: $NN"
shuf -n 8 "$OUT/.names" 2>/dev/null | sed 's/^/  /' || head -8 "$OUT/.names" | sed 's/^/  /'
echo
echo "Name pattern classes (2nd macro argument or function name):"
sed -E 's/^(TEST|TEST_F|TEST_P|IGNORE_TEST|TYPED_TEST|CPPTEST_TEST)[[:space:]]*\([^,]*,[[:space:]]*//; s/\)$//; s/^void[[:space:]]+//; s/^TEST[[:space:]]*\(//' "$OUT/.names" \
  | awk '{
      n=$0; und=gsub(/_/,"_",n); up=gsub(/[A-Z]/,"",n)
      if ($0 ~ /^test_/)               c="test_lower_snake";
      else if (und>=2)                 c="Snake_With_Underscores (e.g. Func_Condition_Expected)";
      else if (und==1)                 c="Two_Parts";
      else if ($0 ~ /^[A-Z][a-z]+([A-Z][a-z0-9]+)+$/) c="CamelCase";
      else if ($0 ~ /^[a-z]+[A-Z]/)    c="camelCase";
      else                             c="other";
      cnt[c]++ } END { for (k in cnt) printf "  %5d  %s\n", cnt[k], k }' | sort -rn
echo
echo "## Assertions (top 12)"
top '\b(TEST_ASSERT[A-Z0-9_]*|EXPECT_(EQ|NE|LT|LE|GT|GE|TRUE|FALSE|STREQ|STRNE|STRCASEEQ|FLOAT_EQ|DOUBLE_EQ|NEAR|THAT|THROW|NO_THROW|ANY_THROW|DEATH)|ASSERT_(EQ|NE|LT|LE|GT|GE|TRUE|FALSE|STREQ|STRNE|FLOAT_EQ|DOUBLE_EQ|NEAR|THAT|THROW|NO_THROW|DEATH)|LONGS_EQUAL[A-Z_]*|UNSIGNED_LONGS_EQUAL[A-Z_]*|CHECK_TRUE|CHECK_FALSE|CHECK_EQUAL|CHECK_TEXT|CHECK|STRCMP_EQUAL[A-Z_]*|STRNCMP_EQUAL|MEMCMP_EQUAL|BYTES_EQUAL|BITS_EQUAL|POINTERS_EQUAL|DOUBLES_EQUAL[A-Z_]*|FAIL|CPPTEST_ASSERT[A-Z_]*|REQUIRE|CHECK_THAT)[[:space:]]*\(' 12
echo
echo "## Mock / stub API (top 12)"
top '\b(mock\(\)\.[a-zA-Z]+|EXPECT_CALL|ON_CALL|MOCK_METHOD[0-9]*|NiceMock|StrictMock|[A-Za-z0-9_]+_(ExpectAndReturn|Expect|ExpectAnyArgs|ExpectAnyArgsAndReturn|IgnoreAndReturn|Ignore|IgnoreArg_[a-z_]+|ReturnThruPtr_[a-z_]+|ReturnArrayThruPtr_[a-z_]+|StubWithCallback|AddCallback|Stub)|FAKE_VALUE_FUNC|FAKE_VOID_FUNC|RESET_FAKE|[A-Za-z0-9_]+_fake\.[a-z_]+|CppTest_Stub_[A-Za-z0-9_]+|CPPTEST_REGISTER_STUB_CALLBACK|UT_PTR_SET)[[:space:]]*\(?' 12
echo
echo "## Fixtures and setup"
printf '| Item | Count |\n|---|---|\n'
printf '| CppUTest TEST_GROUP | %s |\n' "$(cnt '^[[:space:]]*TEST_GROUP[[:space:]]*\(')"
printf '| CppUTest setup()/teardown() | %s / %s |\n' "$(cnt '\bvoid[[:space:]]+setup[[:space:]]*\(')" "$(cnt '\bvoid[[:space:]]+teardown[[:space:]]*\(')"
printf '| gtest fixture classes (: public ::testing::Test) | %s |\n' "$(cnt ':[[:space:]]*public[[:space:]]+(::)?testing::Test\b')"
printf '| gtest SetUp()/TearDown() | %s / %s |\n' "$(cnt '\bSetUp[[:space:]]*\([[:space:]]*\)')" "$(cnt '\bTearDown[[:space:]]*\([[:space:]]*\)')"
printf '| Unity setUp()/tearDown() | %s / %s |\n' "$(cnt '\bvoid[[:space:]]+setUp[[:space:]]*\(')" "$(cnt '\bvoid[[:space:]]+tearDown[[:space:]]*\(')"
printf '| mock().checkExpectations() / mock().clear() | %s / %s |\n' "$(cnt 'mock\(\)\.checkExpectations')" "$(cnt 'mock\(\)\.clear')"
printf '| extern "C" blocks around includes | %s |\n' "$(cnt 'extern[[:space:]]*"C"')"
printf '| #include "*.c" (testing statics by including the source) | %s |\n' "$(cnt '#include[[:space:]]*"[^"]*\.c"')"
printf '| IGNORE_TEST / DISABLED_ / TEST_IGNORE | %s |\n' "$(cnt 'IGNORE_TEST|DISABLED_|TEST_IGNORE')"
echo
echo "## File naming"
awk -F/ '{f=$NF; if (f ~ /^test_/) c="test_<name>.<ext>"; else if (f ~ /_test\./) c="<name>_test.<ext>"; else if (f ~ /_tests\./) c="<name>_tests.<ext>"; else if (f ~ /Test\./) c="<name>Test.<ext>"; else if (f ~ /Tests\./) c="<name>Tests.<ext>"; else if (f ~ /[Mm]ock/) c="mock file"; else if (f ~ /[Ss]tub/) c="stub file"; else if (f ~ /[Ff]ake/) c="fake file"; else c="other: " f; cnt[c]++} END {for (k in cnt) printf "  %5d  %s\n", cnt[k], k}' "$LIST" | sort -rn
echo
echo "## Includes most used (top 10)"
top '#include[[:space:]]*[<"][^>"]+[>"]' 10 | sed -E 's/#include[[:space:]]*//'
echo
echo "## Exemplar candidates (typical, small, with mocks)"
echo "Score = uses mocks (+3), 30-200 lines (+2), has fixture (+1), >=3 test cases (+1). Read the top one first."
while IFS= read -r f; do
  l=$(wc -l < "$f" | tr -d ' ')
  t=$(grep -cE '^[[:space:]]*(TEST|TEST_F|TEST_P)[[:space:]]*\(|^[[:space:]]*(static[[:space:]]+)?void[[:space:]]+test_[A-Za-z0-9_]+[[:space:]]*\(|RUN_TEST[[:space:]]*\(|CPPTEST_TEST[[:space:]]*\(' "$f")
  m=$(grep -cE 'mock\(\)\.|EXPECT_CALL|_ExpectAndReturn|_Expect\(|FAKE_(VALUE|VOID)_FUNC|CppTest_Stub|_fake\.' "$f")
  x=$(grep -cE 'TEST_GROUP|::testing::Test|void[[:space:]]+(setUp|setup|SetUp)[[:space:]]*\(' "$f")
  s=0; [ "$m" -gt 0 ] && s=$((s+3)); [ "$l" -ge 30 ] && [ "$l" -le 200 ] && s=$((s+2)); [ "$x" -gt 0 ] && s=$((s+1)); [ "$t" -ge 3 ] && s=$((s+1))
  [ "$t" -gt 0 ] && printf '%d\t%s\t%s lines, %s tests, %s mock uses\n' "$s" "$f" "$l" "$t" "$m"
done < "$LIST" | sort -rn | head -6 | awk -F'\t' '{printf "  score %s  %s  (%s)\n", $1, $2, $3}'
echo
echo "## Mock / stub files"
xargs -d '\n' grep -lE 'mock\(\)\.actualCall|FAKE_(VALUE|VOID)_FUNC|CppTest_Stub_|MOCK_METHOD' < "$LIST" 2>/dev/null | head -10 | sed 's/^/  /'
echo "(CMock generated mocks are not listed: they are generated from headers at build time)"
} > "$OUT/testscan.md"
rm -f "$LIST" "$OUT/.names"
echo "testscan: $N files -> $OUT/testscan.md"
