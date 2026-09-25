#include "cvaccel/dispatcher.hpp"

#include "CppUTest/TestHarness.h"

namespace {

using namespace cvaccel;

class FakeAccelBlock : public hw::IAccelBlock {
public:
    Status submit(const hw::JobDesc& job) override {
        lastJob = job;
        ++submitCount;
        return submitStatus;
    }
    bool isBusy(CoreType) const override { return busy; }
    void setCompletionHandler(std::function<void(const hw::JobResult&)> h) override { handler = h; }

    Status submitStatus = Status::OK;
    bool busy = false;
    unsigned submitCount = 0;
    hw::JobDesc lastJob{};
    std::function<void(const hw::JobResult&)> handler;
};

class FakeDevice : public os::IDevice {
public:
    Status ioctlToClient(ClientFd, IoctlCmd, const void*, size_t) override {
        ++wakeCount;
        return Status::OK;
    }
    TimeNs nowNs() const override { return now; }
    uint64_t poolPhysBase() const override { return 0; }
    uint8_t* poolVirtBase() override { return nullptr; }

    TimeNs now = 1000;
    unsigned wakeCount = 0;
};

Request makeRequest(RequestId id, MemHandle mem, uint32_t bytes) {
    Request r;
    r.id = id;
    r.session = 1;
    r.clientFd = -1;
    r.mem = mem;
    r.core = CoreType::RESIZE;
    r.priority = Priority::NORMAL;
    r.bytes = bytes;
    r.tQueued = 0;
    return r;
}

}  // namespace

TEST_GROUP(Dispatcher) {};

TEST(Dispatcher, BlockBytesOf_HandleFound_UsesBlockBytesSoIntegrityOk) {
    MemoryPool pool;
    RequestQueue queue;
    SessionManager sessions;
    PerfMonitor perf;
    FakeAccelBlock hw;
    FakeDevice dev;
    Dispatcher dispatcher(hw, dev, queue, pool, sessions, perf);

    MemHandle handle = 0;
    LONGS_EQUAL((int)Status::OK, (int)pool.allocate(1, 100, handle));

    Request r = makeRequest(1, handle, 100);
    hw.submitStatus = Status::HW_ERROR;
    LONGS_EQUAL((int)Status::OK, (int)queue.enqueue(r));

    dispatcher.pump();

    UNSIGNED_LONGS_EQUAL(0, perf.integrityErrors());
}

TEST(Dispatcher, BlockBytesOf_HandleNotFound_ReturnsZeroSoIntegrityFails) {
    MemoryPool pool;
    RequestQueue queue;
    SessionManager sessions;
    PerfMonitor perf;
    FakeAccelBlock hw;
    FakeDevice dev;
    Dispatcher dispatcher(hw, dev, queue, pool, sessions, perf);

    Request r = makeRequest(1, 0, 100);   // mem 0 = invalid handle, never allocated
    hw.submitStatus = Status::HW_ERROR;
    LONGS_EQUAL((int)Status::OK, (int)queue.enqueue(r));

    dispatcher.pump();

    UNSIGNED_LONGS_EQUAL(1, perf.integrityErrors());
}

TEST(Dispatcher, Start_ConfigAllZero_JobConfigAllZero) {
    MemoryPool pool;
    RequestQueue queue;
    SessionManager sessions;
    PerfMonitor perf;
    FakeAccelBlock hw;
    FakeDevice dev;
    Dispatcher dispatcher(hw, dev, queue, pool, sessions, perf);

    Request r = makeRequest(1, 0, 100);
    for (unsigned i = 0; i < kConfigWords; ++i) r.config[i] = 0;
    hw.submitStatus = Status::OK;
    LONGS_EQUAL((int)Status::OK, (int)queue.enqueue(r));

    dispatcher.pump();

    uint32_t expected[kConfigWords] = {};
    MEMCMP_EQUAL(expected, hw.lastJob.config, sizeof(expected));
}

