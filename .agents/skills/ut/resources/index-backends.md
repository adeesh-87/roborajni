# Code index backends (for the orchestrator and the user; test writers never need this file)
Every backend writes the same `KB_DIR/index/index.json`; cards, deps, tests, impact, refresh, diagrams, coverage and
traces read only that file. The ut tool picks the backend with `index.sh detect` in phase 3 and asks at most ONE
question (only when clang is not usable and both gcc and graphify are). Switch any time: `ut index --backend gcc`.

| Backend | Needs | Calls | Branches (outline) | Fits embedded code | Main limit |
|---------|-------|-------|--------------------|--------------------|------------|
| clang (default when it parses cleanly) | compile DB + libclang (`index.sh setup clang`) | exact: overloads, templates, virtual dispatch, calls made by macros, constructors, lambdas, std::function and function-pointer callbacks (also through parameters) | exact, from the same AST | vendor extensions (IAR, TI, Keil) can fail to parse: `UT_CLANG_EXTRA="--target=arm-none-eabi -D__IAR_SYSTEMS_ICC__=0"` or use gcc | a unit with parse errors has incomplete facts (listed in the build output) |
| gcc | compile DB whose compiler is GCC >= 10 (a cross gcc works) | exact for every direct call the compiler emits (compiles each unit once at -O0); indirect/virtual calls named from tree-sitter | tree-sitter on the preprocessed code | uses YOUR compiler and flags; also records stack usage per function (`stack` in the index) | lambdas are merged into the function that defines them; units that do not compile are missing |
| graphify | Python 3.10+ (`index.sh setup`) | tree-sitter + name/type heuristics | tree-sitter | no compile needed; tolerates broken code | method calls on receivers of unknown type link by name only (can pick a wrong same-name method) |
| codemap | bash, grep | names | rough | anything | card/deps/tests only; no diagrams, no impact |

clangd (`index.sh lsp`, `index.sh setup clangd`) is not a backend: it answers one question at a time (callers,
callees, references) for the orchestrator, a stronger model or a human. It keeps its index in the build directory
(`.cache/clangd`). Calls made inside TEST macros may be missing from its caller lists; the index has them.

## Measured on the cvaccel example (C++17, 7 source files, 215 CppUTest tests), same compile DB
| | clang | gcc | graphify |
|---|---|---|---|
| build time | 4 s | 6 s | 7 s |
| functions | 115 | 110 | 133 (includes type and field names) |
| TEST blocks | 224 | 224 | 224 |
| call edges (by name) | 758 | 757, of which 754 shared with clang | 520, of which 508 shared with clang |
| TEST blocks calling `Dispatcher::pump` directly | 29 | 29 | 0 (receiver type not resolved) |
| edges only this backend has, wrong on review | - | 0 of 3 | 9 of 12 (e.g. `dispatcher_.pump()` linked to `CvAccelService::pump`, `q.size()` of a std::deque linked to `RequestQueue::size`) |
| self-test (15 known answers) | 15/15 | 15/15 | 15/15 |
`index.sh compare A B` prints this comparison for your own code; `ut index --compare gcc` stores it in the task.

## Views built on the index (any backend)
- `flow` / `seq` / `scenarios` / `diagrams`: Mermaid text, see `resources/diagrams.md`. Size on cvaccel: a flowchart
  is 1.0–1.6x the words of the function's card, a one-level sequence 0.8–2.5x. The executor prompt gets them only
  for coverage tasks, functions with >= 4 decisions (flow) and functions with >= 2 mockable collaborators (seq),
  within 900 words per prompt (`ut run --diagrams on|off` overrides).
- `cov-import`: lcov `.info`, a gcov build tree (`--gcov-dir`, best: exception arcs are removed), CTC++ `profile.txt`
  (`ctcpost -p`), or a neutral JSON. Counts go onto the flowchart edges; `uncovered` lists the gaps; `ut coverage`
  turns them into work items whose cases are exactly the missing outcomes.
- `trace`: builds the tests with `-finstrument-functions` in a separate build tree, runs them, and writes one runtime
  sequence per TEST (virtual dispatch and callbacks as they really happened) plus the runtime reach shown in cards.
  Linux + glibc + binutils only.
