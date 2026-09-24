# Bundled Graphify (pinned)

Graphify turns source code into a queryable knowledge graph (functions, calls, includes, references)
using tree-sitter. Upstream: https://github.com/Graphify-Labs/graphify — licensed Apache-2.0 / MIT
(see `LICENSE`, `LICENSE-MIT`, `NOTICE` in this folder, which must stay with the wheel).

| File | Purpose |
|------|---------|
| `graphifyy-0.9.67-py3-none-any.whl` | the exact Graphify version the ut skill was written and tested against (pure Python) |
| `known-good-deps.txt` | dependency versions it was tested with (Linux x86-64, Python 3.11) |
| `.venv/` | created by `scripts/graphify.sh setup`; platform specific, not committed |
| `wheels/` | optional offline wheelhouse, created by `scripts/graphify.sh wheelhouse`; not committed |

Only the wheel is bundled. Its dependencies (numpy, rapidfuzz, tree-sitter and grammar packages) are
compiled per operating system and Python version, so they are installed on the target machine:
- **With a package index** (PyPI or your company mirror, via normal pip config): `scripts/graphify.sh setup`.
- **Offline machine**: on a machine with internet run
  `scripts/graphify.sh wheelhouse resources/vendor/graphify/wheels <platform> <python version>`,
  e.g. `win_amd64 3.11`, `manylinux2014_x86_64 3.12`, `macosx_11_0_arm64 3.12`,
  copy the `wheels/` folder to the offline machine, then run `setup` there (it uses `wheels/` automatically).

Requirements: Python 3.10 or newer, bash (Git Bash or WSL on Windows).

The ut skill uses only Graphify's local code mode (`update`, `query`, `explain`, `path`). The wrapper removes
LLM API keys from Graphify's environment, so no code or names are sent to any model provider.

## C/C++ fixes (ut skill code, not part of Graphify)
`scripts/graphify_ut.py` runs around the unmodified Graphify, so the wheel can be upgraded independently:
- **mirror**: copies only the in-scope files; with `--cdb compile_commands.json` it preprocesses each source with
  its real flags (macros expanded, inactive `#if` branches removed, system/third-party header text dropped) and
  keeps a line map back to the original files.
  Each in-scope header's text is kept in ONE translation unit (its own source file first), so large C++ code
  bases are not parsed once per includer (GoogleTest: 118k -> 18k nodes, 4.5 min -> 45 s). Units are preprocessed
  in parallel (`UT_JOBS` = number of workers).
- **augment** (after `graphify update`): original files/lines restored, `static` flags, external callees as nodes
  (`kind` function / pointer / macro / library / test-framework, `declared_in`), one node per
  `TEST`/`TEST_F`/`TEST_GROUP`/... block, duplicates merged, recursion kept;
  C++: methods qualified as `Class::method()` at their definition, `virtual` / `pure_virtual` flags, `obj.m()`
  resolved by the declared type of `obj` (incl. base classes);
  C: function pointers bound to the functions stored in them (designated and positional struct initializers,
  assignments, callbacks passed to a registration function), so call chains continue through them.
- Graphify then re-clusters locally so `GRAPH_REPORT.md` reflects the fixes (`graph.html` skipped above 5000 nodes).
- **deps** / **tests**: the two questions unit-test work asks most (mock candidates; tests reaching a function).
- **selftest**: bundled fixture (`scripts/selftest/`) with known answers, built with the local compiler.

To upgrade: replace the wheel, update the version in `scripts/graphify.sh` (`GRAPHIFY_VERSION`), delete `.venv/`,
run `setup`, and re-test on a known codebase.