TEST(Dispatcher, Start_ConfigOneNonZero_JobConfigCopiesThatWord) {
    MemoryPool pool;
    RequestQueue queue;
    SessionManager sessions;
    PerfMonitor perf;
    FakeAccelBlock hw;
    FakeDevice dev;
    Dispatcher dispatcher(hw, dev, queue, pool, sessions, perf);

    Request r = makeRequest(1, 0, 100);
    for (unsigned i = 0; i < kConfigWords; ++i) r.config[i] = 0;
    r.config[0] = 7;
    hw.submitStatus = Status::OK;
    LONGS_EQUAL((int)Status::OK, (int)queue.enqueue(r));

    dispatcher.pump();

    uint32_t expected[kConfigWords] = {};
    expected[0] = 7;
    MEMCMP_EQUAL(expected, hw.lastJob.config, sizeof(expected));
}

TEST(Dispatcher, Start_ConfigAllNonZero_JobConfigCopiesEveryWord) {
    MemoryPool pool;
    RequestQueue queue;
    SessionManager sessions;
    PerfMonitor perf;
    FakeAccelBlock hw;
    FakeDevice dev;
    Dispatcher dispatcher(hw, dev, queue, pool, sessions, perf);

    Request r = makeRequest(1, 0, 100);
    uint32_t expected[kConfigWords] = {};
    for (unsigned i = 0; i < kConfigWords; ++i) {
        r.config[i] = i + 1;
        expected[i] = i + 1;
    }
    hw.submitStatus = Status::OK;
    LONGS_EQUAL((int)Status::OK, (int)queue.enqueue(r));

    dispatcher.pump();

    MEMCMP_EQUAL(expected, hw.lastJob.config, sizeof(expected));
}

TEST(Dispatcher, Start_SubmitOk_RequestMovesToRunning) {
    MemoryPool pool;
    RequestQueue queue;
    SessionManager sessions;
    PerfMonitor perf;
    FakeAccelBlock hw;
    FakeDevice dev;
    Dispatcher dispatcher(hw, dev, queue, pool, sessions, perf);

    Request r = makeRequest(42, 0, 100);
    hw.submitStatus = Status::OK;
    LONGS_EQUAL((int)Status::OK, (int)queue.enqueue(r));

    unsigned started = dispatcher.pump();

    UNSIGNED_LONGS_EQUAL(1, started);
    UNSIGNED_LONGS_EQUAL(1, dispatcher.inFlight());
    CHECK_TRUE(dispatcher.isRunning(42));
}

TEST(Dispatcher, Start_SubmitFails_RequestNotMovedToRunning) {
    MemoryPool pool;
    RequestQueue queue;
    SessionManager sessions;
    PerfMonitor perf;
    FakeAccelBlock hw;
    FakeDevice dev;
    Dispatcher dispatcher(hw, dev, queue, pool, sessions, perf);

    Request r = makeRequest(42, 0, 100);
    hw.submitStatus = Status::HW_ERROR;
    LONGS_EQUAL((int)Status::OK, (int)queue.enqueue(r));

    unsigned started = dispatcher.pump();

    UNSIGNED_LONGS_EQUAL(0, started);
    UNSIGNED_LONGS_EQUAL(0, dispatcher.inFlight());
    CHECK_FALSE(dispatcher.isRunning(42));
}

TEST(Dispatcher, Pump_L36_NoCoresHaveQueuedRequests_ReturnsZeroStarted) {
    MemoryPool pool;
    RequestQueue queue;
    SessionManager sessions;
    PerfMonitor perf;
    FakeAccelBlock hw;
    FakeDevice dev;
    Dispatcher dispatcher(hw, dev, queue, pool, sessions, perf);

    unsigned started = dispatcher.pump();

    UNSIGNED_LONGS_EQUAL(0, started);
    UNSIGNED_LONGS_EQUAL(0, hw.submitCount);
}

