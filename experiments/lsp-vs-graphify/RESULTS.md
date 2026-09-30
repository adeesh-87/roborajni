# Results: clangd (LSP) vs Graphify vs grep

Method, files and how to reproduce: [README.md](README.md). Raw data: [`results/`](results/).

## Update: the grep baseline beats both indexes
A third arm ran the same 12 tasks x 3 runs with no index tool. Haiku could read, grep and list the code freely,
which is how Claude Code works by default. It did best on almost every measure:

| Tool (both codebases, 36 runs each) | Tests build & pass | Branch coverage (mean) | 100% branches | Cost/run | Turns | Hit the 80-turn cap |
|---|---|---|---|---|---|---|
| Graphify only (reading code denied) | 24/36 | 51% | 4 | $0.62 | 64 | 15 |
| clangd only (reading code denied) | 26/36 | 63% | 7 | $0.64 | 67 | 14 |
| **grep + read, no index** | **32/36** | **77%** | **11** | **$0.55** | **49** | **5** |

Per codebase:
- **cvaccel:** grep 17/18 and 92% branch coverage, against clangd 15/18 and 78%, and Graphify 8/18 and 36%.
- **libcanard:** grep 15/18 and 61%, against Graphify 16/18 and 65%, and clangd 11/18 and 47%.

Section 3 below has the per-task table.

Three things limit what this shows:
1. **The index arms were also denied reading the code.** The skill denies reads today, and the experiment did the
   same, so this compares "index only" against "reading". It does not test "index first, reading allowed". The
   failures of the index arms are all things the source shows directly: namespaces, `#include` lines, full
   interfaces, macros and struct fields. The grep agents got them by reading whole files (13 `Read` calls per run on
   average; `Grep` fewer than 2).
2. **Both codebases are small** (cvaccel 960 lines of production code, libcanard about 2,800), so reading whole files
   is cheap. An index should matter more as code grows, but that is untested.
3. **Grep answers are noisy.** On "which lines call F", grep's precision is 0.25 in C++ and 0.80 in C, against 0.95
   and 0.99 for clangd (section 4). In small code, the agent absorbs that noise by reading.

Consequence for the skill: on these codebases, "never read or grep code, only the index" (the current agent command
denies `Read` of code paths and `Grep`) made the agents worse, not better. The next experiment to run: the index as
the first stop, with reading allowed, on a larger codebase.

## Verdict (Graphify vs clangd, both with reading denied)
| Codebase | Which tool gave the right answers | Which tool gave better tests (Haiku 4.5, 18 runs per tool) |
|---|---|---|
| cvaccel (C++17, interfaces, CppUTest) | **clangd**. Callees F1 0.98 vs 0.78; test callers 1.00 vs 0.89 | **clangd**. Tests pass 15/18 vs 8/18; branch coverage 78% vs 36% |
| libcanard (C11 embedded, macros, statics, vtables) | **Graphify**. Callees F1 1.00 vs 0.90 | **Graphify**. Tests pass 16/18 vs 11/18; branch coverage 65% vs 47% |

Neither tool wins everywhere, and each one loses for reasons that can be named. Cost per run was the same (about
$0.62 vs $0.64).

- **Graphify fails on C++.** It resolves calls by name, and it never shows the namespace, the header that declares
  a symbol, or the complete list of an interface's pure virtual methods. It chose the wrong `const` overload, could
  not tell `Dispatcher::pump` from `CvAccelService::pump`, and has no constructor or destructor calls at all. The
  agents then wrote fakes that did not compile: 6 of the 10 Graphify C++ runs that never built failed with
  "`JobDesc` does not name a type", "`Dispatcher` has not been declared", or "abstract type `MockDevice`". clangd's
  `hover` answers "provided by `cvaccel/request_queue.hpp`, in namespace `cvaccel`".
