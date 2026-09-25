%% Sequence of CvAccelService::clientDisconnected  examples/cvaccel/src/service.cpp:137-142  (callees expanded 1 level(s) deep)
%% Lnn = call site line. alt/opt/loop = the branch or loop around the calls. Participant notes name existing test doubles.
sequenceDiagram
  participant Caller as Caller (the test)
  participant CvAccelService as CvAccelService (class)
  participant SessionManager as SessionManager (class)
  participant f as function pointer f; may call CvAccelService::clientDisconnected.lambda@140
  participant Dispatcher as Dispatcher (class)
  participant MemoryPool as MemoryPool (class)
  Caller->>CvAccelService: CvAccelService::clientDisconnected()
  CvAccelService->>SessionManager: L140 sessions_.forEachOfClient()
  loop L25 for auto& s : sessions_
    opt L25 s.active && s.clientFd == fd
      SessionManager->>f: L25 f()
    end
  end
  loop L141 for SessionId id : ids
    CvAccelService->>CvAccelService: L141 closeSession()
    CvAccelService->>SessionManager: L57 sessions_.owns()
    CvAccelService->>Dispatcher: L58 dispatcher_.cancelSession()
    CvAccelService->>MemoryPool: L63 pool_.releaseAll()
    CvAccelService->>SessionManager: L64 sessions_.close()
  end