TEST(Dispatcher, Pump_L36_OneCoreHasQueuedRequest_StartsThatCoresRequest) {
    MemoryPool pool;
    RequestQueue queue;
    SessionManager sessions;
    PerfMonitor perf;
    FakeAccelBlock hw;
    FakeDevice dev;
    Dispatcher dispatcher(hw, dev, queue, pool, sessions, perf);

    Request r = makeRequest(1, 0, 100);
    hw.submitStatus = Status::OK;
    LONGS_EQUAL((int)Status::OK, (int)queue.enqueue(r));

    unsigned started = dispatcher.pump();

    UNSIGNED_LONGS_EQUAL(1, started);
    UNSIGNED_LONGS_EQUAL(1, hw.submitCount);
}

TEST(Dispatcher, Pump_L36_MultipleCoresHaveQueuedRequests_StartsEachCoresRequest) {
    MemoryPool pool;
    RequestQueue queue;
    SessionManager sessions;
    PerfMonitor perf;
    FakeAccelBlock hw;
    FakeDevice dev;
    Dispatcher dispatcher(hw, dev, queue, pool, sessions, perf);

    Request r1 = makeRequest(1, 0, 100);
    r1.core = CoreType::RESIZE;
    Request r2 = makeRequest(2, 0, 100);
    r2.core = CoreType::CONVOLVE;
    hw.submitStatus = Status::OK;
    LONGS_EQUAL((int)Status::OK, (int)queue.enqueue(r1));
    LONGS_EQUAL((int)Status::OK, (int)queue.enqueue(r2));

    unsigned started = dispatcher.pump();

    UNSIGNED_LONGS_EQUAL(2, started);
    UNSIGNED_LONGS_EQUAL(2, hw.submitCount);
}

TEST(Dispatcher, Pump_L38_CoreBusy_SkipsCoreWithoutDequeuing) {
    MemoryPool pool;
    RequestQueue queue;
    SessionManager sessions;
    PerfMonitor perf;
    FakeAccelBlock hw;
    FakeDevice dev;
    Dispatcher dispatcher(hw, dev, queue, pool, sessions, perf);

    Request r = makeRequest(1, 0, 100);
    LONGS_EQUAL((int)Status::OK, (int)queue.enqueue(r));
    hw.busy = true;

    unsigned started = dispatcher.pump();

    UNSIGNED_LONGS_EQUAL(0, started);
    UNSIGNED_LONGS_EQUAL(0, hw.submitCount);
    UNSIGNED_LONGS_EQUAL(1, queue.size(CoreType::RESIZE));
}

TEST(Dispatcher, Pump_L38_CoreFreeWithOneRequest_StartsOneRequestThenStops) {
    MemoryPool pool;
    RequestQueue queue;
    SessionManager sessions;
    PerfMonitor perf;
    FakeAccelBlock hw;
    FakeDevice dev;
    Dispatcher dispatcher(hw, dev, queue, pool, sessions, perf);

    Request r = makeRequest(1, 0, 100);
    hw.submitStatus = Status::OK;
    LONGS_EQUAL((int)Status::OK, (int)queue.enqueue(r));

    unsigned started = dispatcher.pump();

    UNSIGNED_LONGS_EQUAL(1, started);
    UNSIGNED_LONGS_EQUAL(1, hw.submitCount);
    UNSIGNED_LONGS_EQUAL(0, queue.size(CoreType::RESIZE));
}

TEST(Dispatcher, Pump_L38_CoreFreeWithManyRequests_StartsAllQueuedRequests) {
    MemoryPool pool;
    RequestQueue queue;
    SessionManager sessions;
    PerfMonitor perf;
    FakeAccelBlock hw;
    FakeDevice dev;
    Dispatcher dispatcher(hw, dev, queue, pool, sessions, perf);

    hw.submitStatus = Status::OK;
    for (RequestId id = 1; id <= 3; ++id) {
        Request r = makeRequest(id, 0, 100);
        LONGS_EQUAL((int)Status::OK, (int)queue.enqueue(r));
    }

    unsigned started = dispatcher.pump();

    UNSIGNED_LONGS_EQUAL(3, started);
    UNSIGNED_LONGS_EQUAL(3, hw.submitCount);
    UNSIGNED_LONGS_EQUAL(0, queue.size(CoreType::RESIZE));
}

