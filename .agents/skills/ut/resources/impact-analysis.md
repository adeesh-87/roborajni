# Impact analysis: code item → tests and mocks

Use for every row in context.md 3.1. Output: one or more rows in context.md 3.2.
`F` = function or item name, `S` = its source file, `H` = its header.

## 1. Find what touches F
Fast path: the code map (regenerate first if the code changed: see knowledge.md Step 3).
```sh
awk -F'\t' '$3=="F"' "$KB_DIR/codemap/calls.tsv"      # callers of F: tests (TEST(...) names), mocks, production code
awk -F'\t' '$2=="F"' "$KB_DIR/codemap/functions.tsv"  # where F is defined: real source AND mocks/stubs
awk -F'\t' '$1 ~ /S$/ && $2=="F"' "$KB_DIR/codemap/calls.tsv"   # what F calls: dependencies to mock
```
Code graph (if `KB_DIR/graphify` exists; rebuild it first if the code changed):
```sh
G="$SKILL_DIR/resources/scripts/graphify.sh"
"$G" tests   "$KB_DIR/graphify" F      # tests that reach F (directly or through callers)
"$G" deps    "$KB_DIR/graphify" F      # what F calls outside its file: mocks/stubs it needs
"$G" explain "$KB_DIR/graphify" F      # all callers and callees
```
Then confirm with grep (macros and function pointers are invisible to both):
```sh
grep -rnw 'F' <test paths> | head -30                 # tests that call or mention F
grep -rnw 'F' <mock paths> | head -20                 # mocks/stubs that define or fake F
grep -rnE '(mock|expect|Expect|EXPECT_CALL|actualCall|CppTest_Stub|_fake).*F' <test paths> <mock paths> | head
grep -rn  '<S basename without extension>' <test build files> | head   # is S compiled into a test binary?
```
Also find F's callers inside production code when F's behaviour or signature changed:
`grep -rnw 'F' <code paths> | grep -v '^S:' | head`. Callers' tests may mock F.

## 2. Decide the work per change kind
| Change kind | Tests calling F | Mocks/stubs of F | New work |
|-------------|-----------------|------------------|----------|
| added | none yet | none | D: new tests for F. C: mocks for F if other modules' tests need it |
| modified-logic | B: re-check expected values and branches | C: only if F's contract changed | D: tests for new branches |
| signature | B: update calls | C: update every mock/stub of F (else link/compile errors) | — |
| deleted | A: remove tests of F (ask) | A: remove mocks/stubs of F (ask) | check nothing else uses them |
| moved/renamed | B: update includes/names | C: update names | E: build registration may change |
| type/macro | B: tests that build or check that type | C: mocks returning that type | D: new enum values/fields need cases |
| new-dependency | B: tests of F now call a new external → it needs a mock/stub | C: create the mock/stub | E: link errors until it exists |
| targeted (user asked) | review what exists | review | D or G as the user asked |

## 3. Things that are easy to miss
- A header change affects every test that includes the header, not only the tests of F.
- A new `static` function is tested through its public caller (or per KB static-access rule).
- A new `#define` limit or buffer size changes boundary values in existing tests.
- A new error return means callers' tests need a mock that returns it.
- A deleted function may still be referenced by a mock that is shared by other tests: check before deleting.
- Test code already changed on the branch: read it; do not redo it.
- Generated code (e.g. CMock `mock_*.c`, Parasoft generated stubs) is regenerated, not hand-edited.

## 4. Write the row
`| n | S:F | kind | test_file:TEST_NAME, ... | mock_file:F | what to do | A/B/C/D/E/G |`
One row per code item. If there is nothing to do, write `none` and why.
