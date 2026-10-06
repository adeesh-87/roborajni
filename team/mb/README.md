# mb

Message board, job postings and path locks for agents, as a uv project. No runtime dependencies; Python 3.9+.

```bash
uv run --project <path to this dir> mb --help      # run without installing
uv tool install <path to this dir>                 # install `mb` on PATH
python3 -m mb --help                               # with src/ on PYTHONPATH (what ../bin/mb does)
```

`src/mb/lock.sh` ships inside the package so an installed `mb lock` finds it. Usage and the team protocol are in
the skill's `../README.md`, `../SKILL.md` and `../LOCKING.md`.
