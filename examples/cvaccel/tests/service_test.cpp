#include "cvaccel/service.hpp"

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

}  // namespace

TEST_GROUP(CvAccelService) {};

TEST(CvAccelService, Handle_L19_PayloadNull_ReturnsInvalidArg) {
    FakeAccelBlock hw;
    FakeDevice dev;
    CvAccelService svc(hw, dev);

    Status st = svc.handle(1, IoctlCmd::OPEN_SESSION, nullptr, 0);

    LONGS_EQUAL((int)Status::INVALID_ARG, (int)st);
}

TEST(CvAccelService, Handle_L19_PayloadNotNull_ProceedsPastNullCheck) {
    FakeAccelBlock hw;
    FakeDevice dev;
    CvAccelService svc(hw, dev);

    GetStatsArgs args{};
    args.session = 5;   // never opened, so ownership check fails rather than the null check

    Status st = svc.handle(1, IoctlCmd::GET_STATS, &args, sizeof(args));

    LONGS_EQUAL((int)Status::NOT_OWNER, (int)st);
}

TEST(CvAccelService, Handle_L21_OpenSessionCmd_CallsOpenSession) {
    FakeAccelBlock hw;
    FakeDevice dev;
    CvAccelService svc(hw, dev);

    OpenSessionArgs args{};
    args.priority = Priority::NORMAL;
    args.outSession = 0;

    Status st = svc.handle(1, IoctlCmd::OPEN_SESSION, &args, sizeof(args));

    LONGS_EQUAL((int)Status::OK, (int)st);
    UNSIGNED_LONGS_EQUAL(1, args.outSession);
}

TEST(CvAccelService, Handle_L21_CloseSessionCmd_CallsCloseSession) {
    FakeAccelBlock hw;
    FakeDevice dev;
    CvAccelService svc(hw, dev);

    OpenSessionArgs open{};
    open.priority = Priority::NORMAL;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::OPEN_SESSION, &open, sizeof(open)));
    SessionId sid = open.outSession;

    Status st = svc.handle(1, IoctlCmd::CLOSE_SESSION, &sid, sizeof(sid));

    LONGS_EQUAL((int)Status::OK, (int)st);
}

TEST(CvAccelService, Handle_L21_AllocMemCmd_CallsAllocMem) {
    FakeAccelBlock hw;
    FakeDevice dev;
    CvAccelService svc(hw, dev);

    OpenSessionArgs open{};
    open.priority = Priority::NORMAL;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::OPEN_SESSION, &open, sizeof(open)));
    SessionId sid = open.outSession;

    AllocMemArgs alloc{};
    alloc.session = sid;
    alloc.bytes = 100;
    alloc.outHandle = 0;

    Status st = svc.handle(1, IoctlCmd::ALLOC_MEM, &alloc, sizeof(alloc));

    LONGS_EQUAL((int)Status::OK, (int)st);
    UNSIGNED_LONGS_EQUAL(1, alloc.outHandle);
}

TEST(CvAccelService, Handle_L21_FreeMemCmd_CallsFreeMem) {
    FakeAccelBlock hw;
    FakeDevice dev;
    CvAccelService svc(hw, dev);

    OpenSessionArgs open{};
    open.priority = Priority::NORMAL;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::OPEN_SESSION, &open, sizeof(open)));
    SessionId sid = open.outSession;

    AllocMemArgs alloc{};
    alloc.session = sid;
    alloc.bytes = 100;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::ALLOC_MEM, &alloc, sizeof(alloc)));

    FreeMemArgs free{};
    free.session = sid;
    free.handle = alloc.outHandle;

    Status st = svc.handle(1, IoctlCmd::FREE_MEM, &free, sizeof(free));

    LONGS_EQUAL((int)Status::OK, (int)st);
}

TEST(CvAccelService, Handle_L21_PostConfigCmd_CallsPostConfig) {
    FakeAccelBlock hw;
    FakeDevice dev;
    CvAccelService svc(hw, dev);

    OpenSessionArgs open{};
    open.priority = Priority::NORMAL;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::OPEN_SESSION, &open, sizeof(open)));
    SessionId sid = open.outSession;

    AllocMemArgs alloc{};
    alloc.session = sid;
    alloc.bytes = 100;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::ALLOC_MEM, &alloc, sizeof(alloc)));

    PostConfigArgs cfg{};
    cfg.session = sid;
    cfg.handle = alloc.outHandle;
    cfg.core = CoreType::RESIZE;
    cfg.bytes = 100;
    cfg.outRequest = 0;

    Status st = svc.handle(1, IoctlCmd::POST_CONFIG, &cfg, sizeof(cfg));

    LONGS_EQUAL((int)Status::OK, (int)st);
    UNSIGNED_LONGS_EQUAL(1, cfg.outRequest);
}

TEST(CvAccelService, Handle_L21_SubmitCmd_CallsSubmit) {
    FakeAccelBlock hw;
    FakeDevice dev;
    CvAccelService svc(hw, dev);

    OpenSessionArgs open{};
    open.priority = Priority::NORMAL;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::OPEN_SESSION, &open, sizeof(open)));
    SessionId sid = open.outSession;

    AllocMemArgs alloc{};
    alloc.session = sid;
    alloc.bytes = 100;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::ALLOC_MEM, &alloc, sizeof(alloc)));

    PostConfigArgs cfg{};
    cfg.session = sid;
    cfg.handle = alloc.outHandle;
    cfg.core = CoreType::RESIZE;
    cfg.bytes = 100;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::POST_CONFIG, &cfg, sizeof(cfg)));

    SubmitArgs sub{};
    sub.session = sid;
    sub.request = cfg.outRequest;

    Status st = svc.handle(1, IoctlCmd::SUBMIT, &sub, sizeof(sub));

    LONGS_EQUAL((int)Status::OK, (int)st);
}

TEST(CvAccelService, Handle_L21_GetStatsCmd_CallsGetStats) {
    FakeAccelBlock hw;
    FakeDevice dev;
    CvAccelService svc(hw, dev);

    OpenSessionArgs open{};
    open.priority = Priority::NORMAL;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::OPEN_SESSION, &open, sizeof(open)));
    SessionId sid = open.outSession;

    GetStatsArgs stats{};
    stats.session = sid;

    Status st = svc.handle(1, IoctlCmd::GET_STATS, &stats, sizeof(stats));

    LONGS_EQUAL((int)Status::OK, (int)st);
    UNSIGNED_LONGS_EQUAL(0, stats.outCount);
}

TEST(CvAccelService, Handle_L21_WakeCmd_ReturnsInvalidArg) {
    FakeAccelBlock hw;
    FakeDevice dev;
    CvAccelService svc(hw, dev);

    int dummy = 0;
    Status st = svc.handle(1, IoctlCmd::WAKE, &dummy, sizeof(dummy));

    LONGS_EQUAL((int)Status::INVALID_ARG, (int)st);
}

TEST(CvAccelService, Handle_L21_UnknownCmd_ReturnsInvalidArg) {
    FakeAccelBlock hw;
    FakeDevice dev;
    CvAccelService svc(hw, dev);

    int dummy = 0;
    Status st = svc.handle(1, static_cast<IoctlCmd>(0xDEAD), &dummy, sizeof(dummy));

    LONGS_EQUAL((int)Status::INVALID_ARG, (int)st);
}

TEST(CvAccelService, Handle_L23_PayloadBytesLessThanOpenSessionArgs_ReturnsInvalidArg) {
    FakeAccelBlock hw;
    FakeDevice dev;
    CvAccelService svc(hw, dev);

    OpenSessionArgs args{};
    args.priority = Priority::NORMAL;

    Status st = svc.handle(1, IoctlCmd::OPEN_SESSION, &args, sizeof(OpenSessionArgs) - 1);

    LONGS_EQUAL((int)Status::INVALID_ARG, (int)st);
}