TEST(Dispatcher, Pump_L40_DequeueFails_BreaksWithoutStarting) {
    MemoryPool pool;
    RequestQueue queue;
    SessionManager sessions;
    PerfMonitor perf;
    FakeAccelBlock hw;
    FakeDevice dev;
    Dispatcher dispatcher(hw, dev, queue, pool, sessions, perf);

    unsigned started = dispatcher.pump();

    UNSIGNED_LONGS_EQUAL(0, started);
    UNSIGNED_LONGS_EQUAL(0, queue.sizeTotal());
    UNSIGNED_LONGS_EQUAL(0, dispatcher.inFlight());
}

TEST(Dispatcher, Pump_L40_DequeueSucceeds_CallsStart) {
    MemoryPool pool;
    RequestQueue queue;
    SessionManager sessions;
    PerfMonitor perf;
    FakeAccelBlock hw;
    FakeDevice dev;
    Dispatcher dispatcher(hw, dev, queue, pool, sessions, perf);

    Request r = makeRequest(7, 0, 100);
    hw.submitStatus = Status::OK;
    LONGS_EQUAL((int)Status::OK, (int)queue.enqueue(r));

    dispatcher.pump();

    UNSIGNED_LONGS_EQUAL(1, hw.submitCount);
    UNSIGNED_LONGS_EQUAL(7, hw.lastJob.jobId);
}

TEST(Dispatcher, Pump_L43_StatusOk_IncrementsStartedAndContinuesLoop) {
    MemoryPool pool;
    RequestQueue queue;
    SessionManager sessions;
    PerfMonitor perf;
    FakeAccelBlock hw;
    FakeDevice dev;
    Dispatcher dispatcher(hw, dev, queue, pool, sessions, perf);

    Request r = makeRequest(5, 0, 100);
    hw.submitStatus = Status::OK;
    LONGS_EQUAL((int)Status::OK, (int)queue.enqueue(r));

    unsigned started = dispatcher.pump();

    UNSIGNED_LONGS_EQUAL(1, started);
    UNSIGNED_LONGS_EQUAL(1, dispatcher.inFlight());
    CHECK_TRUE(dispatcher.isRunning(5));
}

TEST(Dispatcher, Pump_L43_StatusNotOk_DoesNotIncrementStarted) {
    MemoryPool pool;
    RequestQueue queue;
    SessionManager sessions;
    PerfMonitor perf;
    FakeAccelBlock hw;
    FakeDevice dev;
    Dispatcher dispatcher(hw, dev, queue, pool, sessions, perf);

    Request r = makeRequest(6, 0, 100);
    hw.submitStatus = Status::HW_ERROR;
    LONGS_EQUAL((int)Status::OK, (int)queue.enqueue(r));

    unsigned started = dispatcher.pump();

    UNSIGNED_LONGS_EQUAL(0, started);
    UNSIGNED_LONGS_EQUAL(0, dispatcher.inFlight());
    UNSIGNED_LONGS_EQUAL(1, perf.totalCount());
}

TEST(Dispatcher, Pump_L47_StatusBusy_ReEnqueuesRequestAndBreaks) {
    MemoryPool pool;
    RequestQueue queue;
    SessionManager sessions;
    PerfMonitor perf;
    FakeAccelBlock hw;
    FakeDevice dev;
    Dispatcher dispatcher(hw, dev, queue, pool, sessions, perf);

    Request r = makeRequest(8, 0, 100);
    hw.submitStatus = Status::BUSY;
    LONGS_EQUAL((int)Status::OK, (int)queue.enqueue(r));

    unsigned started = dispatcher.pump();

    UNSIGNED_LONGS_EQUAL(0, started);
    UNSIGNED_LONGS_EQUAL(1, queue.size(CoreType::RESIZE));
    UNSIGNED_LONGS_EQUAL(0, perf.totalCount());
}

