# Codebase decomposition request for a stronger model

You are asked to explain part of a C/C++ codebase so that a smaller model can write unit tests for it.
Do not write tests. Write short, factual module notes.

## Read
1. <KB_DIR>/kb.md sections 0, 2, 3 (identity, code map table, test conventions)
2. <KB_DIR>/graphify/out/GRAPH_REPORT.md and, for questions, `graphify.sh explain|query|path <KB_DIR>/graphify ...`
   (run from <SKILL_DIR>/resources/scripts/)
3. <KB_DIR>/codemap/summary.md (functions, calls, external dependencies; a heuristic map, verify in code)
4. The source files of these modules: <MODULES / PATHS>

## Write one file per module: <KB_DIR>/decompositions/<module>.md
Keep each file under 120 lines. Use this structure:
```
# <module> (<source files>)
Purpose: 1-3 sentences.
Public API: function | what it does | important preconditions | return / error codes
Internal (static) functions worth testing directly: ...
State: globals / static variables, their valid values, who changes them, how to reset them in a test
Data structures: the few that tests must build, with the fields that matter
Control flow: state machines (states, events, transitions), loops waiting on hardware/flags, timeouts
Dependencies: external calls and what each is used for; which should be mocked; which are pure helpers
Error handling: how errors are detected and reported; which error paths are hard to reach and how
Hardware / OS touch points: registers, ISRs, critical sections, delays, RTOS calls
Testability notes: seams (function pointers, weak symbols, STATIC macros), traps (asserts, infinite loops)
Suggested test focus: 5-15 bullets, highest risk first
Open questions for a human: ...
```
## Then
- In <KB_DIR>/kb.md: add one row per module file to section 1, and 3-5 lines per module to section 6
  ending with `(source: decompositions/<module>.md)`.
- Tell the user the notes are written.