TEST(CvAccelService, Handle_L23_PayloadBytesAtLeastOpenSessionArgs_CallsOpenSession) {
    FakeAccelBlock hw;
    FakeDevice dev;
    CvAccelService svc(hw, dev);

    OpenSessionArgs args{};
    args.priority = Priority::NORMAL;

    Status st = svc.handle(1, IoctlCmd::OPEN_SESSION, &args, sizeof(OpenSessionArgs));

    LONGS_EQUAL((int)Status::OK, (int)st);
    UNSIGNED_LONGS_EQUAL(1, args.outSession);
}

TEST(CvAccelService, Handle_L26_PayloadBytesLessThanSessionId_ReturnsInvalidArg) {
    FakeAccelBlock hw;
    FakeDevice dev;
    CvAccelService svc(hw, dev);

    SessionId sid = 1;

    Status st = svc.handle(1, IoctlCmd::CLOSE_SESSION, &sid, sizeof(SessionId) - 1);

    LONGS_EQUAL((int)Status::INVALID_ARG, (int)st);
}

TEST(CvAccelService, OpenSession_L52StOk_SetsOutSessionAndReturnsOk) {
    FakeAccelBlock hw;
    FakeDevice dev;
    CvAccelService svc(hw, dev);

    OpenSessionArgs args{};
    args.priority = Priority::NORMAL;
    args.outSession = 0;

    Status st = svc.handle(1, IoctlCmd::OPEN_SESSION, &args, sizeof(args));

    LONGS_EQUAL((int)Status::OK, (int)st);
    UNSIGNED_LONGS_EQUAL(1, args.outSession);
}

TEST(CvAccelService, OpenSession_L52StNotOk_LeavesOutSessionUnset) {
    FakeAccelBlock hw;
    FakeDevice dev;
    CvAccelService svc(hw, dev);

    for (unsigned i = 0; i < kMaxSessions; ++i) {
        OpenSessionArgs args{};
        args.priority = Priority::NORMAL;
        LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::OPEN_SESSION, &args, sizeof(args)));
    }

    OpenSessionArgs args{};
    args.priority = Priority::NORMAL;
    args.outSession = 42;

    Status st = svc.handle(1, IoctlCmd::OPEN_SESSION, &args, sizeof(args));

    LONGS_EQUAL((int)Status::NO_MEMORY, (int)st);
    UNSIGNED_LONGS_EQUAL(42, args.outSession);
}

TEST(CvAccelService, CloseSession_L57NotOwner_ReturnsNotOwner) {
    FakeAccelBlock hw;
    FakeDevice dev;
    CvAccelService svc(hw, dev);

    OpenSessionArgs open{};
    open.priority = Priority::NORMAL;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::OPEN_SESSION, &open, sizeof(open)));
    SessionId sid = open.outSession;

    Status st = svc.handle(2, IoctlCmd::CLOSE_SESSION, &sid, sizeof(sid));

    LONGS_EQUAL((int)Status::NOT_OWNER, (int)st);
}

TEST(CvAccelService, CloseSession_L57Owner_ProceedsPastOwnershipCheck) {
    FakeAccelBlock hw;
    FakeDevice dev;
    CvAccelService svc(hw, dev);

    OpenSessionArgs open{};
    open.priority = Priority::NORMAL;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::OPEN_SESSION, &open, sizeof(open)));
    SessionId sid = open.outSession;

    Status st = svc.handle(1, IoctlCmd::CLOSE_SESSION, &sid, sizeof(sid));

    LONGS_EQUAL((int)Status::OK, (int)st);
}

TEST(CvAccelService, CloseSession_L59LoopZeroIterations_ReturnsOk) {
    FakeAccelBlock hw;
    FakeDevice dev;
    CvAccelService svc(hw, dev);

    OpenSessionArgs open{};
    open.priority = Priority::NORMAL;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::OPEN_SESSION, &open, sizeof(open)));
    SessionId sid = open.outSession;

    // no ALLOC_MEM/POST_CONFIG done, so posted_ is empty: the loop body never runs
    Status st = svc.handle(1, IoctlCmd::CLOSE_SESSION, &sid, sizeof(sid));

    LONGS_EQUAL((int)Status::OK, (int)st);
}

TEST(CvAccelService, CloseSession_L59LoopOneIteration_ErasesPostedEntry) {
    FakeAccelBlock hw;
    FakeDevice dev;
    CvAccelService svc(hw, dev);

    OpenSessionArgs open{};
    open.priority = Priority::NORMAL;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::OPEN_SESSION, &open, sizeof(open)));
    SessionId sid = open.outSession;

    AllocMemArgs alloc{};
    alloc.session = sid;
    alloc.bytes = 100;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::ALLOC_MEM, &alloc, sizeof(alloc)));

    PostConfigArgs cfg{};
    cfg.session = sid;
    cfg.handle = alloc.outHandle;
    cfg.core = CoreType::RESIZE;
    cfg.bytes = 100;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::POST_CONFIG, &cfg, sizeof(cfg)));

    Status closeSt = svc.handle(1, IoctlCmd::CLOSE_SESSION, &sid, sizeof(sid));
    LONGS_EQUAL((int)Status::OK, (int)closeSt);

    // the single posted_ entry was erased, so a submit for it is rejected before the ownership check
    SubmitArgs sub{};
    sub.session = sid;
    sub.request = cfg.outRequest;
    Status subSt = svc.handle(1, IoctlCmd::SUBMIT, &sub, sizeof(sub));

    LONGS_EQUAL((int)Status::INVALID_ARG, (int)subSt);
}

TEST(CvAccelService, CloseSession_L59LoopManyIterations_ErasesAllPostedEntries) {
    FakeAccelBlock hw;
    FakeDevice dev;
    CvAccelService svc(hw, dev);

    OpenSessionArgs open{};
    open.priority = Priority::NORMAL;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::OPEN_SESSION, &open, sizeof(open)));
    SessionId sid = open.outSession;

    RequestId requests[3];
    for (int i = 0; i < 3; ++i) {
        AllocMemArgs alloc{};
        alloc.session = sid;
        alloc.bytes = 100;
        LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::ALLOC_MEM, &alloc, sizeof(alloc)));

        PostConfigArgs cfg{};
        cfg.session = sid;
        cfg.handle = alloc.outHandle;
        cfg.core = CoreType::RESIZE;
        cfg.bytes = 100;
        LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::POST_CONFIG, &cfg, sizeof(cfg)));
        requests[i] = cfg.outRequest;
    }

    Status closeSt = svc.handle(1, IoctlCmd::CLOSE_SESSION, &sid, sizeof(sid));
    LONGS_EQUAL((int)Status::OK, (int)closeSt);

    for (int i = 0; i < 3; ++i) {
        SubmitArgs sub{};
        sub.session = sid;
        sub.request = requests[i];
        Status subSt = svc.handle(1, IoctlCmd::SUBMIT, &sub, sizeof(sub));
        LONGS_EQUAL((int)Status::INVALID_ARG, (int)subSt);
    }
}