TEST(Dispatcher, Pump_L47_StatusNotBusy_RecordsFailureInPlace) {
    MemoryPool pool;
    RequestQueue queue;
    SessionManager sessions;
    PerfMonitor perf;
    FakeAccelBlock hw;
    FakeDevice dev;
    Dispatcher dispatcher(hw, dev, queue, pool, sessions, perf);

    Request r = makeRequest(9, 0, 100);
    hw.submitStatus = Status::HW_ERROR;
    LONGS_EQUAL((int)Status::OK, (int)queue.enqueue(r));

    dispatcher.pump();

    UNSIGNED_LONGS_EQUAL(1, perf.totalCount());
    UNSIGNED_LONGS_EQUAL(0, queue.size(CoreType::RESIZE));
}

TEST(Dispatcher, Pump_L75_ClientFdSet_WakesClient) {
    MemoryPool pool;
    RequestQueue queue;
    SessionManager sessions;
    PerfMonitor perf;
    FakeAccelBlock hw;
    FakeDevice dev;
    Dispatcher dispatcher(hw, dev, queue, pool, sessions, perf);

    Request r = makeRequest(10, 0, 100);
    r.clientFd = 5;
    hw.submitStatus = Status::HW_ERROR;
    LONGS_EQUAL((int)Status::OK, (int)queue.enqueue(r));

    dispatcher.pump();

    UNSIGNED_LONGS_EQUAL(1, dev.wakeCount);
}

TEST(Dispatcher, Pump_L75_ClientFdInvalid_DoesNotWakeClient) {
    MemoryPool pool;
    RequestQueue queue;
    SessionManager sessions;
    PerfMonitor perf;
    FakeAccelBlock hw;
    FakeDevice dev;
    Dispatcher dispatcher(hw, dev, queue, pool, sessions, perf);

    Request r = makeRequest(11, 0, 100);
    r.clientFd = -1;
    hw.submitStatus = Status::HW_ERROR;
    LONGS_EQUAL((int)Status::OK, (int)queue.enqueue(r));

    dispatcher.pump();

    UNSIGNED_LONGS_EQUAL(0, dev.wakeCount);
}

TEST(Dispatcher, OnCompletion_L90_JobIdNotInRunning_ReturnsInvalidArg) {
    MemoryPool pool;
    RequestQueue queue;
    SessionManager sessions;
    PerfMonitor perf;
    FakeAccelBlock hw;
    FakeDevice dev;
    Dispatcher dispatcher(hw, dev, queue, pool, sessions, perf);

    hw::JobResult res{999, Status::OK, 0};

    LONGS_EQUAL((int)Status::INVALID_ARG, (int)dispatcher.onCompletion(res));
    UNSIGNED_LONGS_EQUAL(0, perf.totalCount());
    UNSIGNED_LONGS_EQUAL(0, dev.wakeCount);
}

TEST(Dispatcher, OnCompletion_L90_JobIdInRunning_ErasesFromRunningAndReturnsOk) {
    MemoryPool pool;
    RequestQueue queue;
    SessionManager sessions;
    PerfMonitor perf;
    FakeAccelBlock hw;
    FakeDevice dev;
    Dispatcher dispatcher(hw, dev, queue, pool, sessions, perf);

    Request r = makeRequest(20, 0, 100);
    r.clientFd = -1;
    hw.submitStatus = Status::OK;
    LONGS_EQUAL((int)Status::OK, (int)queue.enqueue(r));
    dispatcher.pump();

    hw::JobResult res{20, Status::OK, 42};

    LONGS_EQUAL((int)Status::OK, (int)dispatcher.onCompletion(res));
    CHECK_FALSE(dispatcher.isRunning(20));
    UNSIGNED_LONGS_EQUAL(0, dispatcher.inFlight());
}

