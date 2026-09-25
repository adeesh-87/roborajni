#include "cvaccel/request_queue.hpp"

#include "CppUTest/TestHarness.h"

namespace {

using namespace cvaccel;

Request makeRequest(RequestId id, CoreType core, Priority priority) {
    Request r;
    r.id = id;
    r.session = 1;
    r.clientFd = -1;
    r.mem = 0;
    r.core = core;
    r.priority = priority;
    r.bytes = 100;
    r.tQueued = 0;
    return r;
}

}  // namespace

TEST_GROUP(RequestQueue) {};

// higherOrEqualPriority() has internal (anonymous-namespace) linkage in src/request_queue.cpp, so it
// cannot be called directly from this translation unit. It is exercised through
// RequestQueue::enqueue()'s insertion loop: higherOrEqualPriority(NORMAL, HIGH) == (1 >= 2) == false,
// so the loop stops immediately and the HIGH request is placed ahead of the already-queued NORMAL one.
TEST(RequestQueue, HigherOrEqualPriority_TypicalInputs_HigherPriorityOvertakesLowerPriority) {
    RequestQueue queue;
    Request normal = makeRequest(1, CoreType::RESIZE, Priority::NORMAL);
    Request high = makeRequest(2, CoreType::RESIZE, Priority::HIGH);
    LONGS_EQUAL((int)Status::OK, (int)queue.enqueue(normal));
    LONGS_EQUAL((int)Status::OK, (int)queue.enqueue(high));

    Request out;
    CHECK_TRUE(queue.dequeue(CoreType::RESIZE, out));
    UNSIGNED_LONGS_EQUAL(2, out.id);
}

// L15 true: coreIdx (static_cast<unsigned>(r.core)) >= kCoreCount(5) -> INVALID_ARG before queues_ is touched.
TEST(RequestQueue, Enqueue_CoreIdxGreaterOrEqualCoreCount_ReturnsInvalidArg) {
    RequestQueue queue;
    Request r = makeRequest(1, static_cast<CoreType>(5), Priority::NORMAL);
    LONGS_EQUAL((int)Status::INVALID_ARG, (int)queue.enqueue(r));
}

// L15 false: a valid core index passes the guard and the request is queued.
TEST(RequestQueue, Enqueue_CoreIdxLessThanCoreCount_ReturnsOk) {
    RequestQueue queue;
    Request r = makeRequest(1, CoreType::RESIZE, Priority::NORMAL);
    LONGS_EQUAL((int)Status::OK, (int)queue.enqueue(r));
}

// L17 true: q.size() (32) >= kMaxQueuePerCore(32) -> QUEUE_FULL.
TEST(RequestQueue, Enqueue_QueueSizeAtMax_ReturnsQueueFull) {
    RequestQueue queue;
    for (RequestId id = 1; id <= kMaxQueuePerCore; ++id) {
        Request r = makeRequest(id, CoreType::RESIZE, Priority::NORMAL);
        LONGS_EQUAL((int)Status::OK, (int)queue.enqueue(r));
    }
    Request extra = makeRequest(kMaxQueuePerCore + 1, CoreType::RESIZE, Priority::NORMAL);
    LONGS_EQUAL((int)Status::QUEUE_FULL, (int)queue.enqueue(extra));
}

// L17 false: q.size() (31) < kMaxQueuePerCore(32) -> passes the guard, and the queue reaches size 32.
TEST(RequestQueue, Enqueue_QueueSizeBelowMax_ReturnsOk) {
    RequestQueue queue;
    for (RequestId id = 1; id < kMaxQueuePerCore; ++id) {
        Request r = makeRequest(id, CoreType::RESIZE, Priority::NORMAL);
        LONGS_EQUAL((int)Status::OK, (int)queue.enqueue(r));
    }
    UNSIGNED_LONGS_EQUAL(kMaxQueuePerCore - 1, queue.size(CoreType::RESIZE));

    Request r = makeRequest(kMaxQueuePerCore, CoreType::RESIZE, Priority::NORMAL);
    LONGS_EQUAL((int)Status::OK, (int)queue.enqueue(r));
    UNSIGNED_LONGS_EQUAL(kMaxQueuePerCore, queue.size(CoreType::RESIZE));
}