TEST(CvAccelService, CloseSession_L60SessionMatches_ErasesEntry) {
    FakeAccelBlock hw;
    FakeDevice dev;
    CvAccelService svc(hw, dev);

    OpenSessionArgs open1{};
    open1.priority = Priority::NORMAL;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::OPEN_SESSION, &open1, sizeof(open1)));
    SessionId sid1 = open1.outSession;

    OpenSessionArgs open2{};
    open2.priority = Priority::NORMAL;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::OPEN_SESSION, &open2, sizeof(open2)));
    SessionId sid2 = open2.outSession;

    AllocMemArgs alloc1{};
    alloc1.session = sid1;
    alloc1.bytes = 100;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::ALLOC_MEM, &alloc1, sizeof(alloc1)));
    PostConfigArgs cfg1{};
    cfg1.session = sid1;
    cfg1.handle = alloc1.outHandle;
    cfg1.core = CoreType::RESIZE;
    cfg1.bytes = 100;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::POST_CONFIG, &cfg1, sizeof(cfg1)));

    AllocMemArgs alloc2{};
    alloc2.session = sid2;
    alloc2.bytes = 100;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::ALLOC_MEM, &alloc2, sizeof(alloc2)));
    PostConfigArgs cfg2{};
    cfg2.session = sid2;
    cfg2.handle = alloc2.outHandle;
    cfg2.core = CoreType::RESIZE;
    cfg2.bytes = 100;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::POST_CONFIG, &cfg2, sizeof(cfg2)));

    // close sid1: its posted_ entry matches (it->second.session == s) and is erased
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::CLOSE_SESSION, &sid1, sizeof(sid1)));

    SubmitArgs sub1{};
    sub1.session = sid1;
    sub1.request = cfg1.outRequest;
    Status subSt1 = svc.handle(1, IoctlCmd::SUBMIT, &sub1, sizeof(sub1));

    LONGS_EQUAL((int)Status::INVALID_ARG, (int)subSt1);
}

TEST(CvAccelService, CloseSession_L60SessionDiffers_KeepsOtherSessionsEntry) {
    FakeAccelBlock hw;
    FakeDevice dev;
    CvAccelService svc(hw, dev);

    OpenSessionArgs open1{};
    open1.priority = Priority::NORMAL;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::OPEN_SESSION, &open1, sizeof(open1)));
    SessionId sid1 = open1.outSession;

    OpenSessionArgs open2{};
    open2.priority = Priority::NORMAL;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::OPEN_SESSION, &open2, sizeof(open2)));
    SessionId sid2 = open2.outSession;

    AllocMemArgs alloc1{};
    alloc1.session = sid1;
    alloc1.bytes = 100;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::ALLOC_MEM, &alloc1, sizeof(alloc1)));
    PostConfigArgs cfg1{};
    cfg1.session = sid1;
    cfg1.handle = alloc1.outHandle;
    cfg1.core = CoreType::RESIZE;
    cfg1.bytes = 100;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::POST_CONFIG, &cfg1, sizeof(cfg1)));

    AllocMemArgs alloc2{};
    alloc2.session = sid2;
    alloc2.bytes = 100;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::ALLOC_MEM, &alloc2, sizeof(alloc2)));
    PostConfigArgs cfg2{};
    cfg2.session = sid2;
    cfg2.handle = alloc2.outHandle;
    cfg2.core = CoreType::RESIZE;
    cfg2.bytes = 100;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::POST_CONFIG, &cfg2, sizeof(cfg2)));

    // close sid1: while iterating, cfg2's entry has (it->second.session == s) FALSE, so it is kept (else: ++it)
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::CLOSE_SESSION, &sid1, sizeof(sid1)));

    SubmitArgs sub2{};
    sub2.session = sid2;
    sub2.request = cfg2.outRequest;
    Status subSt2 = svc.handle(1, IoctlCmd::SUBMIT, &sub2, sizeof(sub2));

    LONGS_EQUAL((int)Status::OK, (int)subSt2);
}

TEST(CvAccelService, AllocMem_L68OwnsFalse_ReturnsNotOwner) {
    FakeAccelBlock hw;
    FakeDevice dev;
    CvAccelService svc(hw, dev);

    OpenSessionArgs open{};
    open.priority = Priority::NORMAL;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::OPEN_SESSION, &open, sizeof(open)));
    SessionId sid = open.outSession;

    AllocMemArgs alloc{};
    alloc.session = sid;
    alloc.bytes = 100;

    Status st = svc.handle(2, IoctlCmd::ALLOC_MEM, &alloc, sizeof(alloc));

    LONGS_EQUAL((int)Status::NOT_OWNER, (int)st);
}

TEST(CvAccelService, AllocMem_L68OwnsTrue_ProceedsPastOwnershipCheck) {
    FakeAccelBlock hw;
    FakeDevice dev;
    CvAccelService svc(hw, dev);

    OpenSessionArgs open{};
    open.priority = Priority::NORMAL;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::OPEN_SESSION, &open, sizeof(open)));
    SessionId sid = open.outSession;

    AllocMemArgs alloc{};
    alloc.session = sid;
    alloc.bytes = 100;

    Status st = svc.handle(1, IoctlCmd::ALLOC_MEM, &alloc, sizeof(alloc));

    LONGS_EQUAL((int)Status::OK, (int)st);
    UNSIGNED_LONGS_EQUAL(1, alloc.outHandle);
}

TEST(CvAccelService, AllocMem_L71StNotOk_ReturnsSt) {
    FakeAccelBlock hw;
    FakeDevice dev;
    CvAccelService svc(hw, dev);

    OpenSessionArgs open{};
    open.priority = Priority::NORMAL;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::OPEN_SESSION, &open, sizeof(open)));
    SessionId sid = open.outSession;

    AllocMemArgs alloc{};
    alloc.session = sid;
    alloc.bytes = 0;   // pool_.allocate() rejects bytes == 0 with INVALID_ARG

    Status st = svc.handle(1, IoctlCmd::ALLOC_MEM, &alloc, sizeof(alloc));

    LONGS_EQUAL((int)Status::INVALID_ARG, (int)st);
}

TEST(CvAccelService, AllocMem_L71StOk_SetsOutHandleAndReturnsOk) {
    FakeAccelBlock hw;
    FakeDevice dev;
    CvAccelService svc(hw, dev);

    OpenSessionArgs open{};
    open.priority = Priority::NORMAL;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::OPEN_SESSION, &open, sizeof(open)));
    SessionId sid = open.outSession;

    AllocMemArgs alloc{};
    alloc.session = sid;
    alloc.bytes = 100;

    Status st = svc.handle(1, IoctlCmd::ALLOC_MEM, &alloc, sizeof(alloc));

    LONGS_EQUAL((int)Status::OK, (int)st);
    UNSIGNED_LONGS_EQUAL(1, alloc.outHandle);
}

TEST(CvAccelService, AllocMem_L73SessionFound_IncrementsBytesAllocated) {
    FakeAccelBlock hw;
    FakeDevice dev;
    CvAccelService svc(hw, dev);

    OpenSessionArgs open{};
    open.priority = Priority::NORMAL;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::OPEN_SESSION, &open, sizeof(open)));
    SessionId sid = open.outSession;

    AllocMemArgs alloc{};
    alloc.session = sid;
    alloc.bytes = 100;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::ALLOC_MEM, &alloc, sizeof(alloc)));

    const SessionInfo* si = svc.sessions().find(sid);
    CHECK(si != nullptr);
    UNSIGNED_LONGS_EQUAL(100, si->bytesAllocated);
}

TEST(CvAccelService, FreeMem_L78OwnsFalse_ReturnsNotOwner) {
    FakeAccelBlock hw;
    FakeDevice dev;
    CvAccelService svc(hw, dev);

    OpenSessionArgs open{};
    open.priority = Priority::NORMAL;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::OPEN_SESSION, &open, sizeof(open)));
    SessionId sid = open.outSession;

    FreeMemArgs free{};
    free.session = sid;
    free.handle = 1;

    Status st = svc.handle(2, IoctlCmd::FREE_MEM, &free, sizeof(free));

    LONGS_EQUAL((int)Status::NOT_OWNER, (int)st);
}