- **A plain LSP fails on embedded C.** clangd's workspace symbols do not contain macros: `find CANARD_IFACE` returns
  nothing, and `source RX_SLOT_OVERHEAD` reports that no such symbol exists. In the C runs, 21% of clangd queries
  came back empty, against 4% for Graphify. clangd also misses:
  - every call into a vendored header included with `-isystem`, which libcanard's own CMake does for cavl2;
  - callers inside CppUTest `TEST` bodies (call hierarchy finds none; references do);
  - pointer calls: it counts a function passed as a pointer as a call.

## 1. Fact benchmark (ground truth: GCC `-fcallgraph-info`, every function of the repo)
F1 per question: precision and recall over all edges. "clangd" means live LSP queries: call hierarchy, plus
references mapped to the enclosing function or TEST. "clangd-graph" is one graph built from clangd references, the
way an index would be built on clangd.

| Question | cvaccel: Graphify | cvaccel: clangd | cvaccel: clangd-graph | libcanard: Graphify | libcanard: clangd | libcanard: clangd-graph | libcanard `-I`: clangd-graph |
|---|---|---|---|---|---|---|---|
| Callees of a production function | 0.78 | **0.98** | 0.96 | **1.00** | 0.90 | 0.91 | 0.97 |
| Production callers | 0.75 | **0.91** | **0.91** | **1.00** | 0.90 | 0.90 | 0.95 |
| Test callers ("which tests reach it") | 0.89 | **1.00**¹ | **1.00** | **1.00** | **1.00** | **1.00** | **1.00** |
| Callees of a test | 0.91 | 0.00² | **1.00** | **1.00** | 0.99 | 0.99 | 1.00 |
| Constructor / destructor calls | 0.00 | 0.05 | **0.84** | – | – | – | – |
| Calls through an interface (20 sites) | 0.95 | **1.00** | **1.00** | – | – | – | – |
| Definition found by name | **1.00** | **1.00** | **1.00** | **1.00** | 0.99 | 0.99 | 0.99 |
| Cold index build | 7 s | 3 s | +30 s graph | 15 s | 2 s | +34 s graph | |

¹ Only because the benchmark maps raw references to the TEST around them: clangd's `callers` (incomingCalls)
returns none of the 408 test callers, because CppUTest's TEST macro generates the function.
² The call hierarchy cannot be opened on a TEST macro.

Scope: 334 functions and 566 named call edges in cvaccel; 684 functions and 2049 edges in libcanard. The benchmark
neither rewards nor penalises:
- calls written inside lambdas;
- dynamic dispatch to overrides;
- compiler-generated members;
- CppUTest macro internals.

