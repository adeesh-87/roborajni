# Build systems: reading build logs
## Reading build logs
Always handle the FIRST error; many later errors are consequences.
```sh
grep -nE '(error|Error)[: ]|undefined reference|multiple definition|No such file|cannot find -l' build.log | head -20
```
| Error | Meaning | Usual fix |
|-------|---------|-----------|
| `fatal error: x.h: No such file or directory` | include path missing | add `-I`/`target_include_directories`, or fix the include name |
| `implicit declaration of function` (C) | header not included / renamed | include the header |
| `conflicting types for` / `too few arguments` | prototype changed | update test calls / mocks |
| `undefined reference to 'f'` | f's definition not linked | link the source, a mock or a stub |
| `undefined reference to 'f(int)'` (C++ signature shown) | C function declared without `extern "C"` | wrap C headers in `extern "C" { }` |
| `multiple definition of 'f'` | two definitions linked (real + mock) | remove one from this test target |
| `cannot find -lCppUTest` / `GTest not found` | framework not installed / path not set | ask user: env setup step missing |
| `recipe for target ... failed` | only a summary line | scroll up to the real error |

