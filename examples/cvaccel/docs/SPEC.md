# cvaccel — CV accelerator service (SoC), architecture contract

The SoC has one hardware block with **5 cores**, one per execution type: RESIZE, CONVOLVE, WARP, HISTOGRAM, MATCH.
`libcvaccel` (the "base app") takes requests from client applications, queues them, forwards them to the block,
and when a job completes it wakes the client that posted it by an ioctl on that client's device fd.
`libcvclient` is the static library client applications link against; it talks to the service only through the
`os::IDevice` ioctl path (in-process simulation here, a kernel char device on the real SoC).

Client protocol (every call goes through the service facade, `CvAccelService::handle(clientFd, cmd, payload)`):
1. OPEN_SESSION(priority) → SessionId (max 16 sessions, one client may hold several)
2. ALLOC_MEM(session, bytes) → MemHandle (pool of 64 MiB, 64-byte aligned, first-fit; per-session accounting)
3. POST_CONFIG(session, mem, core, configWords[8]) → RequestId (queued; validates core, ownership, memory size)
4. the client fills the memory (simulated: writes through `MemoryPool::map`)
5. SUBMIT(request) → queued per core, priority order, FIFO within a priority
6. completion → `PerfMonitor::record` + `IDevice::ioctlToClient(clientFd, IOCTL_WAKE, CompletionInfo)`
7. FREE_MEM, CLOSE_SESSION (frees everything of the session; pending requests are cancelled with STATUS_CANCELLED)

Performance and integrity (PerfMonitor): per request: bytes used, t_queued, t_started, t_finished; per core and per
session: count, average and max latency, bytes; integrity checks: bytes <= allocated for that handle, timestamps
monotonic, every completion matches a submitted request; violations are counted and reported.

Rules: C++17, no exceptions across the API (Status codes), no dynamic polymorphism except the two hardware/OS
interfaces (`hw::IAccelBlock`, `os::IDevice`) which exist so that unit tests can mock them, thread-safe service
(one mutex; the sim hardware calls `onCompletion` from its own thread). No unit tests are written in this
repository on purpose: it is the greenfield fixture for the ut skill.
