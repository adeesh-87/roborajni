# cpp_analysis: dead code and MC/DC decisions for C/C++

Two libclang-based tools:

* `dead_code.py` finds dead functions (call-graph reachability from each product's entry points), unreachable statements (`-Wunreachable-code-aggressive`), and `#if` blocks that are never compiled in any analysed configuration.
* `mcdc.py` lists every decision, with its conditions, a minimal MC/DC test set and the independence pair for each condition.

## Setup

```bash
pip install libclang                  # Python bindings + bundled libclang, no LLVM install needed
cmake -B build -DCMAKE_EXPORT_COMPILE_COMMANDS=ON ...   # or: bear -- make
```

You need a `compile_commands.json`, because the tools parse every file with its real defines and include paths.

* Make-based builds can generate one with [`bear`](https://github.com/rizsotto/Bear) (`bear -- make`).
* The pip libclang has no clang builtin headers (`stddef.h`, `stdbool.h`...). The tools borrow them from the compiler named in each compile command, or from `gcc`.
* Cross-compiled code may also need `--extra-arg=--target=aarch64-linux-gnu`, or `--resource-dir` pointing at a clang install.
* Files that fail to compile are counted in a warning. `--show-errors` lists them, and their results may be incomplete.

## Quick start

```bash
python3 dead_code.py -p build --entry main --exclude tests/
python3 dead_code.py -p build --public-headers client/include/ --include client/ --include shared/
python3 mcdc.py -p build --exclude tests/ --min-conditions 2
python3 mcdc.py -p build --include driver/src/dispatch.c --detail
```

Try both tools on the included sample first:

```bash
python3 dead_code.py --config sample/analysis.json
python3 mcdc.py --config sample/analysis.json --detail
```

## Several products sharing code (`--config`)

Use a config when a codebase builds several things: a daemon, client libs, and a component shared between them. Paths are relative to the config file.

```json
{
  "project_root": ".",
  "compile_commands": "build/compile_commands.json",
  "exclude": ["tests/", "third_party/"],
  "extra_roots": ["^isr_"],
  "products": [
    {"name": "driver", "sources": ["driver/"], "entry_points": ["main"]},
    {"name": "client", "sources": ["client/", "shared/"],
     "public_headers": ["client/include/"], "command_regex": "clientlib\\.dir"},
    {"name": "guest_client", "sources": ["guest_client/", "shared/"],
     "public_headers": ["guest_client/include/"],
     "compile_commands": "build-guest/compile_commands.json"}
  ]
}
```

| Key | Meaning |
|---|---|
| `sources` | Which files (and compile entries) belong to the product. Each pattern is a folder/file prefix, or a glob where `*` also matches `/`. |
| `entry_points` | Function names that are always used, e.g. `main`. |
| `public_headers` | Every function declared in these headers is API, so it counts as used. Use this for libraries. |
| `extra_roots` | Regexes for functions that are called invisibly: ISRs, asm, `dlsym`, linker scripts. |
| `command_regex` | Picks this product's compile entries when the same file is compiled into several products, e.g. shared code built into both client libs. It's matched against the compile command, typically the `-o` output path. |
| `compile_commands` | Per-product compile database, e.g. a separate guest-VM build directory. |

With neither `entry_points` nor `public_headers`, `main` is used if it exists. Otherwise every external function counts as used, and externals that nobody calls are listed as "no callers".

## How dead functions are decided

Everything reachable from the roots is used. The call graph follows:

* **Calls:** direct calls.
* **Taken addresses:** callbacks such as `signal(SIGTERM, handler)`, function pointers, and dispatch tables in global initialisers.
* **Overrides:** virtual overrides, when the base method is used.
* **Templates:** template instantiations, and unresolved calls inside templates (matched by name).

Shared code is reported as `dead` only when it is dead in every product that contains it. Otherwise it is reported as `unused in <product>`, together with the products that do use it.

Never reported as dead, to avoid false alarms:

* constructors and destructors
* overrides of virtual methods from outside the project
* functions with `__attribute__((constructor|destructor|used|interrupt))`
* functions referenced from globals that have external linkage or a dynamic initialiser

Limits:

* Calls through function pointers that are built at runtime, e.g. from `dlsym` or integer casts, can't be seen. Add those functions as `extra_roots`.
* Only the configurations in the compile database are analysed. "Never compiled" means inactive in every one of them.

## MC/DC definition used

The tool uses unique-cause MC/DC with C short-circuit evaluation. A condition that wasn't evaluated is a don't-care (`-`). Two tests form an independence pair for condition c when:

* c has different values in them,
* the outcome differs, and
* every other condition evaluated in both tests has the same value.

This is the same rule clang's `-fcoverage-mcdc` / `llvm-cov --show-mcdc` applies, so measured coverage can be compared directly. Build the tests with clang ≥ 18 using `-fprofile-instr-generate -fcoverage-mapping -fcoverage-mcdc`.

**What counts as a decision:** conditions of `if`, `while`, `do`, `for` and `?:`, plus every other `&&` / `||` expression, as DO-178C does. Use `--branch-only` to drop the non-branch expressions.

**Where conditions are split:** expressions are split on `&&`, `||` and `!`. With `--bitwise`, `&`, `|` and `^` between boolean operands also split, and those are evaluated without short-circuit.

**Notes in the report:**

* **Decisions from macros:** conditions inside a macro body are shown expanded.
* **Constant conditions:** for example `while (1)`, where only one outcome is possible.
* **Coupled conditions:** the same expression appears twice. Impossible combinations are left out, so a redundant condition shows up as "can't be shown independent".
* **Too big:** decisions with more than `--max-conditions` conditions are listed without a test set.
