# Cards for src/session_manager.cpp (4 functions)

## SessionManager::open  (src/session_manager.cpp:5-20)
Signature: Status SessionManager::open(ClientFd clientFd, Priority prio, SessionId& outId)
Params: clientFd (ClientFd clientFd); prio (Priority prio); outId (SessionId& outId)
Decisions (drive each outcome; loops: 0, 1, many):
  L6     for      (unsigned i = 0; i < kMaxSessions; ++i)
  L8     if       (!s.active)
Returns: Status::OK | Status::NO_MEMORY
Callers: CvAccelService::openSession() (src/service.cpp)
Existing tests calling it directly: TEST(Dispatcher, CancelSession_L133_SessionFound_WakesUsingSessionClientFd) (tests/dispatcher_test.cpp:L632); TEST(Dispatcher, CancelSession_L136_ClientFdInvalid_NoWake) (tests/dispatcher_test.cpp:L695); TEST(Dispatcher, CancelSession_L136_ClientFdValid_SendsWake) (tests/dispatcher_test.cpp:L674); TEST(Dispatcher, CancelSession_L145_OpenRequestsPositive_Decrements) (tests/dispatcher_test.cpp:L717); TEST(Dispatcher, CancelSession_L145_OpenRequestsZero_NoUnderflow) (tests/dispatcher_test.cpp:L740); TEST(Dispatcher, OnCompletion_L107_SessionFoundWithOpenRequests_DecrementsOpenRequests) (tests/dispatcher_test.cpp:L510); TEST(Dispatcher, OnCompletion_L107_SessionFoundWithZeroOpenRequests_StaysZero) (tests/dispatcher_test.cpp:L563); TEST(SessionManager, Close_SessionFound_ReturnsOkAndClearsSlot) (tests/session_manager_test.cpp:L81)

## SessionManager::close  (src/session_manager.cpp:22-27)
Signature: Status SessionManager::close(SessionId id)
Params: id (SessionId id)
Decisions (drive each outcome; loops: 0, 1, many):
  L24    if       (!s)
Returns: Status::NO_SESSION | Status::OK
Calls: SessionManager::find() (src/session_manager.cpp:L36)
Callers: CvAccelService::closeSession() (src/service.cpp)
Existing tests calling it directly: TEST(SessionManager, Close_SessionFound_ReturnsOkAndClearsSlot) (tests/session_manager_test.cpp:L81); TEST(SessionManager, Close_SessionNotFound_ReturnsNoSession) (tests/session_manager_test.cpp:L73)

## SessionManager::find  (src/session_manager.cpp:29-34)
Signature: SessionInfo* SessionManager::find(SessionId id)
Params: id (SessionId id)
Decisions (drive each outcome; loops: 0, 1, many):
  L30    if       (id == 0 || id > kMaxSessions) [2 sub-conditions: each must flip the outcome alone]
  L32    if       (!s.active || s.id != id) [2 sub-conditions: each must flip the outcome alone]
Returns: nullptr | &s
Callers: SessionManager::close() (src/session_manager.cpp); SessionManager::owns() (src/session_manager.cpp)
Existing tests calling it directly: TEST(Dispatcher, CancelSession_L145_OpenRequestsPositive_Decrements) (tests/dispatcher_test.cpp:L717); TEST(Dispatcher, CancelSession_L145_OpenRequestsZero_NoUnderflow) (tests/dispatcher_test.cpp:L740); TEST(Dispatcher, OnCompletion_L107_SessionFoundWithOpenRequests_DecrementsOpenRequests) (tests/dispatcher_test.cpp:L510); TEST(Dispatcher, OnCompletion_L107_SessionFoundWithZeroOpenRequests_StaysZero) (tests/dispatcher_test.cpp:L563); TEST(SessionManager, Close_SessionFound_ReturnsOkAndClearsSlot) (tests/session_manager_test.cpp:L81); TEST(SessionManager, Find_IdEqualsKMaxSessions_PassesRangeCheck) (tests/session_manager_test.cpp:L101); TEST(SessionManager, Find_IdOutOfRange_ReturnsNullptr) (tests/session_manager_test.cpp:L93); TEST(SessionManager, Find_SlotActiveWithMatchingId_ReturnsPointer) (tests/session_manager_test.cpp:L117)

## SessionManager::owns  (src/session_manager.cpp:43-46)
Signature: bool SessionManager::owns(SessionId id, ClientFd clientFd) const
Params: id (SessionId id); clientFd (ClientFd clientFd)
Decisions: none (straight-line code)
Returns: s != nullptr && s->clientFd == clientFd
Calls: SessionManager::find() (src/session_manager.cpp:L36)
Callers: CvAccelService::allocMem() (src/service.cpp); CvAccelService::closeSession() (src/service.cpp); CvAccelService::freeMem() (src/service.cpp); CvAccelService::getStats() (src/service.cpp); CvAccelService::postConfig() (src/service.cpp); CvAccelService::submit() (src/service.cpp)
Existing tests calling it directly: TEST(SessionManager, Owns_TypicalInputs_MatchesFindAndClientFd) (tests/session_manager_test.cpp:L130)
# dependencies of src/session_manager.cpp  (mock/stub candidates first; 'in-scope code' = another scanned file, often an existing mock)
