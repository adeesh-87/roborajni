#include "cvaccel/dispatcher.hpp"
#include "cvaccel/session_manager.hpp"
#include "cvaccel/perf_monitor.hpp"
#include "CppUTest/TestHarness.h"
#include "CppUTestExt/MockSupport.h"

namespace {
using namespace cvaccel;
class Hw : public hw::IAccelBlock {
public:
    Status submit(const hw::JobDesc& j) override { last = j; return st; }
    bool isBusy(CoreType) const override { return false; }
    void setCompletionHandler(std::function<void(const hw::JobResult&)>) override {}
    Status st = Status::OK; hw::JobDesc last{};
};
class Dev : public os::IDevice {
public:
    Status ioctlToClient(ClientFd, IoctlCmd, const void*, size_t) override { return Status::OK; }
    TimeNs nowNs() const override { return 100; }
    uint64_t poolPhysBase() const override { return 0; }
    uint8_t* poolVirtBase() override { return nullptr; }
};
Request req(RequestId id) { Request r; r.id = id; r.session = 1; r.mem = 5; r.bytes = 10; return r; }
}  // namespace

TEST_GROUP(DispatcherWrap) {
    Hw hw; Dev dev; RequestQueue q; MemoryPool pool{1024, 0x1000}; SessionManager sm; PerfMonitor perf;
    void teardown() override { mock().checkExpectations(); mock().clear(); }
};

TEST(DispatcherWrap, SubmitFails_RecordsFailure_Spy) {
    mock("MemoryPool::physAddr").ignoreOtherCalls();
    mock("PerfMonitor::record").expectOneCall("PerfMonitor::record").withUnsignedIntParameter("request", 7)
        .withIntParameter("status", static_cast<int>(Status::HW_ERROR));
    Dispatcher d(hw, dev, q, pool, sm, perf);
    hw.st = Status::HW_ERROR;
    q.enqueue(req(7));
    d.pump();
    UNSIGNED_LONGS_EQUAL(1, perf.totalCount());          // spy: the real record() ran too
}

TEST(DispatcherWrap, Start_UsesPhysAddrOfHandle_Mocked) {
    mock("MemoryPool::physAddr").expectOneCall("MemoryPool::physAddr").withUnsignedIntParameter("h", 5)
        .andReturnValue(static_cast<unsigned long long>(0xABC000));
    Dispatcher d(hw, dev, q, pool, sm, perf);
    q.enqueue(req(8));
    d.pump();
    UNSIGNED_LONGS_EQUAL(0xABC000, hw.last.physAddr);
}

TEST(DispatcherWrap, Completion_RealPath) {
    mock("MemoryPool::physAddr").ignoreOtherCalls();
    mock("PerfMonitor::record").ignoreOtherCalls();
    Dispatcher d(hw, dev, q, pool, sm, perf);
    q.enqueue(req(9));
    d.pump();
    hw::JobResult res{9, Status::OK, 3};
    LONGS_EQUAL(static_cast<int>(Status::OK), static_cast<int>(d.onCompletion(res)));
    UNSIGNED_LONGS_EQUAL(1, perf.totalCount());
}
