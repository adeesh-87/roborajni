# Cards for src/request_queue.cpp (7 functions)

## higherOrEqualPriority  (src/request_queue.cpp:8-10)
Signature: bool higherOrEqualPriority(Priority a, Priority b)
Params: a (Priority a); b (Priority b)
Decisions: none (straight-line code)
Returns: static_cast<uint8_t>(a) >= static_cast<uint8_t>(b)
Callers: RequestQueue::enqueue() (src/request_queue.cpp)
Existing tests calling it directly: none

## RequestQueue::enqueue  (src/request_queue.cpp:13-25)
Signature: Status RequestQueue::enqueue(const Request& r)
Params: r (const Request& r)
Decisions (drive each outcome; loops: 0, 1, many):
  L14    if       (x.id == r.id)
  L16    if       (coreIdx >= kCoreCount)
  L18    if       (q.size() >= kMaxQueuePerCore)
  L22    while    (it != q.end() && higherOrEqualPriority(it->priority, r.priority)) [2 sub-conditions: each must flip the outcome alone]
Returns: Status::INVALID_ARG | Status::QUEUE_FULL | Status::OK
Calls: higherOrEqualPriority() (src/request_queue.cpp:L8)
Callers: CvAccelService::submit() (src/service.cpp); Dispatcher::pump() (src/dispatcher.cpp)
Existing tests calling it directly: TEST(Dispatcher, BlockBytesOf_HandleFound_UsesBlockBytesSoIntegrityOk) (tests/dispatcher_test.cpp:L57); TEST(Dispatcher, BlockBytesOf_HandleNotFound_ReturnsZeroSoIntegrityFails) (tests/dispatcher_test.cpp:L78); TEST(Dispatcher, CancelSession_L133_SessionFound_WakesUsingSessionClientFd) (tests/dispatcher_test.cpp:L632); TEST(Dispatcher, CancelSession_L133_SessionNotFound_NoWakeButStillRemoved) (tests/dispatcher_test.cpp:L654); TEST(Dispatcher, CancelSession_L136_ClientFdInvalid_NoWake) (tests/dispatcher_test.cpp:L695); TEST(Dispatcher, CancelSession_L136_ClientFdValid_SendsWake) (tests/dispatcher_test.cpp:L674); TEST(Dispatcher, CancelSession_L145_OpenRequestsPositive_Decrements) (tests/dispatcher_test.cpp:L717); TEST(Dispatcher, CancelSession_L145_OpenRequestsZero_NoUnderflow) (tests/dispatcher_test.cpp:L740)

## RequestQueue::dequeue  (src/request_queue.cpp:27-35)
Signature: bool RequestQueue::dequeue(CoreType core, Request& out)
Params: core (CoreType core); out (Request& out)
Decisions (drive each outcome; loops: 0, 1, many):
  L29    if       (coreIdx >= kCoreCount)
  L31    if       (q.empty())
Returns: false | true
Callers: Dispatcher::pump() (src/dispatcher.cpp)
Existing tests calling it directly: TEST(RequestQueue, Dequeue_CoreIdxGreaterOrEqualCoreCount_ReturnsFalse) (tests/request_queue_test.cpp:L128); TEST(RequestQueue, Dequeue_CoreIdxLessThanCoreCount_DoesNotReturnFalseImmediately) (tests/request_queue_test.cpp:L135); TEST(RequestQueue, Dequeue_QueueEmpty_ReturnsFalse) (tests/request_queue_test.cpp:L145); TEST(RequestQueue, Dequeue_QueueNotEmpty_ReturnsTrueAndPopsFront) (tests/request_queue_test.cpp:L152); TEST(RequestQueue, Enqueue_L21LoopManyIterations_InsertsAfterMultipleHigherPriorityEntries) (tests/request_queue_test.cpp:L111); TEST(RequestQueue, Enqueue_L21LoopOneIteration_InsertsAfterOneHigherPriorityEntry) (tests/request_queue_test.cpp:L95); TEST(RequestQueue, Enqueue_L21LoopZeroIterations_EmptyQueue_InsertsAsOnlyElement) (tests/request_queue_test.cpp:L83); TEST(RequestQueue, HigherOrEqualPriority_TypicalInputs_HigherPriorityOvertakesLowerPriority) (tests/request_queue_test.cpp:L30)

## RequestQueue::peek  (src/request_queue.cpp:37-44)
Signature: bool RequestQueue::peek(CoreType core, Request& out) const
Params: core (CoreType core); out (Request& out)
Decisions (drive each outcome; loops: 0, 1, many):
  L39    if       (coreIdx >= kCoreCount)
  L41    if       (q.empty())
