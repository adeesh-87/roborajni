# Playbook: fix-build
Test-side code only (production code only if Config allows). Load `tools/errors/build-systems.md` and `tools/errors/<tool>.md`.
1. Build; take the FIRST error only: `grep -nE '(error|Error)[: ]|undefined reference|multiple definition|No such file' <log> | head -5`.
2. Classify with the errors file; fix ONE error; rebuild; repeat. Keep the list of fixes in the task file.
3. Max 3 attempts on the same error → BLOCKED with the exact text.
4. It builds → run all tests once; failing tests go to the task `Result` (they are fix-run work).
5. New build knowledge → KB `Build notes`.
