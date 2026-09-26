# Results: clangd (LSP) vs Graphify

Method, files and how to reproduce: [README.md](README.md). Raw data: [`results/`](results/).

## Verdict
| Codebase | Which tool gave the right answers | Which tool gave better tests (Haiku 4.5, 18 runs per tool) |
|---|---|---|
| cvaccel (C++17, interfaces, CppUTest) | **clangd**. Callees F1 0.98 vs 0.78; test callers 1.00 vs 0.89 | **clangd**. Tests pass 15/18 vs 8/18; branch coverage 78% vs 36% |
| libcanard (C11 embedded, macros, statics, vtables) | **Graphify**. Callees F1 1.00 vs 0.90 | **Graphify**. Tests pass 16/18 vs 11/18; branch coverage 65% vs 47% |

Neither tool wins everywhere, and each one loses for reasons that can be named. Cost per run was the same (about
$0.62 vs $0.64).

- **Graphify fails on C++.** It resolves calls by name, and it never shows the namespace, the header that declares
  a symbol, or the complete list of an interface's pure virtual methods. It chose the wrong `const` overload, could
  not tell `Dispatcher::pump` from `CvAccelService::pump`, and has no constructor or destructor calls at all. The
  agents then wrote fakes that did not compile: 7 of the 10 Graphify C++ runs that never built failed with
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
  - 7 runs had undeclared types or namespaces, or incomplete fakes of an interface;
  - 3 runs hit the CppUTest include-order pitfall.
- **clangd, C++ (3 failures):**
  - 1 run hit the same include-order pitfall;
  - 2 runs had failing assertions.
- **clangd, C (7 failures):**
  - wrong struct members;
  - violated `assert` preconditions of the target;
  - no test at all within 80 turns.

The include-order pitfall: including CppUTest's new/delete macros before a standard-library header breaks the
build. It hit both tools and is unrelated to the index. Graphify's card lists `assert` conditions as decisions
because it preprocesses with the build's flags; clangd's `source` shows them only as source text.

Caveats:
- 3 runs per task. The runs of one task are not independent, so the pass-count p-values (Fisher: cvaccel 0.04,
  libcanard 0.12) overstate the evidence. The per-task pattern above is the stronger evidence.
- The agent's "RESULT: DONE" is not evidence. One clangd run and one Graphify run on `postConfig` passed with 0/20
  branches: the tests never called the target, they only checked their own variables.

## What this means for the skill
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
