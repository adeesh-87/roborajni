# Cards for src/dispatcher.cpp (6 functions)

## blockBytesOf  (src/dispatcher.cpp:8-11)
Signature: uint32_t blockBytesOf(const MemoryPool& pool, MemHandle h)
Params: pool (const MemoryPool& pool); h (MemHandle h)
Decisions (drive each outcome; loops: 0, 1, many):
  L10    ?:       blk
Returns: blk ? static_cast<uint32_t>(blk->bytes) : 0
Calls: MemoryPool::find() (src/memory_pool.cpp:L59)
Callers: Dispatcher::onCompletion() (src/dispatcher.cpp); Dispatcher::pump() (src/dispatcher.cpp)
Existing tests calling it directly: none

## Dispatcher::Dispatcher  (src/dispatcher.cpp:14-16)
Signature: Dispatcher::Dispatcher(hw::IAccelBlock& hw, os::IDevice& dev, RequestQueue& q, MemoryPool& pool, SessionManager& sm, PerfMonitor& perf) :...
Params: hw (hw::IAccelBlock& hw); dev (os::IDevice& dev); q (RequestQueue& q); pool (MemoryPool& pool); sm (SessionManager& sm); perf (PerfMonitor& perf)
Decisions: none (straight-line code)
Existing tests calling it directly: none

## Dispatcher::start  (src/dispatcher.cpp:18-32)
Signature: Status Dispatcher::start(Request& r)
Params: r (Request& r)
Decisions (drive each outcome; loops: 0, 1, many):
  L24    for      (unsigned i = 0; i < kConfigWords; ++i) job.config[i] = r.config[i];
  L27    if       (st == Status::OK)
Returns: st
Calls: FakeDevice::nowNs() (tests/dispatcher_test.cpp:L32); MemoryPool::physAddr() (src/memory_pool.cpp:L64)
Callers: Dispatcher::pump() (src/dispatcher.cpp)
Existing tests calling it directly: none

## Dispatcher::pump  (src/dispatcher.cpp:34-86)
Signature: unsigned Dispatcher::pump()
Decisions (drive each outcome; loops: 0, 1, many):
  L36    for      (unsigned c = 0; c < kCoreCount; ++c)
  L38    while    (!hw_.isBusy(core))
  L40    if       (!queue_.dequeue(core, r))
  L43    if       (st == Status::OK)
  L47    if       (st == Status::BUSY)
  L75    if       (r.clientFd != -1)
  L82    if       (si && si->openRequests > 0) [2 sub-conditions: each must flip the outcome alone]
Returns: started
Calls: Dispatcher::start() (src/dispatcher.cpp:L18); FakeAccelBlock::isBusy() (tests/dispatcher_test.cpp:L16); FakeDevice::ioctlToClient() (tests/dispatcher_test.cpp:L28); FakeDevice::nowNs() (tests/dispatcher_test.cpp:L32); PerfMonitor::record() (src/perf_monitor.cpp:L32); RequestQueue::dequeue() (src/request_queue.cpp:L27); RequestQueue::enqueue() (src/request_queue.cpp:L13); blockBytesOf() (src/dispatcher.cpp:L8)
Existing tests calling it directly: none

## Dispatcher::onCompletion  (src/dispatcher.cpp:88-126)
Signature: Status Dispatcher::onCompletion(const hw::JobResult& res)
Params: res (const hw::JobResult& res)
Decisions (drive each outcome; loops: 0, 1, many):
  L90    if       (it == running_.end())
  L107   if       (si && si->openRequests > 0) [2 sub-conditions: each must flip the outcome alone]
  L111   if       (r.clientFd != -1)
