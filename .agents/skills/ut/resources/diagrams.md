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