TEST(CvAccelService, FreeMem_L78OwnsTrue_ProceedsPastOwnershipCheck) {
    FakeAccelBlock hw;
    FakeDevice dev;
    CvAccelService svc(hw, dev);

    OpenSessionArgs open{};
    open.priority = Priority::NORMAL;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::OPEN_SESSION, &open, sizeof(open)));
    SessionId sid = open.outSession;

    AllocMemArgs alloc{};
    alloc.session = sid;
    alloc.bytes = 64;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::ALLOC_MEM, &alloc, sizeof(alloc)));

    FreeMemArgs free{};
    free.session = sid;
    free.handle = alloc.outHandle;

    // same fd that owns the session: the ownership check does not short-circuit with NOT_OWNER
    Status st = svc.handle(1, IoctlCmd::FREE_MEM, &free, sizeof(free));

    LONGS_EQUAL((int)Status::OK, (int)st);
}

TEST(CvAccelService, FreeMem_L80BlkTrue_DeductsBlockBytesFromSession) {
    FakeAccelBlock hw;
    FakeDevice dev;
    CvAccelService svc(hw, dev);

    OpenSessionArgs open{};
    open.priority = Priority::NORMAL;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::OPEN_SESSION, &open, sizeof(open)));
    SessionId sid = open.outSession;

    AllocMemArgs alloc{};
    alloc.session = sid;
    alloc.bytes = 100;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::ALLOC_MEM, &alloc, sizeof(alloc)));

    FreeMemArgs free{};
    free.session = sid;
    free.handle = alloc.outHandle;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::FREE_MEM, &free, sizeof(free)));

    // blk was found, so bytes == blk->bytes (100), not 0: bytesAllocated drops all the way to 0
    const SessionInfo* si = svc.sessions().find(sid);
    CHECK(si != nullptr);
    UNSIGNED_LONGS_EQUAL(0, si->bytesAllocated);
}

TEST(CvAccelService, FreeMem_L80BlkFalse_ReturnsInvalidArg) {
    FakeAccelBlock hw;
    FakeDevice dev;
    CvAccelService svc(hw, dev);

    OpenSessionArgs open{};
    open.priority = Priority::NORMAL;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::OPEN_SESSION, &open, sizeof(open)));
    SessionId sid = open.outSession;

    FreeMemArgs free{};
    free.session = sid;
    free.handle = 42;   // never allocated: pool_.find() returns nullptr, so blk is false and bytes defaults to 0

    Status st = svc.handle(1, IoctlCmd::FREE_MEM, &free, sizeof(free));

    LONGS_EQUAL((int)Status::INVALID_ARG, (int)st);
}

TEST(CvAccelService, FreeMem_L82StNotOk_ReturnsSt) {
    FakeAccelBlock hw;
    FakeDevice dev;
    CvAccelService svc(hw, dev);

    OpenSessionArgs open1{};
    open1.priority = Priority::NORMAL;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::OPEN_SESSION, &open1, sizeof(open1)));
    SessionId sid1 = open1.outSession;

    OpenSessionArgs open2{};
    open2.priority = Priority::NORMAL;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::OPEN_SESSION, &open2, sizeof(open2)));
    SessionId sid2 = open2.outSession;

    AllocMemArgs alloc{};
    alloc.session = sid1;
    alloc.bytes = 100;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::ALLOC_MEM, &alloc, sizeof(alloc)));

    FreeMemArgs free{};
    free.session = sid2;          // same fd owns sid2 (passes L78), but the block belongs to sid1
    free.handle = alloc.outHandle;

    Status st = svc.handle(1, IoctlCmd::FREE_MEM, &free, sizeof(free));

    LONGS_EQUAL((int)Status::NOT_OWNER, (int)st);
}

TEST(CvAccelService, FreeMem_L82StOk_ProceedsPastStatusCheck) {
    FakeAccelBlock hw;
    FakeDevice dev;
    CvAccelService svc(hw, dev);

    OpenSessionArgs open{};
    open.priority = Priority::NORMAL;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::OPEN_SESSION, &open, sizeof(open)));
    SessionId sid = open.outSession;

    AllocMemArgs alloc{};
    alloc.session = sid;
    alloc.bytes = 128;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::ALLOC_MEM, &alloc, sizeof(alloc)));

    FreeMemArgs free{};
    free.session = sid;
    free.handle = alloc.outHandle;

    Status st = svc.handle(1, IoctlCmd::FREE_MEM, &free, sizeof(free));

    LONGS_EQUAL((int)Status::OK, (int)st);
}

// L83 (SessionInfo* si = sessions_.find(a.session)) FALSE has no test: sessions_.owns(a.session, fd)
// at L78 already requires sessions_.find(a.session) to succeed with a matching clientFd, and nothing
// between L78 and L83 mutates sessions_ (pool_.release() only touches MemoryPool). So whenever L78
// lets execution reach L83, si is always non-null; this branch is unreachable through the public API.

TEST(CvAccelService, FreeMem_L83SiFound_UpdatesBytesAllocated) {
    FakeAccelBlock hw;
    FakeDevice dev;
    CvAccelService svc(hw, dev);

    OpenSessionArgs open{};
    open.priority = Priority::NORMAL;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::OPEN_SESSION, &open, sizeof(open)));
    SessionId sid = open.outSession;

    AllocMemArgs alloc{};
    alloc.session = sid;
    alloc.bytes = 100;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::ALLOC_MEM, &alloc, sizeof(alloc)));

    FreeMemArgs free{};
    free.session = sid;
    free.handle = alloc.outHandle;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::FREE_MEM, &free, sizeof(free)));

    const SessionInfo* si = svc.sessions().find(sid);
    CHECK(si != nullptr);
    UNSIGNED_LONGS_EQUAL(0, si->bytesAllocated);
}

TEST(CvAccelService, FreeMem_L84BytesLessEqualBytesAllocated_SubtractsBytes) {
    FakeAccelBlock hw;
    FakeDevice dev;
    CvAccelService svc(hw, dev);

    OpenSessionArgs open{};
    open.priority = Priority::NORMAL;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::OPEN_SESSION, &open, sizeof(open)));
    SessionId sid = open.outSession;

    AllocMemArgs alloc1{};
    alloc1.session = sid;
    alloc1.bytes = 100;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::ALLOC_MEM, &alloc1, sizeof(alloc1)));

    AllocMemArgs alloc2{};
    alloc2.session = sid;
    alloc2.bytes = 50;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::ALLOC_MEM, &alloc2, sizeof(alloc2)));
    // bytesAllocated is now 150

    FreeMemArgs free{};
    free.session = sid;
    free.handle = alloc2.outHandle;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::FREE_MEM, &free, sizeof(free)));

    // bytes (50) <= si->bytesAllocated (150) is true: si->bytesAllocated - bytes == 100
    const SessionInfo* si = svc.sessions().find(sid);
    CHECK(si != nullptr);
    UNSIGNED_LONGS_EQUAL(100, si->bytesAllocated);
}

TEST(CvAccelService, FreeMem_L84BytesGreaterThanBytesAllocated_ClampsToZero) {
    FakeAccelBlock hw;
    FakeDevice dev;
    CvAccelService svc(hw, dev);

    OpenSessionArgs open{};
    open.priority = Priority::NORMAL;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::OPEN_SESSION, &open, sizeof(open)));
    SessionId sid = open.outSession;

    // allocate directly through the pool, bypassing allocMem(), so si->bytesAllocated stays 0
    // while the block itself carries real bytes (100)
    MemHandle handle = 0;
    LONGS_EQUAL((int)Status::OK, (int)svc.pool().allocate(sid, 100, handle));

    FreeMemArgs free{};
    free.session = sid;
    free.handle = handle;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::FREE_MEM, &free, sizeof(free)));

    // bytes (100) <= si->bytesAllocated (0) is false: si->bytesAllocated clamps to 0 instead of underflowing
    const SessionInfo* si = svc.sessions().find(sid);
    CHECK(si != nullptr);
    UNSIGNED_LONGS_EQUAL(0, si->bytesAllocated);
}

