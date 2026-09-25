# Parasoft C/C++test — quick reference: errors and fixes
## Errors and fixes
| Symptom | Fix |
|---------|-----|
| New test does not run | missing `CPPTEST_TEST(name);` line in the class block |
| `undefined reference` to a dependency | add a stub (copy style), or enable auto stubs in the test config |
| Test uses real function instead of stub | stub name/signature does not exactly match; check `CppTest_Stub_` prefix and types |
| static function not visible | suite not `INCLUDED_TO` the source; follow the repo's way |
| License error | environment problem: tell the user, do not retry in a loop |
