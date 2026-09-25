# cvaccel

A simulated SoC service for a CV hardware accelerator block with 5 cores, one per execution type
(RESIZE, CONVOLVE, WARP, HISTOGRAM, MATCH). `libcvaccel` (the "base app") queues requests from
client applications per core in priority order, forwards them to the block, and wakes the posting
client with a completion ioctl when a job finishes. `libcvclient` is the static library client
applications link against; it talks to the service only through an `os::IDevice`-style ioctl
path — in-process here, a kernel char device on the real SoC. See `docs/SPEC.md` for the full
architecture contract.

## Directory layout

- `include/cvaccel/` — fixed contract headers; `src/` — the `CvAccelService` implementation.
- `client/include/cvclient/`, `client/src/cvclient.cpp` — client contract header and `libcvclient`.
- `sim/` — in-process simulation: `SimAccelBlock`, `SimDevice` (pool, clock, wake-ups), `SimTransport`.
- `apps/demo_app.cpp` — integration demo across all 5 cores. `scripts/coverage.sh` — coverage build.

## Build

```sh
cmake -S . -B build -DCMAKE_EXPORT_COMPILE_COMMANDS=ON
cmake --build build -j
./build/demo_app
```

## Linking a client application

A client application links against `libcvclient` (plus `libcvsim`/`libcvaccel` for the
simulation) and includes only `client/include/cvclient/cvclient.hpp` and
`include/cvaccel/types.hpp`:

```cmake
target_link_libraries(my_app PRIVATE cvclient cvsim cvaccel Threads::Threads)
```

It constructs an `ITransport` (`SimTransport` in-process, the real device transport on the SoC),
wraps it in a `cvclient::Client`, and drives `openSession`/`allocMem`/`postConfig`/`submit`/
`wait`/`freeMem`/`closeSession`.

## Unit-test policy

No unit tests are committed here on purpose — this is the greenfield fixture for the `ut` skill.
Tests will be added later under `tests/` using CppUTest, built via `-DBUILD_UNIT_TESTS=ON`
(`CMakeLists.txt` already wires up `add_subdirectory(tests)`, waiting for that directory).
Coverage is measured with Testwell CTC++, the project's coverage tool, via `scripts/coverage.sh`,
which falls back to gcov/gcovr when `ctcwrap` is not installed.

## ioctl protocol

| `IoctlCmd`      | Args struct        |
|-----------------|---------------------|
| `OPEN_SESSION`  | `OpenSessionArgs`   |
| `CLOSE_SESSION` | `SubmitArgs` (only `.session` read) |
| `ALLOC_MEM`     | `AllocMemArgs`      |
| `FREE_MEM`      | `FreeMemArgs`       |
| `POST_CONFIG`   | `PostConfigArgs`    |
| `SUBMIT`        | `SubmitArgs`        |
| `GET_STATS`     | `GetStatsArgs`      |
| `WAKE` (service → client) | `CompletionInfo` |