Function-pointer calls (10 sites in libcanard's vtables) have no static answer. Graphify lists candidate targets;
clangd lists nothing. cvaccel is this repo's example, and Graphify's fixes were developed on it, which if anything
favours Graphify.

## 2. Agent runs (Haiku 4.5, 12 target functions x 3 runs x 2 tools)
Setup, identical for both tools:
- All existing tests were deleted from both codebases.
- Reading, grepping and listing the code was denied, so the tool was the only view of it.
- The agent built and ran its tests with `./ut_run.sh`, limited to 80 turns.

After each run, the agent's tests were rebuilt and gcov measured the branches of the target function.

| Codebase | Tool | Tests build & pass | Branch coverage (mean, failed = 0) | Coverage of passing runs | 100% branches | Hit the 80-turn cap | Cost/run | Empty tool answers |
|---|---|---|---|---|---|---|---|---|
| cvaccel | Graphify | 8/18 | 36% | 82% | 4 | 11 | $0.59 | 5% |
| cvaccel | clangd | **15/18** | **78%** | 87% | 7 | 6 | $0.58 | 1% |
| libcanard | Graphify | **16/18** | **65%** | 73% | 0 | 4 | $0.64 | 4% |
| libcanard | clangd | 11/18 | 47% | 77% | 0 | 8 | $0.69 | 21% |
| both | Graphify | 24/36 | 51% | | 4 | 15 | $0.62 | |
| both | clangd | 26/36 | 63% | | 7 | 14 | $0.64 | |

Per task (✓ = the tests build and pass; x/y = branches taken out of y):

| Codebase | Target | Graphify | clangd |
|---|---|---|---|
| cvaccel | RequestQueue::enqueue | ✓17/17 ✓17/17 ✓17/17 | ✓17/17 ✓17/17 ✓17/17 |
| cvaccel | MemoryPool::allocate | ✓19/19 ✓17/19 ✓16/19 | ✗ ✓17/19 ✓17/19 |
| cvaccel | CvAccelService::postConfig | ✗ ✓0/20 ✗ | ✓0/20 ✓19/20 ✓19/20 |
| cvaccel | Dispatcher::onCompletion | ✗ ✓12/15 ✗ | ✓15/15 ✗ ✓15/15 |
| cvaccel | Dispatcher::pump | ✗ ✗ ✗ | ✓24/24 ✗ ✓24/24 |
| cvaccel | Dispatcher::cancelSession | ✗ ✗ ✗ | ✓12/17 ✓13/17 ✓14/17 |
| libcanard | tx_push | ✓28/36 ✓28/36 ✓28/36 | ✓26/36 ✗ ✓28/36 |
| libcanard | rx_parse | ✓73/88 ✓72/88 ✓70/88 | ✓74/88 ✓77/88 ✓75/88 |
| libcanard | rx_filter_configure | ✓14/20 ✓16/20 ✓14/20 | ✓14/20 ✓15/20 ✓16/20 |
| libcanard | node_id_occupancy_update | ✓26/36 ✓24/36 ✓26/36 | ✓27/36 ✓26/36 ✓25/36 |
| libcanard | rx_session_complete_slot | ✗ ✓19/28 ✓19/28 | ✗ ✗ ✗ |
| libcanard | rx_session_update | ✗ ✓36/50 ✓24/50 | ✗ ✗ ✗ |

The clear differences come from the tasks that need the most knowledge about surrounding code:
- **C++, the Dispatcher tasks.** The agent has to fake two interfaces and build the objects the code under test
  uses.
- **C, the rx_session tasks.** The agent needs internal structs, macros, allocators and preconditions.

Where the target is self-contained, both tools do equally well.

Why runs failed:
- **Graphify, C++ (10 runs never built):**
  - 6 runs had undeclared types or namespaces, or incomplete fakes of an interface;
  - 4 runs hit the CppUTest include-order pitfall.
- **clangd, C++ (3 failures):**
  - 1 run hit the same include-order pitfall;
  - 2 runs had failing tests.
- **clangd, C (7 failures):**
  - 2 runs had wrong struct members or types;
  - 2 runs violated `assert` preconditions of the target;
  - 1 run failed its own leak check;
  - 2 runs produced no test within 80 turns.
- **Graphify, C (2 failures):**
  - 1 run had an undeclared identifier;
  - 1 run produced no test.

The include-order pitfall: including CppUTest's new/delete macros before a standard-library header breaks the
build. It hit both tools and is unrelated to the index. Graphify's card lists `assert` conditions as decisions
because it preprocesses with the build's flags; clangd's `source` shows them only as source text.

Caveats:
- 3 runs per task. The runs of one task are not independent, so the pass-count p-values (Fisher: cvaccel 0.04,
  libcanard 0.12) overstate the evidence. The per-task pattern above is the stronger evidence.
- The agent's "RESULT: DONE" is not evidence. One clangd run and one Graphify run on `postConfig` passed with 0/20
  branches: the tests never called the target, they only checked their own variables.

## What this means for the skill
*(Written before the grep baseline. That baseline, in the Update at the top, comes first: allowing agents to read
code mattered more than which index they used.)*

A plain LSP given to agents in place of the index would help C++ and hurt embedded C. What each tool does well is
something the other can supply cheaply:

| Needed | Plain clangd | Graphify | A clangd-built index + tree-sitter (proposal) |
|---|---|---|---|
| Correct C++ calls: overloads, members, ctor/dtor, interfaces | yes | no | yes (clangd references) |
| Namespace, declaring header, full interface for fakes | yes (hover) | no | yes (clangd hover and documentSymbol in the card) |
| Macros and constants | **no** | yes | yes (tree-sitter symbols, as today) |
| Callers and callees of CppUTest TEST blocks | **no** (call hierarchy) | yes | yes (references mapped to TEST ranges) |
| Decisions with preconditions (the card) | no | yes | yes (tree-sitter outline, as today) |
| Vendored `-isystem` headers inside the repo | **no** | yes | yes, once in-repo `-isystem` paths are rewritten to `-I` for indexing (0.97 above) |
| Function pointers passed as arguments | counted as calls | candidate targets | keep only references followed by `(` as calls |

Proposal: keep `index.sh`, the cards and every command. Build the call graph and the type facts in `index.json` from
clangd (the clangd-graph arm above) instead of from Graphify. Keep the tree-sitter parts: decision outlines, macros,
TEST blocks and symbols. Graphify itself then goes away. Its only unique extra is candidate targets of function
pointers, which the ut fixes can keep computing from tree-sitter.

## 3. Agent runs: all three arms
| Codebase | Arm | Runs | Tests pass | RESULT: DONE | Branch cov. (mean) | 100% branches | Cost/run | Turns | Time/run | Code lookups | Builds | Denied |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| cvaccel | graphify | 18 | 8/18 | 7/18 | 36% | 4/18 | $0.59 | 66 | 280 s | 38.6 | 11.0 | 5.5 |
| cvaccel | clangd | 18 | 15/18 | 12/18 | 78% | 7/18 | $0.58 | 63 | 323 s | 36.8 | 10.8 | 6.1 |
| cvaccel | grep | 18 | 17/18 | 17/18 | 92% | 11/18 | $0.43 | 42 | 226 s | 22.1 | 7.4 | 0.0 |
| libcanard | graphify | 18 | 16/18 | 14/18 | 65% | 0/18 | $0.64 | 61 | 291 s | 32.5 | 10.2 | 4.7 |
| libcanard | clangd | 18 | 11/18 | 10/18 | 47% | 0/18 | $0.69 | 72 | 311 s | 42.2 | 8.9 | 5.8 |
| libcanard | grep | 18 | 15/18 | 14/18 | 61% | 0/18 | $0.66 | 57 | 259 s | 31.7 | 8.7 | 0.0 |
| all | graphify | 36 | 24/36 | 21/36 | 51% | 4/36 | $0.62 | 64 | 285 s | 35.5 | 10.6 | 5.1 |
| all | clangd | 36 | 26/36 | 22/36 | 63% | 7/36 | $0.64 | 67 | 317 s | 39.5 | 9.9 | 6.0 |
| all | grep | 36 | 32/36 | 31/36 | 77% | 11/36 | $0.55 | 49 | 243 s | 26.9 | 8.1 | 0.0 |

| Codebase | Task | graphify: pass, branch cov. per run | clangd: pass, branch cov. per run | grep: pass, branch cov. per run | graphify $ | clangd $ | grep $ |
|---|---|---|---|---|---|---|---|
| cvaccel | CvAccelService::postConfig | ✗- ✓0/20 ✗- | ✓0/20 ✓19/20 ✓19/20 | ✓19/20 ✓19/20 ✓19/20 | 0.89 | 0.55 | 0.34 |
| cvaccel | Dispatcher::cancelSession | ✗- ✗- ✗- | ✓12/17 ✓13/17 ✓14/17 | ✓16/17 ✗- ✓14/17 | 0.67 | 0.74 | 0.60 |
| cvaccel | Dispatcher::onCompletion | ✗- ✓12/15 ✗- | ✓15/15 ✗- ✓15/15 | ✓15/15 ✓15/15 ✓15/15 | 0.74 | 0.70 | 0.41 |
| cvaccel | Dispatcher::pump | ✗- ✗- ✗- | ✓24/24 ✗6/24 ✓24/24 | ✓24/24 ✓24/24 ✓24/24 | 0.67 | 0.84 | 0.68 |
| cvaccel | MemoryPool::allocate | ✓19/19 ✓17/19 ✓16/19 | ✗17/19 ✓17/19 ✓17/19 | ✓19/19 ✓17/19 ✓19/19 | 0.30 | 0.47 | 0.31 |
| cvaccel | RequestQueue::enqueue | ✓17/17 ✓17/17 ✓17/17 | ✓17/17 ✓17/17 ✓17/17 | ✓17/17 ✓17/17 ✓17/17 | 0.28 | 0.16 | 0.26 |
| libcanard | node_id_occupancy_update | ✓26/36 ✓24/36 ✓26/36 | ✓27/36 ✓26/36 ✓25/36 | ✓28/36 ✓24/36 ✓25/36 | 0.45 | 0.63 | 0.50 |
| libcanard | rx_filter_configure | ✓14/20 ✓16/20 ✓14/20 | ✓14/20 ✓15/20 ✓16/20 | ✗- ✓16/20 ✓16/20 | 0.32 | 0.50 | 0.57 |
| libcanard | rx_parse | ✓73/88 ✓72/88 ✓70/88 | ✓74/88 ✓77/88 ✓75/88 | ✓73/88 ✓75/88 ✓73/88 | 0.81 | 0.85 | 0.46 |
| libcanard | rx_session_complete_slot | ✗- ✓19/28 ✓19/28 | ✗- ✗- ✗- | ✓19/28 ✓19/28 ✓19/28 | 0.75 | 0.73 | 0.59 |
| libcanard | rx_session_update | ✗- ✓36/50 ✓24/50 | ✗- ✗- ✗- | ✗- ✓26/50 ✗- | 0.81 | 0.75 | 1.02 |
| libcanard | tx_push | ✓28/36 ✓28/36 ✓28/36 | ✓26/36 ✗- ✓28/36 | ✓27/36 ✓27/36 ✓27/36 | 0.71 | 0.71 | 0.82 |

## 4. Grep baseline for facts: "which lines call F?"
One question per production function, answered by each tool, scored against GCC's call sites (a returned line
counts if it is within 2 lines of a call; GCC reports a call inside a multi-line macro argument at the macro's
first line). Script: `bench_sites.py`. Output: `results/sites-*.txt`.

| Tool | cvaccel (C++): precision | recall | F1 | lines/question | libcanard (C): precision | recall | F1 | lines/question |
|---|---|---|---|---|---|---|---|---|
| `grep -rnw NAME` | 0.25 | 1.00 | 0.40 | 34 | 0.80 | 0.97 | 0.88 | 16 |
| `grep -rnE 'NAME\s*\('` | 0.50 | 1.00 | 0.66 | 17 | 0.87 | 0.97 | 0.92 | 14 |
| Graphify | 0.91 | 0.57 | 0.70 | 5 | 1.00 | 0.73 | 0.84 | 9 |
| clangd (`refs`) | **0.95** | **1.00** | **0.98** | 9 | **0.99** | **0.98** | **0.99** | 13 |

- **Grep finds nearly every call but returns many other lines.** In C++, method names are shared across classes,
  so 3 of every 4 lines are something else. Grep misses calls made through macros such as `LIST_HEAD`.
- **Graphify's recall is capped by its format.** It stores one call line per caller and callee pair, so a test that
  calls a function twice shows one line. The *callers* themselves it finds (section 1).
- **Grep cannot say which function or test a line belongs to**, or what a function calls. The agent reads the file
  for that.