Returns: false | true
Existing tests calling it directly: TEST(RequestQueue, Peek_CoreIdxGreaterOrEqualCoreCount_ReturnsFalse) (tests/request_queue_test.cpp:L170); TEST(RequestQueue, Peek_CoreIdxLessThanCoreCount_DoesNotReturnFalseImmediately) (tests/request_queue_test.cpp:L177); TEST(RequestQueue, Peek_QueueEmpty_ReturnsFalse) (tests/request_queue_test.cpp:L187); TEST(RequestQueue, Peek_QueueNotEmpty_ReturnsTrueAndDoesNotPopFront) (tests/request_queue_test.cpp:L194)

## RequestQueue::size  (src/request_queue.cpp:46-50)
Signature: unsigned RequestQueue::size(CoreType core) const
Params: core (CoreType core)
Decisions (drive each outcome; loops: 0, 1, many):
  L48    if       (coreIdx >= kCoreCount)
Returns: 0 | static_cast<unsigned>(queues_[coreIdx].size())
Calls: RequestQueue::size() (src/request_queue.cpp:L46)
Callers: RequestQueue::size() (src/request_queue.cpp); RequestQueue::sizeTotal() (src/request_queue.cpp)
Existing tests calling it directly: TEST(Dispatcher, Pump_L38_CoreBusy_SkipsCoreWithoutDequeuing) (tests/dispatcher_test.cpp:L258); TEST(Dispatcher, Pump_L38_CoreFreeWithManyRequests_StartsAllQueuedRequests) (tests/dispatcher_test.cpp:L298); TEST(Dispatcher, Pump_L38_CoreFreeWithOneRequest_StartsOneRequestThenStops) (tests/dispatcher_test.cpp:L278); TEST(Dispatcher, Pump_L47_StatusBusy_ReEnqueuesRequestAndBreaks) (tests/dispatcher_test.cpp:L395); TEST(Dispatcher, Pump_L47_StatusNotBusy_RecordsFailureInPlace) (tests/dispatcher_test.cpp:L415); TEST(RequestQueue, CancelSession_L60LoopManyIterations_MultipleQueuedRequests_ReturnsThree) (tests/request_queue_test.cpp:L261); TEST(RequestQueue, CancelSession_SessionDoesNotMatch_KeepsRequestAndReturnsZero) (tests/request_queue_test.cpp:L291); TEST(RequestQueue, CancelSession_SessionMatches_RemovesRequestAndReturnsOne) (tests/request_queue_test.cpp:L276)

## RequestQueue::sizeTotal  (src/request_queue.cpp:52-56)
Signature: unsigned RequestQueue::sizeTotal() const
Decisions: none (straight-line code)
Returns: total
Calls: RequestQueue::size() (src/request_queue.cpp:L46)
Callers: CvAccelService::queued() (src/service.cpp)
Existing tests calling it directly: TEST(Dispatcher, Pump_L40_DequeueFails_BreaksWithoutStarting) (tests/dispatcher_test.cpp:L320); TEST(RequestQueue, SizeTotal_TypicalInputs_ReturnsSumAcrossCores) (tests/request_queue_test.cpp:L225)

## RequestQueue::cancelSession  (src/request_queue.cpp:58-72)
Signature: unsigned RequestQueue::cancelSession(SessionId session, std::vector<RequestId>& removed)
Params: session (SessionId session); removed (std::vector<RequestId>& removed)
Decisions (drive each outcome; loops: 0, 1, many):
  L61    for      (auto it = q.begin(); it != q.end();)
  L62    if       (it->session == session) (has else)
Returns: count
Existing tests calling it directly: TEST(RequestQueue, CancelSession_L60LoopManyIterations_MultipleQueuedRequests_ReturnsThree) (tests/request_queue_test.cpp:L261); TEST(RequestQueue, CancelSession_L60LoopOneIteration_SingleQueuedRequest_ReturnsOne) (tests/request_queue_test.cpp:L248); TEST(RequestQueue, CancelSession_L60LoopZeroIterations_EmptyQueues_ReturnsZero) (tests/request_queue_test.cpp:L239); TEST(RequestQueue, CancelSession_SessionDoesNotMatch_KeepsRequestAndReturnsZero) (tests/request_queue_test.cpp:L291); TEST(RequestQueue, CancelSession_SessionMatches_RemovesRequestAndReturnsOne) (tests/request_queue_test.cpp:L276)
# dependencies of src/request_queue.cpp  (mock/stub candidates first; 'in-scope code' = another scanned file, often an existing mock)
