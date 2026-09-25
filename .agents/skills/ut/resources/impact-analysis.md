# Impact analysis: one code item → tests and mocks (fills the work-item columns)

For each row `F` (file `S`):
```sh
"$I" tests "$GD" F        # existing tests reaching F      → column "Existing tests"
"$I" deps  "$GD" F        # what F needs mocked            → column "Mocks affected"
"$I" defs  "$GD" F        # mocks / fakes / overloads named F
```
Signature or behaviour changes also hit F's callers: `"$I" refs "$GD" F` → their tests may mock F.
(`I="$SKILL_DIR/resources/scripts/index.sh"; GD="$KB_DIR/index"`)

| Change kind | Tests calling F | Mocks/stubs of F | New work |
|-------------|-----------------|------------------|----------|
| added | none | none | D new tests; C a mock if other modules' tests need F |
| modified-logic | B re-check expectations | C only if the contract changed | D tests for new branches |
| signature | B update calls | C update every mock of F (else build breaks) | |
| deleted | A remove (ask) | A remove (ask) | check shared mocks first |
| moved/renamed | B includes/names | C names | E build registration |
| type/macro | B tests that use the type | C mocks returning it | D new enum values / fields |
| new-dependency | B tests of F need the new mock | C create it | E link errors until it exists |
| targeted | review | review | D or G as requested |

Easy to miss: a header change hits every includer; a new `#define` limit moves boundary values; a new error return
needs a mock returning it in callers' tests; generated mocks (CMock `mock_*.c`, Parasoft stubs) are regenerated,
not edited; test code already changed on the branch is not redone.
