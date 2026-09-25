# Cards for src/service.cpp (13 functions)

## CvAccelService::CvAccelService  (src/service.cpp:6-12)
Signature: CvAccelService::CvAccelService(hw::IAccelBlock& hw, os::IDevice& dev) : hw_(hw), dev_(dev), pool_(kPoolBytes, dev.poolPhysBase(), dev.poo...
Params: hw (hw::IAccelBlock& hw); dev (os::IDevice& dev)
Decisions: none (straight-line code)
Calls: CvAccelService::onHwCompletion() (src/service.cpp:L144); FakeAccelBlock::setCompletionHandler() (tests/dispatcher_test.cpp:L17)
Existing tests calling it directly: none

## CvAccelService::handle  (src/service.cpp:18-47)
Signature: Status CvAccelService::handle(ClientFd clientFd, IoctlCmd cmd, void* payload, size_t payloadBytes)
Params: clientFd (ClientFd clientFd); cmd (IoctlCmd cmd); payload (void* payload); payloadBytes (size_t payloadBytes)
Decisions (drive each outcome; loops: 0, 1, many):
  L19    if       (payload == nullptr)
  L21    switch   (cmd) cases: IoctlCmd::OPEN_SESSION, IoctlCmd::CLOSE_SESSION, IoctlCmd::ALLOC_MEM, IoctlCmd::FREE_MEM, IoctlCmd::POST_CONFIG, IoctlCmd::SUBMIT, IoctlCmd::GET_STATS, IoctlCmd::WAKE + default
  L23    if       (payloadBytes < sizeof(OpenSessionArgs))
  L26    if       (payloadBytes < sizeof(SessionId))
  L29    if       (payloadBytes < sizeof(AllocMemArgs))
  L32    if       (payloadBytes < sizeof(FreeMemArgs))
  L35    if       (payloadBytes < sizeof(PostConfigArgs))
  L38    if       (payloadBytes < sizeof(SubmitArgs))
  L41    if       (payloadBytes < sizeof(GetStatsArgs))
Returns: Status::INVALID_ARG | openSession(clientFd, *static_cast<OpenSessionA... | closeSession(clientFd, *static_cast<SessionId*>... | allocMem(clientFd, *static_cast<AllocMemArgs*>(... | freeMem(clientFd, *static_cast<FreeMemArgs*>(pa... | postConfig(clientFd, *static_cast<PostConfigArg... | submit(clientFd, *static_cast<SubmitArgs*>(payl... | getStats(clientFd, *static_cast<GetStatsArgs*>(...
Calls: CvAccelService::allocMem() (src/service.cpp:L67); CvAccelService::closeSession() (src/service.cpp:L56); CvAccelService::freeMem() (src/service.cpp:L77); CvAccelService::getStats() (src/service.cpp:L127); CvAccelService::openSession() (src/service.cpp:L49); CvAccelService::postConfig() (src/service.cpp:L89); CvAccelService::submit() (src/service.cpp:L111)
Existing tests calling it directly: TEST(CvAccelService, AllocMem_L68OwnsFalse_ReturnsNotOwner) (tests/service_test.cpp:L561); TEST(CvAccelService, AllocMem_L68OwnsTrue_ProceedsPastOwnershipCheck) (tests/service_test.cpp:L580); TEST(CvAccelService, AllocMem_L71StNotOk_ReturnsSt) (tests/service_test.cpp:L600); TEST(CvAccelService, AllocMem_L71StOk_SetsOutHandleAndReturnsOk) (tests/service_test.cpp:L619); TEST(CvAccelService, AllocMem_L73SessionFound_IncrementsBytesAllocated) (tests/service_test.cpp:L639); TEST(CvAccelService, ClientDisconnected_TypicalClient_ClosesAllItsSessions) (tests/service_test.cpp:L1522); TEST(CvAccelService, CloseSession_L57NotOwner_ReturnsNotOwner) (tests/service_test.cpp:L347); TEST(CvAccelService, CloseSession_L57Owner_ProceedsPastOwnershipCheck) (tests/service_test.cpp:L362)

## CvAccelService::openSession  (src/service.cpp:49-54)
Signature: Status CvAccelService::openSession(ClientFd fd, OpenSessionArgs& a)
Params: fd (ClientFd fd); a (OpenSessionArgs& a)
Decisions (drive each outcome; loops: 0, 1, many):
  L52    if       (st == Status::OK)
Returns: st
Calls: SessionManager::open() (src/session_manager.cpp:L5)
Callers: CvAccelService::handle() (src/service.cpp)
Existing tests calling it directly: none

## CvAccelService::closeSession  (src/service.cpp:56-65)
Signature: Status CvAccelService::closeSession(ClientFd fd, SessionId s)
Params: fd (ClientFd fd); s (SessionId s)
Decisions (drive each outcome; loops: 0, 1, many):
  L57    if       (!sessions_.owns(s, fd))
  L59    for      (auto it = posted_.begin(); it != posted_.end();)
  L60    if       (it->second.session == s) (has else)
Returns: Status::NOT_OWNER | sessions_.close(s)
Calls: MemoryPool::releaseAll() (src/memory_pool.cpp:L53); SessionManager::close() (src/session_manager.cpp:L22); SessionManager::owns() (src/session_manager.cpp:L43)
Callers: CvAccelService::clientDisconnected() (src/service.cpp); CvAccelService::handle() (src/service.cpp)
Existing tests calling it directly: none

## CvAccelService::allocMem  (src/service.cpp:67-75)
Signature: Status CvAccelService::allocMem(ClientFd fd, AllocMemArgs& a)
Params: fd (ClientFd fd); a (AllocMemArgs& a)
Decisions (drive each outcome; loops: 0, 1, many):
  L68    if       (!sessions_.owns(a.session, fd))
  L71    if       (st != Status::OK)
  L73    if       (SessionInfo* si = sessions_.find(a.session))
Returns: Status::NOT_OWNER | st | Status::OK
Calls: MemoryPool::allocate() (src/memory_pool.cpp:L15); SessionManager::owns() (src/session_manager.cpp:L43)
Callers: CvAccelService::handle() (src/service.cpp)
Existing tests calling it directly: none

## CvAccelService::freeMem  (src/service.cpp:77-87)
Signature: Status CvAccelService::freeMem(ClientFd fd, FreeMemArgs& a)
Params: fd (ClientFd fd); a (FreeMemArgs& a)
Decisions (drive each outcome; loops: 0, 1, many):
  L78    if       (!sessions_.owns(a.session, fd))
  L80    ?:       blk
  L82    if       (st != Status::OK)
  L83    if       (SessionInfo* si = sessions_.find(a.session))
  L84    ?:       (bytes <= si->bytesAllocated)
Returns: Status::NOT_OWNER | st | Status::OK
Calls: MemoryPool::release() (src/memory_pool.cpp:L42); SessionManager::owns() (src/session_manager.cpp:L43)
Callers: CvAccelService::handle() (src/service.cpp)
Existing tests calling it directly: none

## CvAccelService::postConfig  (src/service.cpp:89-109)
Signature: Status CvAccelService::postConfig(ClientFd fd, PostConfigArgs& a)
Params: fd (ClientFd fd); a (PostConfigArgs& a)
Decisions (drive each outcome; loops: 0, 1, many):
  L90    if       (!sessions_.owns(a.session, fd))
  L91    if       (static_cast<unsigned>(a.core) >= kCoreCount)
  L93    if       (!blk || blk->owner != a.session) [2 sub-conditions: each must flip the outcome alone]
  L94    if       (a.bytes == 0 || a.bytes > blk->bytes) [2 sub-conditions: each must flip the outcome alone]
  L102   if       (const SessionInfo* si = sessions_.find(a.session))
  L103   for      (unsigned i = 0; i < kConfigWords; ++i) r.config[i] = a.config[i];
Returns: Status::NOT_OWNER | Status::INVALID_ARG | Status::OK
Calls: SessionManager::owns() (src/session_manager.cpp:L43)
Callers: CvAccelService::handle() (src/service.cpp)
Existing tests calling it directly: none

## CvAccelService::submit  (src/service.cpp:111-125)
Signature: Status CvAccelService::submit(ClientFd fd, SubmitArgs& a)
Params: fd (ClientFd fd); a (SubmitArgs& a)
Decisions (drive each outcome; loops: 0, 1, many):
  L113   if       (it == posted_.end())
  L114   if       (it->second.session != a.session || !sessions_.owns(a.session, fd)) [2 sub-conditions: each must flip the outcome alone]
  L118   if       (st != Status::OK)
  L121   if       (SessionInfo* si = sessions_.find(a.session))
Returns: Status::INVALID_ARG | Status::NOT_OWNER | st | Status::OK
Calls: FakeDevice::nowNs() (tests/dispatcher_test.cpp:L32); RequestQueue::enqueue() (src/request_queue.cpp:L13); SessionManager::owns() (src/session_manager.cpp:L43)
Callers: CvAccelService::handle() (src/service.cpp)
Existing tests calling it directly: none

## CvAccelService::getStats  (src/service.cpp:127-135)
Signature: Status CvAccelService::getStats(ClientFd fd, GetStatsArgs& a)
Params: fd (ClientFd fd); a (GetStatsArgs& a)
Decisions (drive each outcome; loops: 0, 1, many):
  L128   if       (!sessions_.owns(a.session, fd))
Returns: Status::NOT_OWNER | Status::OK
Calls: PerfMonitor::session() (src/perf_monitor.cpp:L46); SessionManager::owns() (src/session_manager.cpp:L43)
Callers: CvAccelService::handle() (src/service.cpp)
Existing tests calling it directly: none

## CvAccelService::clientDisconnected  (src/service.cpp:137-142)
Signature: void CvAccelService::clientDisconnected(ClientFd clientFd)
Params: clientFd (ClientFd clientFd)
Decisions: none (straight-line code)
Calls: CvAccelService::closeSession() (src/service.cpp:L56)
Existing tests calling it directly: TEST(CvAccelService, ClientDisconnected_TypicalClient_ClosesAllItsSessions) (tests/service_test.cpp:L1522)

## CvAccelService::onHwCompletion  (src/service.cpp:144-148)
Signature: void CvAccelService::onHwCompletion(const hw::JobResult& res)
Params: res (const hw::JobResult& res)
Decisions: none (straight-line code)
Calls: Dispatcher::onCompletion() (src/dispatcher.cpp:L88)
Callers: CvAccelService::CvAccelService() (src/service.cpp)
Existing tests calling it directly: TEST(CvAccelService, OnHwCompletion_TypicalCompletion_RecordsAndWakesClient) (tests/service_test.cpp:L1545)

## CvAccelService::pump  (src/service.cpp:150-153)
Signature: unsigned CvAccelService::pump()
Decisions: none (straight-line code)
Returns: dispatcher_.pump()
Existing tests calling it directly: none

## CvAccelService::queued  (src/service.cpp:155-158)
Signature: unsigned CvAccelService::queued() const
Decisions: none (straight-line code)
Returns: queue_.sizeTotal()
Calls: RequestQueue::sizeTotal() (src/request_queue.cpp:L52)
Existing tests calling it directly: TEST(CvAccelService, Queued_TypicalPendingRequest_ReturnsQueueSizeTotal) (tests/service_test.cpp:L1625)
# dependencies of src/service.cpp  (mock/stub candidates first; 'in-scope code' = another scanned file, often an existing mock)

## in-scope code
- Dispatcher::onCompletion()  [defined in src/dispatcher.cpp:L88]  called by: CvAccelService::onHwCompletion() @ src/service.cpp:L146
- FakeAccelBlock::setCompletionHandler()  [defined in tests/dispatcher_test.cpp:L17]  called by: CvAccelService::CvAccelService() @ src/service.cpp:L11
- FakeDevice::nowNs()  [defined in tests/dispatcher_test.cpp:L32]  called by: CvAccelService::submit() @ src/service.cpp:L116
- MemoryPool::allocate()  [defined in src/memory_pool.cpp:L15]  called by: CvAccelService::allocMem() @ src/service.cpp:L70
- MemoryPool::release()  [defined in src/memory_pool.cpp:L42]  called by: CvAccelService::freeMem() @ src/service.cpp:L81
- MemoryPool::releaseAll()  [defined in src/memory_pool.cpp:L53]  called by: CvAccelService::closeSession() @ src/service.cpp:L63
- PerfMonitor::session()  [defined in src/perf_monitor.cpp:L46]  called by: CvAccelService::getStats() @ src/service.cpp:L129
- RequestQueue::enqueue()  [defined in src/request_queue.cpp:L13]  called by: CvAccelService::submit() @ src/service.cpp:L117
- RequestQueue::sizeTotal()  [defined in src/request_queue.cpp:L52]  called by: CvAccelService::queued() @ src/service.cpp:L157
- SessionManager::close()  [defined in src/session_manager.cpp:L22]  called by: CvAccelService::closeSession() @ src/service.cpp:L64
- SessionManager::open()  [defined in src/session_manager.cpp:L5]  called by: CvAccelService::openSession() @ src/service.cpp:L51
- SessionManager::owns()  [defined in src/session_manager.cpp:L43]  called by: CvAccelService::allocMem() @ src/service.cpp:L68; CvAccelService::closeSession() @ src/service.cpp:L57; CvAccelService::freeMem() @ src/service.cpp:L78; CvAccelService::getStats() @ src/service.cpp:L128 ...
