# T<NN> — <short title>
Type: add-tests | update-tests | remove-tests | fix-mocks | fix-build | fix-run | raise-coverage
Wave:  | Work items: W#  | Depends on:  | Status: TODO | Owner:

## Goal
<one sentence>

## Inputs (read these, nothing else)
- Card: KB_DIR/modules/<name>.cards.md → functions: <f1, f2>
- Exemplar: KB_DIR/exemplars/test.md (+ mock.md)
- Tool file: resources/tools/<tool>.md  | Playbook: resources/playbooks/<type>.md

## Touches (every path this task may write)
-

## Cases (one test per line; from the card's Decisions)
| # | Function | Inputs / state | Mock setup | Expected |
|---|----------|----------------|------------|----------|

## Done when
- [ ] `<single-test command>` prints `<expected summary, e.g. OK (n tests ...)>`
- [ ] (coverage) lines <..> covered

## Result (executor)
Outcome: DONE / PARTIAL / BLOCKED | Files changed: | Tests added/changed/removed: | Build+run: | Open issues / learnings:
