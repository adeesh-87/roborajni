# Sample diagrams (cvaccel, clang index, gcov coverage of the 215 generated tests)
Mermaid text as agents read it (see `resources/diagrams.md`). Regenerate with `index.sh diagrams|flow|seq|trace`.
- `flow-Dispatcher__pump.md`: branches with coverage counts; the header names the one gap (L82).
- `seq-CvAccelService__clientDisconnected.md`: calls in order, a callback bound through a template parameter.
- `trace-...md`: what one test really called at run time (virtual calls land in the test fakes).
- `SCENARIOS.md`: module overview + one scenario per entry point. `coverage-gaps.md`: `index.sh uncovered`.
