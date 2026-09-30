# Coverage gaps (gcov-dir, 2026-09-25 09:54): 137/148 decision outcomes hit

## Functions never executed by the tests
- IAccelBlock::coreCount (examples/cvaccel/include/cvaccel/hw_block.hpp:31)
- Client::openSession (examples/cvaccel/client/src/cvclient.cpp:33)
- Client::closeSession (examples/cvaccel/client/src/cvclient.cpp:40)
- Client::allocMem (examples/cvaccel/client/src/cvclient.cpp:48)
- Client::freeMem (examples/cvaccel/client/src/cvclient.cpp:56)
- Client::postConfig (examples/cvaccel/client/src/cvclient.cpp:62)
- Client::submit (examples/cvaccel/client/src/cvclient.cpp:76)
- Client::wait (examples/cvaccel/client/src/cvclient.cpp:82)
- Client::wait.lambda@90 (examples/cvaccel/client/src/cvclient.cpp:90)
- Client::getStats (examples/cvaccel/client/src/cvclient.cpp:100)
- MemoryPool::bytesInUse (examples/cvaccel/src/memory_pool.cpp:81)

## Decision outcomes never taken
- SessionManager::forEachOfClient (examples/cvaccel/include/cvaccel/session_manager.hpp:25): L25 if (s.active && s.clientFd == fd): only 5/6 branch outcomes hit
- Client::~Client (examples/cvaccel/client/src/cvclient.cpp:28): L29 if (session_ != 0) never TRUE
- Dispatcher::pump (examples/cvaccel/src/dispatcher.cpp:34): L82 if (si && si->openRequests > 0): only 1/4 branch outcomes hit
- MemoryPool::allocate (examples/cvaccel/src/memory_pool.cpp:15): L16 if (align == 0 || (align & (align - 1)) != 0): only 3/4 branch outcomes hit; L17 if (bytes == 0 || bytes > poolBytes_): only 3/4 branch outcomes hit
- MemoryPool::release (examples/cvaccel/src/memory_pool.cpp:42): L44 if (it->handle == h) never FALSE
- MemoryPool::map (examples/cvaccel/src/memory_pool.cpp:69): L71 if (!b || !virtBase_): only 3/4 branch outcomes hit
- CvAccelService::handle (examples/cvaccel/src/service.cpp:18): L29 if (payloadBytes < sizeof(AllocMemArgs)) never TRUE; L32 if (payloadBytes < sizeof(FreeMemArgs)) never TRUE; L35 if (payloadBytes < sizeof(PostConfigArgs)) never TRUE; L38 if (payloadBytes < sizeof(SubmitArgs)) never TRUE; L41 if (payloadBytes < sizeof(GetStatsArgs)) never TRUE
- CvAccelService::allocMem (examples/cvaccel/src/service.cpp:67): L73 if (si) never FALSE
- CvAccelService::freeMem (examples/cvaccel/src/service.cpp:77): L83 if (si) never FALSE
- CvAccelService::postConfig (examples/cvaccel/src/service.cpp:89): L93 if (!blk || blk->owner != a.session): only 3/4 branch outcomes hit; L94 if (a.bytes == 0 || a.bytes > blk->bytes): only 3/4 branch outcomes hit; L102 if (si) never FALSE
- CvAccelService::submit (examples/cvaccel/src/service.cpp:111): L114 if (it->second.session != a.session || !sessions_.owns(a.session, fd)): only 5/6 branch outcomes hit; L121 if (si) never FALSE
- SessionManager::find (examples/cvaccel/src/session_manager.cpp:29): L32 if (!s.active || s.id != id): only 3/4 branch outcomes hit
- SessionManager::find (examples/cvaccel/src/session_manager.cpp:36): L37 if (id == 0 || id > kMaxSessions): only 2/4 branch outcomes hit; L39 if (!s.active || s.id != id): only 3/4 branch outcomes hit
