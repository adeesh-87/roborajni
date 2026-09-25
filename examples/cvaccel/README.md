# cvaccel

A simulated SoC service for a CV hardware accelerator block with 5 cores, one per execution type
(RESIZE, CONVOLVE, WARP, HISTOGRAM, MATCH). `libcvaccel` (the "base app") takes requests from
client applications, queues them per core in priority order, forwards them to the block, and
wakes the posting client with a completion ioctl when a job finishes. `libcvclient` is the static
library client applications link against; it talks to the service only through an
`os::IDevice`-style ioctl path — an in-process simulation here, a kernel char device on the real
SoC. See `docs/SPEC.md` for the full architecture contract.

## Directory layout

- `include/cvaccel/` — fixed contract headers (types, service facade, hardware/OS interfaces,
  session/memory/queue/dispatcher/perf components).
- `src/` — the service implementation (`CvAccelService` and its components).
- `client/include/cvclient/` — the fixed client-facing contract header.
- `client/src/cvclient.cpp` — the `libcvclient` implementation.
- `sim/` — the in-process simulation: `SimAccelBlock` (worker thread per core), `SimDevice` (pool
  memory, clock, wake-up delivery), `SimTransport` (binds a client to a service instance).
- `apps/demo_app.cpp` — integration demo: client threads open sessions, allocate memory, post and
  submit requests across all 5 cores, and wait for completions.
- `scripts/coverage.sh` — coverage build (see below).

## Build

```sh
cmake -S . -B build -DCMAKE_EXPORT_COMPILE_COMMANDS=ON
cmake --build build -j
./build/demo_app
```

This builds `libcvaccel`, `libcvsim`, `libcvclient`, and the `demo_app` executable.

## Linking a client application

A client application links against `libcvclient` (and, for the simulation, `libcvsim` and
`libcvaccel`) and includes only `client/include/cvclient/cvclient.hpp` plus
`include/cvaccel/types.hpp`:

```cmake
target_link_libraries(my_app PRIVATE cvclient cvsim cvaccel Threads::Threads)
```

It constructs an `ITransport` (a `cvaccel::sim::SimTransport` in-process, or the real device
transport on the SoC), wraps it in a `cvclient::Client`, and drives the protocol: `openSession`,
`allocMem`, `postConfig`, `submit`, `wait`, `freeMem`, `closeSession`.

## Unit-test policy

No unit tests are committed to this repository on purpose — it is the greenfield fixture for the
`ut` skill. Tests will be added later under `tests/` using CppUTest, built via
`-DBUILD_UNIT_TESTS=ON` (`add_subdirectory(tests)` is already wired up in `CMakeLists.txt` and
waits for that directory to exist). Coverage is measured with Testwell CTC++, the project's
coverage tool, via `scripts/coverage.sh`; the same script falls back to gcov/gcovr when `ctcwrap`
is not installed on the machine.

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