Returns: Status::INVALID_ARG | Status::OK
Calls: FakeDevice::ioctlToClient() (tests/dispatcher_test.cpp:L28); FakeDevice::nowNs() (tests/dispatcher_test.cpp:L32); PerfMonitor::record() (src/perf_monitor.cpp:L32); blockBytesOf() (src/dispatcher.cpp:L8)
Callers: CvAccelService::onHwCompletion() (src/service.cpp)
Existing tests calling it directly: TEST(Dispatcher, CancelSession_L150_RunningJobDifferentSession_ClientFdUnaffected) (tests/dispatcher_test.cpp:L787); TEST(Dispatcher, CancelSession_L150_RunningJobMatchesSession_CompletionSilenced) (tests/dispatcher_test.cpp:L762); TEST(Dispatcher, OnCompletion_L107_SessionFoundWithOpenRequests_DecrementsOpenRequests) (tests/dispatcher_test.cpp:L510); TEST(Dispatcher, OnCompletion_L107_SessionFoundWithZeroOpenRequests_StaysZero) (tests/dispatcher_test.cpp:L563); TEST(Dispatcher, OnCompletion_L107_SessionNotFound_StillErasesRunningAndReturnsOk) (tests/dispatcher_test.cpp:L539); TEST(Dispatcher, OnCompletion_L111_ClientFdInvalid_DoesNotWakeClient) (tests/dispatcher_test.cpp:L611); TEST(Dispatcher, OnCompletion_L111_ClientFdSet_WakesClient) (tests/dispatcher_test.cpp:L590); TEST(Dispatcher, OnCompletion_L90_JobIdInRunning_ErasesFromRunningAndReturnsOk) (tests/dispatcher_test.cpp:L488)

## Dispatcher::cancelSession  (src/dispatcher.cpp:128-154)
Signature: unsigned Dispatcher::cancelSession(SessionId session)
Params: session (SessionId session)
Decisions (drive each outcome; loops: 0, 1, many):
  L133   ?:       si
  L136   if       (fd != -1)
  L145   if       (si && si->openRequests > 0) [2 sub-conditions: each must flip the outcome alone]
  L150   if       (kv.second.session == session)
Returns: static_cast<unsigned>(removed.size())
Calls: FakeDevice::ioctlToClient() (tests/dispatcher_test.cpp:L28)
Existing tests calling it directly: none
# dependencies of src/dispatcher.cpp  (mock/stub candidates first; 'in-scope code' = another scanned file, often an existing mock)

## in-scope code
- FakeAccelBlock::isBusy()  [defined in tests/dispatcher_test.cpp:L16]  called by: Dispatcher::pump() @ src/dispatcher.cpp:L38
- FakeDevice::ioctlToClient()  [defined in tests/dispatcher_test.cpp:L28]  called by: Dispatcher::cancelSession() @ src/dispatcher.cpp:L143; Dispatcher::onCompletion() @ src/dispatcher.cpp:L121; Dispatcher::pump() @ src/dispatcher.cpp:L78
- FakeDevice::nowNs()  [defined in tests/dispatcher_test.cpp:L32]  called by: Dispatcher::onCompletion() @ src/dispatcher.cpp:L101; Dispatcher::pump() @ src/dispatcher.cpp:L55; Dispatcher::start() @ src/dispatcher.cpp:L28
- MemoryPool::find()  [defined in src/memory_pool.cpp:L59]  called by: blockBytesOf() @ src/dispatcher.cpp:L9
- MemoryPool::physAddr()  [defined in src/memory_pool.cpp:L64]  called by: Dispatcher::start() @ src/dispatcher.cpp:L22
- PerfMonitor::record()  [defined in src/perf_monitor.cpp:L32]  called by: Dispatcher::onCompletion() @ src/dispatcher.cpp:L104; Dispatcher::pump() @ src/dispatcher.cpp:L67
- RequestQueue::dequeue()  [defined in src/request_queue.cpp:L27]  called by: Dispatcher::pump() @ src/dispatcher.cpp:L40
- RequestQueue::enqueue()  [defined in src/request_queue.cpp:L13]  called by: Dispatcher::pump() @ src/dispatcher.cpp:L50
