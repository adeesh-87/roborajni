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

To upgrade: replace the wheel, update the version in `scripts/graphify.sh` (`GRAPHIFY_VERSION`), delete `.venv/`,
run `setup`, and re-test on a known codebase.
