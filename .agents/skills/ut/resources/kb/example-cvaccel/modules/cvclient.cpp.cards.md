# Cards for client/src/cvclient.cpp (9 functions)

## Client::Client  (client/src/cvclient.cpp:20-26)
Signature: Client::Client(ITransport& t) : impl_(new Impl), t_(t)
Params: t (ITransport& t)
Decisions: none (straight-line code)
Calls: FakeTransport::setWakeHandler() (tests/cvclient_test.cpp:L11)
Existing tests calling it directly: none

## Client::openSession  (client/src/cvclient.cpp:33-38)
Signature: Status Client::openSession(Priority prio)
Params: prio (Priority prio)
Decisions (drive each outcome; loops: 0, 1, many):
  L36    if       (s == Status::OK)
Returns: s
Calls: FakeTransport::ioctl() (tests/cvclient_test.cpp:L10)
Existing tests calling it directly: none

## Client::closeSession  (client/src/cvclient.cpp:40-46)
Signature: Status Client::closeSession()
Decisions (drive each outcome; loops: 0, 1, many):
  L41    if       (session_ == 0)
Returns: Status::NO_SESSION | s
Calls: FakeTransport::ioctl() (tests/cvclient_test.cpp:L10)
Existing tests calling it directly: none

## Client::allocMem  (client/src/cvclient.cpp:48-54)
Signature: Status Client::allocMem(uint32_t bytes, MemHandle& out)
Params: bytes (uint32_t bytes); out (MemHandle& out)
Decisions (drive each outcome; loops: 0, 1, many):
  L49    if       (session_ == 0)
  L52    if       (s == Status::OK)
Returns: Status::NO_SESSION | s
Calls: FakeTransport::ioctl() (tests/cvclient_test.cpp:L10)
Existing tests calling it directly: none

## Client::freeMem  (client/src/cvclient.cpp:56-60)
Signature: Status Client::freeMem(MemHandle h)
Params: h (MemHandle h)
Decisions (drive each outcome; loops: 0, 1, many):
  L57    if       (session_ == 0)
Returns: Status::NO_SESSION | t_.ioctl(IoctlCmd::FREE_MEM, &a, sizeof a)
Calls: FakeTransport::ioctl() (tests/cvclient_test.cpp:L10)
Existing tests calling it directly: none

## Client::postConfig  (client/src/cvclient.cpp:62-74)
Signature: Status Client::postConfig(MemHandle mem, CoreType core, uint32_t bytes, const uint32_t config[kConfigWords], RequestId& out)
Params: mem (MemHandle mem); core (CoreType core); bytes (uint32_t bytes); config (const uint32_t config[kConfigWords]); out (RequestId& out)
Decisions (drive each outcome; loops: 0, 1, many):
  L64    if       (session_ == 0)
  L70    for      (unsigned i = 0; i < kConfigWords; ++i) a.config[i] = config[i];
  L72    if       (s == Status::OK)
Returns: Status::NO_SESSION | s
Calls: FakeTransport::ioctl() (tests/cvclient_test.cpp:L10)
Existing tests calling it directly: none

## Client::submit  (client/src/cvclient.cpp:76-80)
Signature: Status Client::submit(RequestId r)
Params: r (RequestId r)
Decisions (drive each outcome; loops: 0, 1, many):
  L77    if       (session_ == 0)
Returns: Status::NO_SESSION | t_.ioctl(IoctlCmd::SUBMIT, &a, sizeof a)
Calls: FakeTransport::ioctl() (tests/cvclient_test.cpp:L10)
Existing tests calling it directly: none

## Client::wait  (client/src/cvclient.cpp:82-98)
Signature: Status Client::wait(RequestId r, Completion& out, uint32_t timeoutMs)
Params: r (RequestId r); out (Completion& out); timeoutMs (uint32_t timeoutMs)
Decisions (drive each outcome; loops: 0, 1, many):
  L85    if       (it != impl_->completions.end())
  L94    if       (!got)
Returns: Status::OK | it != impl_->completions.end() | Status::BUSY
Existing tests calling it directly: none

## Client::getStats  (client/src/cvclient.cpp:100-112)
Signature: Status Client::getStats(uint64_t& count, uint64_t& avgLatencyNs, uint64_t& bytes, uint64_t& integrityErrors)
Params: count (uint64_t& count); avgLatencyNs (uint64_t& avgLatencyNs); bytes (uint64_t& bytes); integrityErrors (uint64_t& integrityErrors)
Decisions (drive each outcome; loops: 0, 1, many):
  L101   if       (session_ == 0)
  L105   if       (s == Status::OK)
Returns: Status::NO_SESSION | s
Calls: FakeTransport::ioctl() (tests/cvclient_test.cpp:L10)
Existing tests calling it directly: none
# dependencies of client/src/cvclient.cpp  (mock/stub candidates first; 'in-scope code' = another scanned file, often an existing mock)

## in-scope code
- FakeTransport::ioctl()  [defined in tests/cvclient_test.cpp:L10]  called by: Client::allocMem() @ client/src/cvclient.cpp:L51; Client::closeSession() @ client/src/cvclient.cpp:L43; Client::freeMem() @ client/src/cvclient.cpp:L59; Client::getStats() @ client/src/cvclient.cpp:L104 ...
- FakeTransport::setWakeHandler()  [defined in tests/cvclient_test.cpp:L11]  called by: Client::Client() @ client/src/cvclient.cpp:L21