TEST(CvAccelService, PostConfig_L90OwnsFalse_ReturnsNotOwner) {
    FakeAccelBlock hw;
    FakeDevice dev;
    CvAccelService svc(hw, dev);

    OpenSessionArgs open{};
    open.priority = Priority::NORMAL;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::OPEN_SESSION, &open, sizeof(open)));
    SessionId sid = open.outSession;

    PostConfigArgs cfg{};
    cfg.session = sid;
    cfg.handle = 1;
    cfg.core = CoreType::RESIZE;
    cfg.bytes = 1;

    // fd 1 owns sid; calling with fd 2 fails sessions_.owns(a.session, fd) at L90
    Status st = svc.handle(2, IoctlCmd::POST_CONFIG, &cfg, sizeof(cfg));

    LONGS_EQUAL((int)Status::NOT_OWNER, (int)st);
}

TEST(CvAccelService, PostConfig_L90OwnsTrue_ProceedsPastOwnershipCheck) {
    FakeAccelBlock hw;
    FakeDevice dev;
    CvAccelService svc(hw, dev);

    OpenSessionArgs open{};
    open.priority = Priority::NORMAL;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::OPEN_SESSION, &open, sizeof(open)));
    SessionId sid = open.outSession;

    AllocMemArgs alloc{};
    alloc.session = sid;
    alloc.bytes = 100;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::ALLOC_MEM, &alloc, sizeof(alloc)));

    PostConfigArgs cfg{};
    cfg.session = sid;
    cfg.handle = alloc.outHandle;
    cfg.core = CoreType::RESIZE;
    cfg.bytes = 100;

    // same fd that owns sid: the ownership check does not short-circuit with NOT_OWNER
    Status st = svc.handle(1, IoctlCmd::POST_CONFIG, &cfg, sizeof(cfg));

    LONGS_EQUAL((int)Status::OK, (int)st);
    UNSIGNED_LONGS_EQUAL(1, cfg.outRequest);
}

TEST(CvAccelService, PostConfig_L91CoreTooLarge_ReturnsInvalidArg) {
    FakeAccelBlock hw;
    FakeDevice dev;
    CvAccelService svc(hw, dev);

    OpenSessionArgs open{};
    open.priority = Priority::NORMAL;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::OPEN_SESSION, &open, sizeof(open)));
    SessionId sid = open.outSession;

    AllocMemArgs alloc{};
    alloc.session = sid;
    alloc.bytes = 100;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::ALLOC_MEM, &alloc, sizeof(alloc)));

    PostConfigArgs cfg{};
    cfg.session = sid;
    cfg.handle = alloc.outHandle;
    cfg.core = static_cast<CoreType>(kCoreCount);   // 5: static_cast<unsigned>(a.core) >= kCoreCount is true
    cfg.bytes = 100;

    Status st = svc.handle(1, IoctlCmd::POST_CONFIG, &cfg, sizeof(cfg));

    LONGS_EQUAL((int)Status::INVALID_ARG, (int)st);
}

TEST(CvAccelService, PostConfig_L91CoreValid_ProceedsPastCoreCheck) {
    FakeAccelBlock hw;
    FakeDevice dev;
    CvAccelService svc(hw, dev);

    OpenSessionArgs open{};
    open.priority = Priority::NORMAL;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::OPEN_SESSION, &open, sizeof(open)));
    SessionId sid = open.outSession;

    AllocMemArgs alloc{};
    alloc.session = sid;
    alloc.bytes = 100;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::ALLOC_MEM, &alloc, sizeof(alloc)));

    PostConfigArgs cfg{};
    cfg.session = sid;
    cfg.handle = alloc.outHandle;
    cfg.core = CoreType::MATCH;   // 4 == kCoreCount - 1: the highest valid core, check does not trip
    cfg.bytes = 100;

    Status st = svc.handle(1, IoctlCmd::POST_CONFIG, &cfg, sizeof(cfg));

    LONGS_EQUAL((int)Status::OK, (int)st);
    UNSIGNED_LONGS_EQUAL(1, cfg.outRequest);
}

TEST(CvAccelService, PostConfig_L93BlkNull_ReturnsInvalidArg) {
    FakeAccelBlock hw;
    FakeDevice dev;
    CvAccelService svc(hw, dev);

    OpenSessionArgs open{};
    open.priority = Priority::NORMAL;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::OPEN_SESSION, &open, sizeof(open)));
    SessionId sid = open.outSession;

    PostConfigArgs cfg{};
    cfg.session = sid;
    cfg.handle = 999;   // never allocated: pool_.find() returns nullptr, so !blk is true
    cfg.core = CoreType::RESIZE;
    cfg.bytes = 1;

    Status st = svc.handle(1, IoctlCmd::POST_CONFIG, &cfg, sizeof(cfg));

    LONGS_EQUAL((int)Status::INVALID_ARG, (int)st);
}

TEST(CvAccelService, PostConfig_L93BlkOwnedBySession_ProceedsPastBlockCheck) {
    FakeAccelBlock hw;
    FakeDevice dev;
    CvAccelService svc(hw, dev);

    OpenSessionArgs open{};
    open.priority = Priority::NORMAL;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::OPEN_SESSION, &open, sizeof(open)));
    SessionId sid = open.outSession;

    AllocMemArgs alloc{};
    alloc.session = sid;
    alloc.bytes = 100;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::ALLOC_MEM, &alloc, sizeof(alloc)));

    PostConfigArgs cfg{};
    cfg.session = sid;
    cfg.handle = alloc.outHandle;
    cfg.core = CoreType::RESIZE;
    cfg.bytes = 100;

    // blk is found and blk->owner == a.session: both sub-conditions of L93 are false, so it proceeds
    Status st = svc.handle(1, IoctlCmd::POST_CONFIG, &cfg, sizeof(cfg));

    LONGS_EQUAL((int)Status::OK, (int)st);
    UNSIGNED_LONGS_EQUAL(1, cfg.outRequest);
}

TEST(CvAccelService, PostConfig_L94BytesZero_ReturnsInvalidArg) {
    FakeAccelBlock hw;
    FakeDevice dev;
    CvAccelService svc(hw, dev);

    OpenSessionArgs open{};
    open.priority = Priority::NORMAL;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::OPEN_SESSION, &open, sizeof(open)));
    SessionId sid = open.outSession;

    AllocMemArgs alloc{};
    alloc.session = sid;
    alloc.bytes = 100;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::ALLOC_MEM, &alloc, sizeof(alloc)));

    PostConfigArgs cfg{};
    cfg.session = sid;
    cfg.handle = alloc.outHandle;
    cfg.core = CoreType::RESIZE;
    cfg.bytes = 0;   // a.bytes == 0 is true; a.bytes > blk->bytes would independently trip the same check

    Status st = svc.handle(1, IoctlCmd::POST_CONFIG, &cfg, sizeof(cfg));

    LONGS_EQUAL((int)Status::INVALID_ARG, (int)st);
}