TEST(Dispatcher, OnCompletion_L107_SessionFoundWithOpenRequests_DecrementsOpenRequests) {
    MemoryPool pool;
    RequestQueue queue;
    SessionManager sessions;
    PerfMonitor perf;
    FakeAccelBlock hw;
    FakeDevice dev;
    Dispatcher dispatcher(hw, dev, queue, pool, sessions, perf);

    SessionId sid = 0;
    LONGS_EQUAL((int)Status::OK, (int)sessions.open(1, Priority::NORMAL, sid));
    SessionInfo* si = sessions.find(sid);
    si->openRequests = 1;

    Request r = makeRequest(30, 0, 100);
    r.session = sid;
    r.clientFd = -1;
    hw.submitStatus = Status::OK;
    LONGS_EQUAL((int)Status::OK, (int)queue.enqueue(r));
    dispatcher.pump();

    hw::JobResult res{30, Status::OK, 0};
    dispatcher.onCompletion(res);

    UNSIGNED_LONGS_EQUAL(0, si->openRequests);
}

// L107 sub-condition A (si is null): completion for a session that was never opened must not
// crash and must still finish the completion normally.
TEST(Dispatcher, OnCompletion_L107_SessionNotFound_StillErasesRunningAndReturnsOk) {
    MemoryPool pool;
    RequestQueue queue;
    SessionManager sessions;
    PerfMonitor perf;
    FakeAccelBlock hw;
    FakeDevice dev;
    Dispatcher dispatcher(hw, dev, queue, pool, sessions, perf);

    Request r = makeRequest(31, 0, 100);
    r.session = 99;   // never opened via sessions.open()
    r.clientFd = -1;
    hw.submitStatus = Status::OK;
    LONGS_EQUAL((int)Status::OK, (int)queue.enqueue(r));
    dispatcher.pump();

    hw::JobResult res{31, Status::OK, 0};

    LONGS_EQUAL((int)Status::OK, (int)dispatcher.onCompletion(res));
    CHECK_FALSE(dispatcher.isRunning(31));
}

// L107 sub-condition B (si->openRequests == 0): the guard must stop the decrement from
// underflowing the unsigned counter.
TEST(Dispatcher, OnCompletion_L107_SessionFoundWithZeroOpenRequests_StaysZero) {
    MemoryPool pool;
    RequestQueue queue;
    SessionManager sessions;
    PerfMonitor perf;
    FakeAccelBlock hw;
    FakeDevice dev;
    Dispatcher dispatcher(hw, dev, queue, pool, sessions, perf);

    SessionId sid = 0;
    LONGS_EQUAL((int)Status::OK, (int)sessions.open(1, Priority::NORMAL, sid));
    SessionInfo* si = sessions.find(sid);
    UNSIGNED_LONGS_EQUAL(0, si->openRequests);

    Request r = makeRequest(32, 0, 100);
    r.session = sid;
    r.clientFd = -1;
    hw.submitStatus = Status::OK;
    LONGS_EQUAL((int)Status::OK, (int)queue.enqueue(r));
    dispatcher.pump();

    hw::JobResult res{32, Status::OK, 0};
    dispatcher.onCompletion(res);

    UNSIGNED_LONGS_EQUAL(0, si->openRequests);
}

TEST(Dispatcher, OnCompletion_L111_ClientFdSet_WakesClient) {
    MemoryPool pool;
    RequestQueue queue;
    SessionManager sessions;
    PerfMonitor perf;
    FakeAccelBlock hw;
    FakeDevice dev;
    Dispatcher dispatcher(hw, dev, queue, pool, sessions, perf);

    Request r = makeRequest(33, 0, 100);
    r.clientFd = 5;
    hw.submitStatus = Status::OK;
    LONGS_EQUAL((int)Status::OK, (int)queue.enqueue(r));
    dispatcher.pump();

    hw::JobResult res{33, Status::OK, 0};
    dispatcher.onCompletion(res);

    UNSIGNED_LONGS_EQUAL(1, dev.wakeCount);
}