// L21 loop 0 iterations: q.begin() == q.end() on an empty queue, so the while condition is false on
// entry and the request is inserted as the sole element.
TEST(RequestQueue, Enqueue_L21LoopZeroIterations_EmptyQueue_InsertsAsOnlyElement) {
    RequestQueue queue;
    Request r = makeRequest(1, CoreType::RESIZE, Priority::NORMAL);
    LONGS_EQUAL((int)Status::OK, (int)queue.enqueue(r));

    Request out;
    CHECK_TRUE(queue.dequeue(CoreType::RESIZE, out));
    UNSIGNED_LONGS_EQUAL(1, out.id);
}

// L21 loop 1 iteration: the single queued HIGH entry satisfies higherOrEqualPriority(HIGH, NORMAL), so
// the loop advances once to end() and the NORMAL request is inserted after it.
TEST(RequestQueue, Enqueue_L21LoopOneIteration_InsertsAfterOneHigherPriorityEntry) {
    RequestQueue queue;
    Request high = makeRequest(1, CoreType::RESIZE, Priority::HIGH);
    Request normal = makeRequest(2, CoreType::RESIZE, Priority::NORMAL);
    LONGS_EQUAL((int)Status::OK, (int)queue.enqueue(high));
    LONGS_EQUAL((int)Status::OK, (int)queue.enqueue(normal));

    Request out;
    CHECK_TRUE(queue.dequeue(CoreType::RESIZE, out));
    UNSIGNED_LONGS_EQUAL(1, out.id);
    CHECK_TRUE(queue.dequeue(CoreType::RESIZE, out));
    UNSIGNED_LONGS_EQUAL(2, out.id);
}

// L21 loop many iterations: three queued HIGH entries all satisfy higherOrEqualPriority(HIGH, NORMAL),
// so the loop advances three times to end() before the NORMAL request is inserted last.
TEST(RequestQueue, Enqueue_L21LoopManyIterations_InsertsAfterMultipleHigherPriorityEntries) {
    RequestQueue queue;
    for (RequestId id = 1; id <= 3; ++id) {
        Request r = makeRequest(id, CoreType::RESIZE, Priority::HIGH);
        LONGS_EQUAL((int)Status::OK, (int)queue.enqueue(r));
    }
    Request normal = makeRequest(4, CoreType::RESIZE, Priority::NORMAL);
    LONGS_EQUAL((int)Status::OK, (int)queue.enqueue(normal));

    Request out;
    for (RequestId expected = 1; expected <= 4; ++expected) {
        CHECK_TRUE(queue.dequeue(CoreType::RESIZE, out));
        UNSIGNED_LONGS_EQUAL(expected, out.id);
    }
}

// L28 true: coreIdx (static_cast<unsigned>(core)) >= kCoreCount(5) -> false before queues_ is touched.
TEST(RequestQueue, Dequeue_CoreIdxGreaterOrEqualCoreCount_ReturnsFalse) {
    RequestQueue queue;
    Request out;
    CHECK_FALSE(queue.dequeue(static_cast<CoreType>(5), out));
}

// L28 false: a valid core index passes the guard, so the function does not return false immediately.
TEST(RequestQueue, Dequeue_CoreIdxLessThanCoreCount_DoesNotReturnFalseImmediately) {
    RequestQueue queue;
    Request r = makeRequest(1, CoreType::RESIZE, Priority::NORMAL);
    LONGS_EQUAL((int)Status::OK, (int)queue.enqueue(r));

    Request out;
    CHECK_TRUE(queue.dequeue(CoreType::RESIZE, out));
}

// L30 true: q.empty() on a core with nothing queued -> false.
TEST(RequestQueue, Dequeue_QueueEmpty_ReturnsFalse) {
    RequestQueue queue;
    Request out;
    CHECK_FALSE(queue.dequeue(CoreType::RESIZE, out));
}

