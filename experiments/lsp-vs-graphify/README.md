# Experiment: clangd (LSP) vs Graphify as the code index of the ut skill

Question: does a plain language server give an agent better answers about C/C++ code than the Graphify index the
skill uses today? Two parts. The results are in [RESULTS.md](RESULTS.md).

1. **Fact benchmark.** Every function in two codebases. Both tools answer who it calls, who calls it (production code
   and tests), and where it is defined. The answers are scored against the call graph GCC itself emits
   (`-fcallgraph-info` at `-O0`).
2. **Agent runs.** Haiku 4.5 writes unit tests for 12 target functions, 3 runs per tool. In each run its only view
   of the code is one tool: Graphify through `index.sh`, or clangd through `clangd_cli.py`. Everything else is
   identical in both arms: the task text, the build script and the permissions. Reading, grepping and listing code
   files is denied in both arms. Each run is scored on build, pass, branch coverage of the target (gcov), cost and
   turns.

## Codebases
| | cvaccel | libcanard |
|---|---|---|
| Language | C++17, classes, interfaces, CppUTest | C11 embedded, statics, function-pointer vtables, Unity |
| Source | `examples/cvaccel` in this repo | github.com/OpenCyphal/libcanard @ 1206003 (v5) |
| Build | `build-ut/compile_commands.json` | `libcanard-CMakeLists.txt` (lean 64-bit build; cavl2 and Unity as `SYSTEM` includes, as upstream) |

## Files
- `gt.py ROOT COMPILE_DB OUT.json`: ground-truth call graph from GCC. Every compile-DB unit is compiled with
  `-O0 -fcallgraph-info`, and the result keeps functions defined in the repo, direct call edges, and indirect call
  sites.
- `bench.py NAME GT GRAPHIFY_INDEX ROOT CDB_DIR OUT.json`: the fact benchmark with three arms.
  - `graphify`: the ut `index.json`.
  - `clangd`: live LSP queries, meaning call hierarchy plus references mapped to the enclosing function or TEST.
  - `clangd-graph`: a call graph built once from clangd references.
- `clangd_cli.py`: the LSP tool used by the clangd arm (find, def, source, refs, callers, callees, symbols, hover).
- `agentrun.py prepare|run|score`:
  - `prepare` makes stripped copies (all existing tests deleted) and builds both indexes.
  - `run` does the Haiku runs.
  - `score` rebuilds each run's tests and computes gcov branch coverage of the target.
- `summarize.py results.json`: Markdown tables of the agent runs.
- `results/`: raw benchmark output (`bench-*.txt`, `bench-*.json` with every miss and false positive) and
  `agent-results.json`.

## Reproduce
```bash
S=.agents/skills/ut/resources/scripts
# ground truth + Graphify index + benchmark (cvaccel)
python3 gt.py examples/cvaccel examples/cvaccel/build-ut/compile_commands.json /tmp/gt-cvaccel.json
(cd examples/cvaccel && $S/index.sh build --cdb build-ut/compile_commands.json /tmp/gfy-cvaccel include src client/include client/src sim apps tests tests/mocks)
python3 bench.py cvaccel /tmp/gt-cvaccel.json /tmp/gfy-cvaccel/index.json examples/cvaccel examples/cvaccel/build-ut /tmp/bench-cvaccel.json
# agent runs (needs the claude CLI; ~72 runs)
python3 agentrun.py prepare && python3 agentrun.py run --runs 3 --jobs 4 && python3 agentrun.py score
python3 summarize.py /tmp/claude-0/exp/agent/results.json
```