TEST(Dispatcher, OnCompletion_L111_ClientFdInvalid_DoesNotWakeClient) {
    MemoryPool pool;
    RequestQueue queue;
    SessionManager sessions;
    PerfMonitor perf;
    FakeAccelBlock hw;
    FakeDevice dev;
    Dispatcher dispatcher(hw, dev, queue, pool, sessions, perf);

    Request r = makeRequest(34, 0, 100);
    r.clientFd = -1;
    hw.submitStatus = Status::OK;
    LONGS_EQUAL((int)Status::OK, (int)queue.enqueue(r));
    dispatcher.pump();

    hw::JobResult res{34, Status::OK, 0};
    dispatcher.onCompletion(res);

    UNSIGNED_LONGS_EQUAL(0, dev.wakeCount);
}

TEST(Dispatcher, CancelSession_L133_SessionFound_WakesUsingSessionClientFd) {
    MemoryPool pool;
    RequestQueue queue;
    SessionManager sessions;
    PerfMonitor perf;
    FakeAccelBlock hw;
    FakeDevice dev;
    Dispatcher dispatcher(hw, dev, queue, pool, sessions, perf);

    SessionId sid = 0;
    LONGS_EQUAL((int)Status::OK, (int)sessions.open(7, Priority::NORMAL, sid));

    Request r = makeRequest(1, 0, 100);
    r.session = sid;
    LONGS_EQUAL((int)Status::OK, (int)queue.enqueue(r));

    unsigned removed = dispatcher.cancelSession(sid);

    UNSIGNED_LONGS_EQUAL(1, removed);
    UNSIGNED_LONGS_EQUAL(1, dev.wakeCount);
}

TEST(Dispatcher, CancelSession_L133_SessionNotFound_NoWakeButStillRemoved) {
    MemoryPool pool;
    RequestQueue queue;
    SessionManager sessions;
    PerfMonitor perf;
    FakeAccelBlock hw;
    FakeDevice dev;
    Dispatcher dispatcher(hw, dev, queue, pool, sessions, perf);

    // Session 42 was never opened via SessionManager, so sessions_.find() returns nullptr.
    Request r = makeRequest(1, 0, 100);
    r.session = 42;
    LONGS_EQUAL((int)Status::OK, (int)queue.enqueue(r));

    unsigned removed = dispatcher.cancelSession(42);

    UNSIGNED_LONGS_EQUAL(1, removed);
    UNSIGNED_LONGS_EQUAL(0, dev.wakeCount);
}

TEST(Dispatcher, CancelSession_L136_ClientFdValid_SendsWake) {
    MemoryPool pool;
    RequestQueue queue;
    SessionManager sessions;
    PerfMonitor perf;
    FakeAccelBlock hw;
    FakeDevice dev;
    Dispatcher dispatcher(hw, dev, queue, pool, sessions, perf);

    SessionId sid = 0;
    LONGS_EQUAL((int)Status::OK, (int)sessions.open(3, Priority::NORMAL, sid));

    Request r = makeRequest(1, 0, 100);
    r.session = sid;
    LONGS_EQUAL((int)Status::OK, (int)queue.enqueue(r));

    dispatcher.cancelSession(sid);

    UNSIGNED_LONGS_EQUAL(1, dev.wakeCount);
}

TEST(Dispatcher, CancelSession_L136_ClientFdInvalid_NoWake) {
    MemoryPool pool;
    RequestQueue queue;
    SessionManager sessions;
    PerfMonitor perf;
    FakeAccelBlock hw;
    FakeDevice dev;
    Dispatcher dispatcher(hw, dev, queue, pool, sessions, perf);

    SessionId sid = 0;
    LONGS_EQUAL((int)Status::OK, (int)sessions.open(-1, Priority::NORMAL, sid));

    Request r = makeRequest(1, 0, 100);
    r.session = sid;
    LONGS_EQUAL((int)Status::OK, (int)queue.enqueue(r));

    unsigned removed = dispatcher.cancelSession(sid);

    UNSIGNED_LONGS_EQUAL(1, removed);
    UNSIGNED_LONGS_EQUAL(0, dev.wakeCount);
}