TEST(CvAccelService, PostConfig_L94BytesWithinBlock_ReturnsOk) {
    FakeAccelBlock hw;
    FakeDevice dev;
    CvAccelService svc(hw, dev);

    OpenSessionArgs open{};
    open.priority = Priority::NORMAL;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::OPEN_SESSION, &open, sizeof(open)));
    SessionId sid = open.outSession;

    AllocMemArgs alloc{};
    alloc.session = sid;
    alloc.bytes = 100;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::ALLOC_MEM, &alloc, sizeof(alloc)));

    PostConfigArgs cfg{};
    cfg.session = sid;
    cfg.handle = alloc.outHandle;
    cfg.core = CoreType::RESIZE;
    cfg.bytes = 50;   // a.bytes (50) != 0 and a.bytes (50) <= blk->bytes (100): both sub-conditions false

    Status st = svc.handle(1, IoctlCmd::POST_CONFIG, &cfg, sizeof(cfg));

    LONGS_EQUAL((int)Status::OK, (int)st);
    UNSIGNED_LONGS_EQUAL(1, cfg.outRequest);
}

// L102 (const SessionInfo* si = sessions_.find(a.session)) FALSE has no test: sessions_.owns(a.session, fd)
// at L90 already requires sessions_.find(a.session) to succeed with a matching clientFd, and nothing between
// L90 and L102 mutates sessions_ (pool_.find() only touches MemoryPool). So whenever L90 lets execution reach
// L102, si is always non-null; this branch is unreachable through the public API.

TEST(CvAccelService, PostConfig_L102SiFound_ReturnsOk) {
    FakeAccelBlock hw;
    FakeDevice dev;
    CvAccelService svc(hw, dev);

    OpenSessionArgs open{};
    open.priority = Priority::NORMAL;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::OPEN_SESSION, &open, sizeof(open)));
    SessionId sid = open.outSession;

    AllocMemArgs alloc{};
    alloc.session = sid;
    alloc.bytes = 100;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::ALLOC_MEM, &alloc, sizeof(alloc)));

    PostConfigArgs cfg{};
    cfg.session = sid;
    cfg.handle = alloc.outHandle;
    cfg.core = CoreType::RESIZE;
    cfg.bytes = 100;

    // si is found (see note above), so r.priority is copied from si->priority; Request is private and not
    // exposed by the public API, so the only directly observable effect here is the successful completion.
    Status st = svc.handle(1, IoctlCmd::POST_CONFIG, &cfg, sizeof(cfg));

    LONGS_EQUAL((int)Status::OK, (int)st);
    UNSIGNED_LONGS_EQUAL(1, cfg.outRequest);
}

TEST(CvAccelService, PostConfig_L103ConfigAllZero_CopiesZeroedConfigToRequest) {
    FakeAccelBlock hw;
    FakeDevice dev;
    CvAccelService svc(hw, dev);

    OpenSessionArgs open{};
    open.priority = Priority::NORMAL;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::OPEN_SESSION, &open, sizeof(open)));
    SessionId sid = open.outSession;

    AllocMemArgs alloc{};
    alloc.session = sid;
    alloc.bytes = 100;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::ALLOC_MEM, &alloc, sizeof(alloc)));

    PostConfigArgs cfg{};   // cfg.config is zero-initialized: all kConfigWords words stay 0
    cfg.session = sid;
    cfg.handle = alloc.outHandle;
    cfg.core = CoreType::RESIZE;
    cfg.bytes = 100;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::POST_CONFIG, &cfg, sizeof(cfg)));

    SubmitArgs sub{};
    sub.session = sid;
    sub.request = cfg.outRequest;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::SUBMIT, &sub, sizeof(sub)));

    // the block accepts immediately (FakeAccelBlock.busy == false), so submit() dispatches it right away
    // and hw.lastJob.config carries exactly what the L103 loop copied from cfg.config
    UNSIGNED_LONGS_EQUAL(cfg.outRequest, hw.lastJob.jobId);
    for (unsigned i = 0; i < kConfigWords; ++i) {
        UNSIGNED_LONGS_EQUAL(0, hw.lastJob.config[i]);
    }
}

TEST(CvAccelService, PostConfig_L103ConfigOneWordSet_CopiesWordToRequest) {
    FakeAccelBlock hw;
    FakeDevice dev;
    CvAccelService svc(hw, dev);

    OpenSessionArgs open{};
    open.priority = Priority::NORMAL;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::OPEN_SESSION, &open, sizeof(open)));
    SessionId sid = open.outSession;

    AllocMemArgs alloc{};
    alloc.session = sid;
    alloc.bytes = 100;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::ALLOC_MEM, &alloc, sizeof(alloc)));

    PostConfigArgs cfg{};
    cfg.session = sid;
    cfg.handle = alloc.outHandle;
    cfg.core = CoreType::RESIZE;
    cfg.bytes = 100;
    cfg.config[0] = 0x1234;   // only word 0 set, the rest stay 0
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::POST_CONFIG, &cfg, sizeof(cfg)));

    SubmitArgs sub{};
    sub.session = sid;
    sub.request = cfg.outRequest;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::SUBMIT, &sub, sizeof(sub)));

    UNSIGNED_LONGS_EQUAL(0x1234, hw.lastJob.config[0]);
    for (unsigned i = 1; i < kConfigWords; ++i) {
        UNSIGNED_LONGS_EQUAL(0, hw.lastJob.config[i]);
    }
}

TEST(CvAccelService, PostConfig_L103ConfigAllWordsSet_CopiesAllWordsToRequest) {
    FakeAccelBlock hw;
    FakeDevice dev;
    CvAccelService svc(hw, dev);

    OpenSessionArgs open{};
    open.priority = Priority::NORMAL;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::OPEN_SESSION, &open, sizeof(open)));
    SessionId sid = open.outSession;

    AllocMemArgs alloc{};
    alloc.session = sid;
    alloc.bytes = 100;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::ALLOC_MEM, &alloc, sizeof(alloc)));

    PostConfigArgs cfg{};
    cfg.session = sid;
    cfg.handle = alloc.outHandle;
    cfg.core = CoreType::RESIZE;
    cfg.bytes = 100;
    for (unsigned i = 0; i < kConfigWords; ++i) cfg.config[i] = (i + 1) * 11;   // every word distinct and non-zero
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::POST_CONFIG, &cfg, sizeof(cfg)));

    SubmitArgs sub{};
    sub.session = sid;
    sub.request = cfg.outRequest;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::SUBMIT, &sub, sizeof(sub)));

    for (unsigned i = 0; i < kConfigWords; ++i) {
        UNSIGNED_LONGS_EQUAL((i + 1) * 11, hw.lastJob.config[i]);
    }
}

TEST(CvAccelService, Submit_L113ItEndTrue_ReturnsInvalidArg) {
    FakeAccelBlock hw;
    FakeDevice dev;
    CvAccelService svc(hw, dev);

    OpenSessionArgs open{};
    open.priority = Priority::NORMAL;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::OPEN_SESSION, &open, sizeof(open)));
    SessionId sid = open.outSession;

    // no ALLOC_MEM/POST_CONFIG done, so posted_ is empty: posted_.find(a.request) == posted_.end()
    SubmitArgs sub{};
    sub.session = sid;
    sub.request = 999;

    Status st = svc.handle(1, IoctlCmd::SUBMIT, &sub, sizeof(sub));

    LONGS_EQUAL((int)Status::INVALID_ARG, (int)st);
}

TEST(CvAccelService, Submit_L113ItEndFalse_ProceedsPastLookup) {
    FakeAccelBlock hw;
    FakeDevice dev;
    CvAccelService svc(hw, dev);

    OpenSessionArgs open{};
    open.priority = Priority::NORMAL;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::OPEN_SESSION, &open, sizeof(open)));
    SessionId sid = open.outSession;

    AllocMemArgs alloc{};
    alloc.session = sid;
    alloc.bytes = 100;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::ALLOC_MEM, &alloc, sizeof(alloc)));

    PostConfigArgs cfg{};
    cfg.session = sid;
    cfg.handle = alloc.outHandle;
    cfg.core = CoreType::RESIZE;
    cfg.bytes = 100;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::POST_CONFIG, &cfg, sizeof(cfg)));

    SubmitArgs sub{};
    sub.session = sid;
    sub.request = cfg.outRequest;

    Status st = svc.handle(1, IoctlCmd::SUBMIT, &sub, sizeof(sub));

    LONGS_EQUAL((int)Status::OK, (int)st);
}

