# Unity + CMock + Ceedling — quick reference (C only): errors and fixes
## Errors and fixes
| Message | Fix |
|---------|-----|
| `Function x:Called more times than expected.` / `...fewer times...` | wrong number of Expect calls or wrong path |
| `Called earlier than expected` / `Called later than expected` | strict ordering is on and call order differs |
| `Function x Argument y:Function called with unexpected argument value.` | argument mismatch: fix the value, or `IgnoreArg_y` if the arg does not matter |
| `macro "x_ExpectWithArray..." passed 4 arguments, but takes just 3` | read the generated macro in `mock_*.h`; a size param may replace `_Depth` |
| `undefined reference` to a function of another module | add `#include "mock_other.h"` (or `other.h` for the real one) |
| `multiple definition` | test includes both `other.h` and `mock_other.h` sources: pick one |
| `x_ReturnThruPtr_...` undeclared | plugin `:return_thru_ptr` not enabled |
