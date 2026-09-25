# GoogleTest + gMock (+ FFF) — quick reference: errors and fixes
## Errors and fixes
| Message | Fix |
|---------|-----|
| `Uninteresting mock function call` (warning) | NaggyMock default; add EXPECT_CALL or use NiceMock like the repo |
| `Unexpected mock function call` / `Actual function call count doesn't match` | check the path; check matchers and `.Times()` |
| `undefined reference` to C function | `extern "C"` around the C header or the forwarding function |
| `multiple definition of spi_read` | real source and fake both linked |
| `no matching function for call to ... MOCK_METHOD` | wrap types with commas in parentheses: `(std::map<int, int>)` |
| segfault in forwarding function | `g_hal` is null: set it in SetUp |
| `undefined reference to 'spi_read'` from a C object with FFF | fakes defined in a .cpp file without `extern "C" { }` around them |
