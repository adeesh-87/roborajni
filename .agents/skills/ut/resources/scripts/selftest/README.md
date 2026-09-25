Self-test fixture for `scripts/index.sh selftest [clang|gcc|graphify|all]` and `scripts/graphify.sh selftest`
(embedded-style C + C++, no test framework needed). Known answers checked for every backend: STATIC helpers, external
crc16, active `#if` variant only, macro-made calls, function-pointer targets (designated/positional initializers,
registered callback), C++ interface calls, per-TEST nodes, line mapping, and the outline (switch cases, call order).
