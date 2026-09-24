# Playbook: fix-build
The test build does not compile or link. Fix test-side code only (production code only if Config allows).
The table of common errors and fixes is in `resources/tools/build-systems.md` and the framework file.

1. Build and save the log. Look at the FIRST error only; later errors are often caused by it.
   ```sh
   grep -nE 'error|undefined reference|multiple definition|No such file|cannot find' <log> | head -5
   ```
2. Classify:
   | Error | Usual cause | Fix |
   |-------|-------------|-----|
   | `No such file or directory` for a header | include path or renamed header | add include path in test build / fix include |
   | `unknown type name`, `was not declared` | missing include, changed name | include the right header / rename |
   | `too few/many arguments`, `conflicting types` | signature changed | update test call or mock prototype |
   | `undefined reference to X` | X not linked: mock missing or source not in test build | add mock/stub or add source to the test target |
   | `multiple definition of X` | real and mock both linked, or two mocks | remove one from the test target |
   | C++ name mangling `undefined reference to X(int)` for a C function | missing `extern "C"` | wrap C includes in `extern "C" { }` |
   | framework macro errors | wrong macro name / include order | see framework tool file |
3. Fix ONE error, rebuild, repeat. Keep a list of what you fixed in the task file.
4. Max 3 attempts on the same error. Then BLOCKED with the exact error text.
5. When it builds: run all tests once to see the new baseline; write failing tests to the task Result
   (they are fix-run work, not this task).
6. Record new build knowledge in KB section 5.