TEST(CvAccelService, Submit_L114SessionMismatch_ReturnsNotOwner) {
    FakeAccelBlock hw;
    FakeDevice dev;
    CvAccelService svc(hw, dev);

    OpenSessionArgs open1{};
    open1.priority = Priority::NORMAL;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::OPEN_SESSION, &open1, sizeof(open1)));
    SessionId sid1 = open1.outSession;

    OpenSessionArgs open2{};
    open2.priority = Priority::NORMAL;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::OPEN_SESSION, &open2, sizeof(open2)));
    SessionId sid2 = open2.outSession;

    AllocMemArgs alloc{};
    alloc.session = sid1;
    alloc.bytes = 100;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::ALLOC_MEM, &alloc, sizeof(alloc)));

    PostConfigArgs cfg{};
    cfg.session = sid1;
    cfg.handle = alloc.outHandle;
    cfg.core = CoreType::RESIZE;
    cfg.bytes = 100;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::POST_CONFIG, &cfg, sizeof(cfg)));

    // fd 1 owns sid2 too (sessions_.owns(a.session, fd) is true), so the session mismatch
    // (it->second.session == sid1 != a.session == sid2) alone trips L114; a wrong fd would
    // independently trip it too via !sessions_.owns(a.session, fd).
    SubmitArgs sub{};
    sub.session = sid2;
    sub.request = cfg.outRequest;

    Status st = svc.handle(1, IoctlCmd::SUBMIT, &sub, sizeof(sub));

    LONGS_EQUAL((int)Status::NOT_OWNER, (int)st);
}

TEST(CvAccelService, Submit_L114BothFalse_ProceedsPastOwnershipCheck) {
    FakeAccelBlock hw;
    FakeDevice dev;
    CvAccelService svc(hw, dev);

    OpenSessionArgs open{};
    open.priority = Priority::NORMAL;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::OPEN_SESSION, &open, sizeof(open)));
    SessionId sid = open.outSession;

    AllocMemArgs alloc{};
    alloc.session = sid;
    alloc.bytes = 100;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::ALLOC_MEM, &alloc, sizeof(alloc)));

    PostConfigArgs cfg{};
    cfg.session = sid;
    cfg.handle = alloc.outHandle;
    cfg.core = CoreType::RESIZE;
    cfg.bytes = 100;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::POST_CONFIG, &cfg, sizeof(cfg)));

    // it->second.session == a.session and sessions_.owns(a.session, fd) is true: both sub-conditions
    // of L114 are false, so it proceeds past the ownership check instead of returning NOT_OWNER
    SubmitArgs sub{};
    sub.session = sid;
    sub.request = cfg.outRequest;

    Status st = svc.handle(1, IoctlCmd::SUBMIT, &sub, sizeof(sub));

    LONGS_EQUAL((int)Status::OK, (int)st);
}

TEST(CvAccelService, Submit_L118StNotOk_ReturnsSt) {
    FakeAccelBlock hw;
    FakeDevice dev;
    CvAccelService svc(hw, dev);

    OpenSessionArgs open{};
    open.priority = Priority::NORMAL;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::OPEN_SESSION, &open, sizeof(open)));
    SessionId sid = open.outSession;

    // keep the block busy so pump() never drains the RESIZE queue while we fill it to kMaxQueuePerCore
    hw.busy = true;

    for (unsigned i = 0; i < kMaxQueuePerCore; ++i) {
        AllocMemArgs alloc{};
        alloc.session = sid;
        alloc.bytes = 100;
        LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::ALLOC_MEM, &alloc, sizeof(alloc)));

        PostConfigArgs cfg{};
        cfg.session = sid;
        cfg.handle = alloc.outHandle;
        cfg.core = CoreType::RESIZE;
        cfg.bytes = 100;
        LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::POST_CONFIG, &cfg, sizeof(cfg)));

        SubmitArgs sub{};
        sub.session = sid;
        sub.request = cfg.outRequest;
        LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::SUBMIT, &sub, sizeof(sub)));
    }

    AllocMemArgs alloc{};
    alloc.session = sid;
    alloc.bytes = 100;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::ALLOC_MEM, &alloc, sizeof(alloc)));

    PostConfigArgs cfg{};
    cfg.session = sid;
    cfg.handle = alloc.outHandle;
    cfg.core = CoreType::RESIZE;
    cfg.bytes = 100;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::POST_CONFIG, &cfg, sizeof(cfg)));

    // the RESIZE queue is at kMaxQueuePerCore: queue_.enqueue() returns QUEUE_FULL
    SubmitArgs sub{};
    sub.session = sid;
    sub.request = cfg.outRequest;

    Status st = svc.handle(1, IoctlCmd::SUBMIT, &sub, sizeof(sub));

    LONGS_EQUAL((int)Status::QUEUE_FULL, (int)st);
}

TEST(CvAccelService, Submit_L118StOk_ProceedsPastStatusCheck) {
    FakeAccelBlock hw;
    FakeDevice dev;
    CvAccelService svc(hw, dev);

    OpenSessionArgs open{};
    open.priority = Priority::NORMAL;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::OPEN_SESSION, &open, sizeof(open)));
    SessionId sid = open.outSession;

    AllocMemArgs alloc{};
    alloc.session = sid;
    alloc.bytes = 100;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::ALLOC_MEM, &alloc, sizeof(alloc)));

    PostConfigArgs cfg{};
    cfg.session = sid;
    cfg.handle = alloc.outHandle;
    cfg.core = CoreType::RESIZE;
    cfg.bytes = 100;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::POST_CONFIG, &cfg, sizeof(cfg)));

    // queue_.enqueue() succeeds (st == Status::OK): it does not return st early at L118
    SubmitArgs sub{};
    sub.session = sid;
    sub.request = cfg.outRequest;

    Status st = svc.handle(1, IoctlCmd::SUBMIT, &sub, sizeof(sub));

    LONGS_EQUAL((int)Status::OK, (int)st);
}

TEST(CvAccelService, Submit_L121SiFound_IncrementsOpenRequests) {
    FakeAccelBlock hw;
    FakeDevice dev;
    CvAccelService svc(hw, dev);

    OpenSessionArgs open{};
    open.priority = Priority::NORMAL;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::OPEN_SESSION, &open, sizeof(open)));
    SessionId sid = open.outSession;

    AllocMemArgs alloc{};
    alloc.session = sid;
    alloc.bytes = 100;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::ALLOC_MEM, &alloc, sizeof(alloc)));

    PostConfigArgs cfg{};
    cfg.session = sid;
    cfg.handle = alloc.outHandle;
    cfg.core = CoreType::RESIZE;
    cfg.bytes = 100;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::POST_CONFIG, &cfg, sizeof(cfg)));

    SubmitArgs sub{};
    sub.session = sid;
    sub.request = cfg.outRequest;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::SUBMIT, &sub, sizeof(sub)));

    // si is found (see note below on L114 requiring sessions_.owns() to already succeed), so
    // si->openRequests is incremented from 0 to 1
    const SessionInfo* si = svc.sessions().find(sid);
    CHECK(si != nullptr);
    UNSIGNED_LONGS_EQUAL(1, si->openRequests);
}