TEST(Dispatcher, CancelSession_L145_OpenRequestsPositive_Decrements) {
    MemoryPool pool;
    RequestQueue queue;
    SessionManager sessions;
    PerfMonitor perf;
    FakeAccelBlock hw;
    FakeDevice dev;
    Dispatcher dispatcher(hw, dev, queue, pool, sessions, perf);

    SessionId sid = 0;
    LONGS_EQUAL((int)Status::OK, (int)sessions.open(1, Priority::NORMAL, sid));
    SessionInfo* si = sessions.find(sid);
    si->openRequests = 3;

    Request r = makeRequest(1, 0, 100);
    r.session = sid;
    LONGS_EQUAL((int)Status::OK, (int)queue.enqueue(r));

    dispatcher.cancelSession(sid);

    UNSIGNED_LONGS_EQUAL(2, sessions.find(sid)->openRequests);
}

TEST(Dispatcher, CancelSession_L145_OpenRequestsZero_NoUnderflow) {
    MemoryPool pool;
    RequestQueue queue;
    SessionManager sessions;
    PerfMonitor perf;
    FakeAccelBlock hw;
    FakeDevice dev;
    Dispatcher dispatcher(hw, dev, queue, pool, sessions, perf);

    SessionId sid = 0;
    LONGS_EQUAL((int)Status::OK, (int)sessions.open(1, Priority::NORMAL, sid));
    // openRequests defaults to 0 after open(); the guard must keep it from underflowing.

    Request r = makeRequest(1, 0, 100);
    r.session = sid;
    LONGS_EQUAL((int)Status::OK, (int)queue.enqueue(r));

    dispatcher.cancelSession(sid);

    UNSIGNED_LONGS_EQUAL(0, sessions.find(sid)->openRequests);
}

TEST(Dispatcher, CancelSession_L150_RunningJobMatchesSession_CompletionSilenced) {
    MemoryPool pool;
    RequestQueue queue;
    SessionManager sessions;
    PerfMonitor perf;
    FakeAccelBlock hw;
    FakeDevice dev;
    Dispatcher dispatcher(hw, dev, queue, pool, sessions, perf);

    Request r = makeRequest(50, 0, 100);
    r.session = 9;
    r.clientFd = 99;
    hw.submitStatus = Status::OK;
    LONGS_EQUAL((int)Status::OK, (int)queue.enqueue(r));
    dispatcher.pump();
    CHECK_TRUE(dispatcher.isRunning(50));

    dispatcher.cancelSession(9);

    hw::JobResult res{50, Status::OK, 0};
    dispatcher.onCompletion(res);

    UNSIGNED_LONGS_EQUAL(0, dev.wakeCount);
}

TEST(Dispatcher, CancelSession_L150_RunningJobDifferentSession_ClientFdUnaffected) {
    MemoryPool pool;
    RequestQueue queue;
    SessionManager sessions;
    PerfMonitor perf;
    FakeAccelBlock hw;
    FakeDevice dev;
    Dispatcher dispatcher(hw, dev, queue, pool, sessions, perf);

    Request r = makeRequest(51, 0, 100);
    r.session = 9;
    r.clientFd = 99;
    hw.submitStatus = Status::OK;
    LONGS_EQUAL((int)Status::OK, (int)queue.enqueue(r));
    dispatcher.pump();
    CHECK_TRUE(dispatcher.isRunning(51));

    dispatcher.cancelSession(10);   // different session: running_ entry for session 9 is untouched

    hw::JobResult res{51, Status::OK, 0};
    dispatcher.onCompletion(res);

    UNSIGNED_LONGS_EQUAL(1, dev.wakeCount);
}