// L30 false: q.empty() is false -> returns true, out is set to the front, and the front is popped.
TEST(RequestQueue, Dequeue_QueueNotEmpty_ReturnsTrueAndPopsFront) {
    RequestQueue queue;
    Request first = makeRequest(1, CoreType::RESIZE, Priority::NORMAL);
    Request second = makeRequest(2, CoreType::RESIZE, Priority::NORMAL);
    LONGS_EQUAL((int)Status::OK, (int)queue.enqueue(first));
    LONGS_EQUAL((int)Status::OK, (int)queue.enqueue(second));

    Request out;
    CHECK_TRUE(queue.dequeue(CoreType::RESIZE, out));
    UNSIGNED_LONGS_EQUAL(1, out.id);
    UNSIGNED_LONGS_EQUAL(1, queue.size(CoreType::RESIZE));

    CHECK_TRUE(queue.dequeue(CoreType::RESIZE, out));
    UNSIGNED_LONGS_EQUAL(2, out.id);
    UNSIGNED_LONGS_EQUAL(0, queue.size(CoreType::RESIZE));
}

// L38 true: coreIdx (static_cast<unsigned>(core)) >= kCoreCount(5) -> false before queues_ is touched.
TEST(RequestQueue, Peek_CoreIdxGreaterOrEqualCoreCount_ReturnsFalse) {
    RequestQueue queue;
    Request out;
    CHECK_FALSE(queue.peek(static_cast<CoreType>(5), out));
}

// L38 false: a valid core index passes the guard, so the function does not return false immediately.
TEST(RequestQueue, Peek_CoreIdxLessThanCoreCount_DoesNotReturnFalseImmediately) {
    RequestQueue queue;
    Request r = makeRequest(1, CoreType::RESIZE, Priority::NORMAL);
    LONGS_EQUAL((int)Status::OK, (int)queue.enqueue(r));

    Request out;
    CHECK_TRUE(queue.peek(CoreType::RESIZE, out));
}

// L40 true: q.empty() on a core with nothing queued -> false.
TEST(RequestQueue, Peek_QueueEmpty_ReturnsFalse) {
    RequestQueue queue;
    Request out;
    CHECK_FALSE(queue.peek(CoreType::RESIZE, out));
}

// L40 false: q.empty() is false -> returns true, out is set to the front, and the front is not removed.
TEST(RequestQueue, Peek_QueueNotEmpty_ReturnsTrueAndDoesNotPopFront) {
    RequestQueue queue;
    Request first = makeRequest(1, CoreType::RESIZE, Priority::NORMAL);
    Request second = makeRequest(2, CoreType::RESIZE, Priority::NORMAL);
    LONGS_EQUAL((int)Status::OK, (int)queue.enqueue(first));
    LONGS_EQUAL((int)Status::OK, (int)queue.enqueue(second));

    Request out;
    CHECK_TRUE(queue.peek(CoreType::RESIZE, out));
    UNSIGNED_LONGS_EQUAL(1, out.id);
    UNSIGNED_LONGS_EQUAL(2, queue.size(CoreType::RESIZE));
}

// L47 true: coreIdx (static_cast<unsigned>(core)) >= kCoreCount(5) -> 0, regardless of queue contents.
TEST(RequestQueue, Size_CoreIdxGreaterOrEqualCoreCount_ReturnsZero) {
    RequestQueue queue;
    UNSIGNED_LONGS_EQUAL(0, queue.size(static_cast<CoreType>(5)));
}

// L47 false: a valid core index passes the guard and the actual queue size is returned.
TEST(RequestQueue, Size_CoreIdxLessThanCoreCount_ReturnsQueueSize) {
    RequestQueue queue;
    Request first = makeRequest(1, CoreType::RESIZE, Priority::NORMAL);
    Request second = makeRequest(2, CoreType::RESIZE, Priority::NORMAL);
    LONGS_EQUAL((int)Status::OK, (int)queue.enqueue(first));
    LONGS_EQUAL((int)Status::OK, (int)queue.enqueue(second));

    UNSIGNED_LONGS_EQUAL(2, queue.size(CoreType::RESIZE));
}