// L121 (SessionInfo* si = sessions_.find(a.session)) FALSE has no test: sessions_.owns(a.session, fd)
// at L114 already requires sessions_.find(a.session) to succeed with a matching clientFd, and nothing
// between L114 and L121 mutates sessions_ (dev_.nowNs() and queue_.enqueue() only touch time/the queue).
// So whenever L114 lets execution reach L121, si is always non-null; this branch is unreachable through
// the public API.

TEST(CvAccelService, GetStats_L128OwnsFalse_ReturnsNotOwner) {
    FakeAccelBlock hw;
    FakeDevice dev;
    CvAccelService svc(hw, dev);

    OpenSessionArgs open{};
    open.priority = Priority::NORMAL;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::OPEN_SESSION, &open, sizeof(open)));
    SessionId sid = open.outSession;

    GetStatsArgs stats{};
    stats.session = sid;

    // fd 1 owns sid; calling with fd 2 fails sessions_.owns(a.session, fd) at L128
    Status st = svc.handle(2, IoctlCmd::GET_STATS, &stats, sizeof(stats));

    LONGS_EQUAL((int)Status::NOT_OWNER, (int)st);
}

TEST(CvAccelService, GetStats_L128OwnsTrue_ReturnsOkAndZeroedStats) {
    FakeAccelBlock hw;
    FakeDevice dev;
    CvAccelService svc(hw, dev);

    OpenSessionArgs open{};
    open.priority = Priority::NORMAL;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::OPEN_SESSION, &open, sizeof(open)));
    SessionId sid = open.outSession;

    GetStatsArgs stats{};
    stats.session = sid;

    // same fd that owns sid: the ownership check does not short-circuit with NOT_OWNER; perf_.session()
    // returns zeroed PerfStats since no request has ever completed for this session
    Status st = svc.handle(1, IoctlCmd::GET_STATS, &stats, sizeof(stats));

    LONGS_EQUAL((int)Status::OK, (int)st);
    UNSIGNED_LONGS_EQUAL(0, stats.outCount);
    UNSIGNED_LONGS_EQUAL(0, stats.outAvgLatencyNs);
    UNSIGNED_LONGS_EQUAL(0, stats.outBytes);
    UNSIGNED_LONGS_EQUAL(0, stats.outIntegrityErrors);
}

TEST(CvAccelService, ClientDisconnected_TypicalClient_ClosesAllItsSessions) {
    FakeAccelBlock hw;
    FakeDevice dev;
    CvAccelService svc(hw, dev);

    OpenSessionArgs open1{};
    open1.priority = Priority::NORMAL;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::OPEN_SESSION, &open1, sizeof(open1)));
    SessionId sid1 = open1.outSession;

    OpenSessionArgs open2{};
    open2.priority = Priority::NORMAL;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::OPEN_SESSION, &open2, sizeof(open2)));
    SessionId sid2 = open2.outSession;

    svc.clientDisconnected(1);

    // closeSession() was called for every active session of clientFd 1: SessionManager::close()
    // deactivates the slot, so find() returns nullptr for both
    CHECK(svc.sessions().find(sid1) == nullptr);
    CHECK(svc.sessions().find(sid2) == nullptr);
}

TEST(CvAccelService, OnHwCompletion_TypicalCompletion_RecordsAndWakesClient) {
    FakeAccelBlock hw;
    FakeDevice dev;
    CvAccelService svc(hw, dev);

    OpenSessionArgs open{};
    open.priority = Priority::NORMAL;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::OPEN_SESSION, &open, sizeof(open)));
    SessionId sid = open.outSession;

    AllocMemArgs alloc{};
    alloc.session = sid;
    alloc.bytes = 100;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::ALLOC_MEM, &alloc, sizeof(alloc)));

    PostConfigArgs cfg{};
    cfg.session = sid;
    cfg.handle = alloc.outHandle;
    cfg.core = CoreType::RESIZE;
    cfg.bytes = 100;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::POST_CONFIG, &cfg, sizeof(cfg)));

    // FakeAccelBlock.busy == false, so submit() dispatches the job to hw straight away and it
    // becomes a running request tracked by the dispatcher
    SubmitArgs sub{};
    sub.session = sid;
    sub.request = cfg.outRequest;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::SUBMIT, &sub, sizeof(sub)));
    UNSIGNED_LONGS_EQUAL(0, dev.wakeCount);

    hw::JobResult res{};
    res.jobId = cfg.outRequest;
    res.status = Status::OK;
    res.hwCycles = 42;

    svc.onHwCompletion(res);

    // dispatcher_.onCompletion() found the running request, recorded it, decremented openRequests,
    // and woke the client fd via dev_.ioctlToClient(); dispatcher_.pump() then ran with an empty queue
    const SessionInfo* si = svc.sessions().find(sid);
    CHECK(si != nullptr);
    UNSIGNED_LONGS_EQUAL(0, si->openRequests);
    UNSIGNED_LONGS_EQUAL(1, dev.wakeCount);
}

TEST(CvAccelService, Pump_TypicalQueuedRequest_ReturnsDispatcherPumpCount) {
    FakeAccelBlock hw;
    hw.busy = true;   // keep the request in the queue instead of letting submit()'s internal pump() start it
    FakeDevice dev;
    CvAccelService svc(hw, dev);

    OpenSessionArgs open{};
    open.priority = Priority::NORMAL;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::OPEN_SESSION, &open, sizeof(open)));
    SessionId sid = open.outSession;

    AllocMemArgs alloc{};
    alloc.session = sid;
    alloc.bytes = 100;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::ALLOC_MEM, &alloc, sizeof(alloc)));

    PostConfigArgs cfg{};
    cfg.session = sid;
    cfg.handle = alloc.outHandle;
    cfg.core = CoreType::RESIZE;
    cfg.bytes = 100;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::POST_CONFIG, &cfg, sizeof(cfg)));

    SubmitArgs sub{};
    sub.session = sid;
    sub.request = cfg.outRequest;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::SUBMIT, &sub, sizeof(sub)));

    hw.busy = false;   // free the core so pump() can dispatch the queued request

    // pump() returns exactly what dispatcher_.pump() returns: one queued request, one free core,
    // FakeAccelBlock.submit() defaults to Status::OK, so start() succeeds and started == 1
    UNSIGNED_LONGS_EQUAL(1, svc.pump());
}

TEST(CvAccelService, Queued_TypicalPendingRequest_ReturnsQueueSizeTotal) {
    FakeAccelBlock hw;
    hw.busy = true;   // keep the request queued instead of letting submit()'s internal pump() drain it
    FakeDevice dev;
    CvAccelService svc(hw, dev);

    OpenSessionArgs open{};
    open.priority = Priority::NORMAL;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::OPEN_SESSION, &open, sizeof(open)));
    SessionId sid = open.outSession;

    AllocMemArgs alloc{};
    alloc.session = sid;
    alloc.bytes = 100;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::ALLOC_MEM, &alloc, sizeof(alloc)));

    PostConfigArgs cfg{};
    cfg.session = sid;
    cfg.handle = alloc.outHandle;
    cfg.core = CoreType::RESIZE;
    cfg.bytes = 100;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::POST_CONFIG, &cfg, sizeof(cfg)));

    SubmitArgs sub{};
    sub.session = sid;
    sub.request = cfg.outRequest;
    LONGS_EQUAL((int)Status::OK, (int)svc.handle(1, IoctlCmd::SUBMIT, &sub, sizeof(sub)));

    // hw stayed busy through submit()'s internal pump(), so the request is still sitting in the
    // RequestQueue: queued() returns queue_.sizeTotal(), which is 1
    UNSIGNED_LONGS_EQUAL(1, svc.queued());
}
