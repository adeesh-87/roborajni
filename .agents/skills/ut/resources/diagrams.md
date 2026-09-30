# Reading the Mermaid diagrams (text for you; nobody renders them)
They are generated from the code index. Every node or message carries its source line `Lnn`: open that line if you
need more. Trust the line numbers; do not trust your memory of the code.

## Flowchart (`flow`) = the branches of ONE function
```
d47{"L47 if st == Status::BUSY"}        a decision; {"..."} = decision, ["..."] = calls in a row, (["..."]) = return/throw
d47 -->|"T 1x"| c50                      T = condition true, taken 1 time in the last coverage run
d47 -->|"F NOT HIT"| c55                 F = condition false, NO test takes it: write the test that makes it false
d36 -->|"loop"| d38 / -->|"done"|        loop body / loop exit
d82 -->|"T (1/4 branch outcomes hit)"|   compound condition (&&, ||): each sub-condition must flip the outcome alone
%% Coverage: missing outcomes: ...       the header lists every gap of the function in one line
```
No counts on an edge = no coverage imported, or the tool cannot measure that edge.
Use it to find the path to a missing outcome: follow the edges from `start` and list the conditions you must set.

## Sequence (`seq`) = the calls of ONE function, in order
```
participant IAccelBlock as IAccelBlock (interface; test doubles: FakeAccelBlock (tests/dispatcher_test.cpp))
Dispatcher->>IAccelBlock: L26 hw_.submit()      the call and its line
opt L27 st == Status::OK ... end                 calls that happen only when the condition holds
alt L22 case OPEN ... else L25 case CLOSE ... end   switch / if-else
loop L36 for ... end                             repeated calls
Note over X: L41 return -1                       an early exit of the function under test
```
Participant notes tell you what to REUSE: `test doubles: FakeX (file)` → include that file / copy that fake;
`no definition in scope: tests need a stub/mock` → write one like `exemplars/mock.md`; `function pointer p; may call f`
→ set `p` to your fake. Runtime sequences (`diagrams/traces/*.md`) show what one existing test really called.

## What is generated and how it is used
- `flow` / `seq` / `scenarios` / `diagrams`: Mermaid text, see `resources/diagrams.md`. Size on cvaccel: a flowchart
  is 1.0–1.6x the words of the function's card, a one-level sequence 0.8–2.5x. They are always generated into
  `KB_DIR/diagrams/` and any agent can print one with `index.sh flow|seq`. The executor PROMPT does not include them
  by default (profile `prompt_diagrams=off`); `ut run --diagrams auto` adds them for coverage tasks, functions with
  >= 4 decisions (flow) and functions with >= 2 mockable collaborators (seq), within 900 words per prompt.
  Why off: the A/B run below showed no gain for the extra words.
- `cov-import`: lcov `.info`, a gcov build tree (`--gcov-dir`, best: exception arcs are removed), CTC++ `profile.txt`
  (`ctcpost -p`), or a neutral JSON. Counts go onto the flowchart edges; `uncovered` lists the gaps; `ut coverage`
  turns them into work items whose cases are exactly the missing outcomes.
- `trace`: builds the tests with `-finstrument-functions` in a separate build tree, runs them, and writes one runtime
  sequence per TEST (virtual dispatch and callbacks as they really happened) plus the runtime reach shown in cards.
  Linux + glibc + binutils only.

## A/B run: executor prompts with and without diagrams (cvaccel, Haiku 4.5 as the test writer)
Same repository, same coverage gaps (gcov), same 7 tasks (1 add-tests, 6 raise-coverage), one run each.
| | A: cards only | B: cards + diagrams (auto rule) |
|---|---|---|
| words per first prompt, coverage tasks (mean) | 2,450 | 2,816 (diagrams 124–821 words) |
| attempts, all 7 tasks | 11 | 11 |
| first-attempt success | 4 of 7 | 5 of 7 |
| tasks DONE / PARTIAL | 6 / 1 | 7 / 0 |
| targeted missing outcomes closed | 13 of 19 | 11 of 19 |
| never-executed target functions now run | 3 of 3 | 3 of 3 |
| decision outcomes hit after the run (before: 137 of 148) | 155 of 160 | 158 of 164 |
One run on one codebase is a small sample: the differences are within what a second run could reverse, so the
diagrams have not earned their tokens in prompts yet. Both variants failed a build on the same cause, a test calling a
private method; cards now say `private (not callable from a test: reach it through a public caller)`.