// Straight-line: sizeTotal sums size() across all queues_ entries (RESIZE=2, CONVOLVE=1 -> total 3).
TEST(RequestQueue, SizeTotal_TypicalInputs_ReturnsSumAcrossCores) {
    RequestQueue queue;
    Request r1 = makeRequest(1, CoreType::RESIZE, Priority::NORMAL);
    Request r2 = makeRequest(2, CoreType::RESIZE, Priority::NORMAL);
    Request r3 = makeRequest(3, CoreType::CONVOLVE, Priority::NORMAL);
    LONGS_EQUAL((int)Status::OK, (int)queue.enqueue(r1));
    LONGS_EQUAL((int)Status::OK, (int)queue.enqueue(r2));
    LONGS_EQUAL((int)Status::OK, (int)queue.enqueue(r3));

    UNSIGNED_LONGS_EQUAL(3, queue.sizeTotal());
}

// L60 loop 0 iterations: every q in queues_ is empty, so q.begin() == q.end() on each -> count stays 0
// and removed stays empty.
TEST(RequestQueue, CancelSession_L60LoopZeroIterations_EmptyQueues_ReturnsZero) {
    RequestQueue queue;
    std::vector<RequestId> removed;
    UNSIGNED_LONGS_EQUAL(0, queue.cancelSession(1, removed));
    CHECK_TRUE(removed.empty());
}

// L60 loop 1 iteration: a single queued request means the inner for-loop body runs once for that core
// before reaching q.end().
TEST(RequestQueue, CancelSession_L60LoopOneIteration_SingleQueuedRequest_ReturnsOne) {
    RequestQueue queue;
    Request r = makeRequest(1, CoreType::RESIZE, Priority::NORMAL);
    LONGS_EQUAL((int)Status::OK, (int)queue.enqueue(r));

    std::vector<RequestId> removed;
    UNSIGNED_LONGS_EQUAL(1, queue.cancelSession(1, removed));
    UNSIGNED_LONGS_EQUAL(1, removed.size());
    UNSIGNED_LONGS_EQUAL(1, removed[0]);
}

// L60 loop many iterations: three queued requests (same session, same core) mean the inner for-loop
// body runs three times before reaching q.end().
TEST(RequestQueue, CancelSession_L60LoopManyIterations_MultipleQueuedRequests_ReturnsThree) {
    RequestQueue queue;
    for (RequestId id = 1; id <= 3; ++id) {
        Request r = makeRequest(id, CoreType::RESIZE, Priority::NORMAL);
        LONGS_EQUAL((int)Status::OK, (int)queue.enqueue(r));
    }

    std::vector<RequestId> removed;
    UNSIGNED_LONGS_EQUAL(3, queue.cancelSession(1, removed));
    UNSIGNED_LONGS_EQUAL(3, removed.size());
    UNSIGNED_LONGS_EQUAL(0, queue.size(CoreType::RESIZE));
}

// L61 true: it->session == session -> the request's id is appended to removed, it is erased, and count
// is incremented.
TEST(RequestQueue, CancelSession_SessionMatches_RemovesRequestAndReturnsOne) {
    RequestQueue queue;
    Request r = makeRequest(1, CoreType::RESIZE, Priority::NORMAL);
    r.session = 7;
    LONGS_EQUAL((int)Status::OK, (int)queue.enqueue(r));

    std::vector<RequestId> removed;
    UNSIGNED_LONGS_EQUAL(1, queue.cancelSession(7, removed));
    UNSIGNED_LONGS_EQUAL(1, removed.size());
    UNSIGNED_LONGS_EQUAL(1, removed[0]);
    UNSIGNED_LONGS_EQUAL(0, queue.size(CoreType::RESIZE));
}

// L61 false: it->session == session is false -> the else branch runs, the iterator is simply advanced,
// and the non-matching request stays queued.
TEST(RequestQueue, CancelSession_SessionDoesNotMatch_KeepsRequestAndReturnsZero) {
    RequestQueue queue;
    Request r = makeRequest(1, CoreType::RESIZE, Priority::NORMAL);
    r.session = 7;
    LONGS_EQUAL((int)Status::OK, (int)queue.enqueue(r));

    std::vector<RequestId> removed;
    UNSIGNED_LONGS_EQUAL(0, queue.cancelSession(8, removed));
    CHECK_TRUE(removed.empty());
    UNSIGNED_LONGS_EQUAL(1, queue.size(CoreType::RESIZE));
}
