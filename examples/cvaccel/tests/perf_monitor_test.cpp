#include "cvaccel/perf_monitor.hpp"

#include "CppUTest/TestHarness.h"

namespace {

using namespace cvaccel;

PerfRecord makeValidRecord() {
    PerfRecord r;
    r.request = 1;
    r.session = 1;
    r.core = CoreType::RESIZE;
    r.bytes = 50;
    r.allocated = 100;
    r.tQueued = 100;
    r.tStarted = 150;
    r.tFinished = 200;
    r.hwCycles = 10;
    r.status = Status::OK;
    return r;
}

}  // namespace

TEST_GROUP(PerfMonitor) {};

// accumulate() has internal (anonymous-namespace) linkage in src/perf_monitor.cpp, so it cannot be
// called directly from this translation unit. It is exercised through PerfMonitor::record(), which
// passes ok = (r.status == Status::OK) into accumulate().
// L13 true: r.status != Status::OK -> !ok is true -> failures is incremented.
TEST(PerfMonitor, Accumulate_StatusNotOk_IncrementsFailures) {
    PerfMonitor monitor;
    PerfRecord r = makeValidRecord();
    r.status = Status::HW_ERROR;
    monitor.record(r);
    UNSIGNED_LONGS_EQUAL(1, monitor.core(CoreType::RESIZE).count);
    UNSIGNED_LONGS_EQUAL(1, monitor.core(CoreType::RESIZE).failures);
}

// L13 false: r.status == Status::OK -> !ok is false -> failures stays 0.
TEST(PerfMonitor, Accumulate_StatusOk_FailuresStayZero) {
    PerfMonitor monitor;
    PerfRecord r = makeValidRecord();
    monitor.record(r);
    UNSIGNED_LONGS_EQUAL(1, monitor.core(CoreType::RESIZE).count);
    UNSIGNED_LONGS_EQUAL(0, monitor.core(CoreType::RESIZE).failures);
}

// Straight-line: tFinished > 0, tQueued <= tStarted <= tFinished -> all true.
TEST(PerfMonitor, TimestampsOk_TypicalInputs_ReturnsTrue) {
    PerfRecord r = makeValidRecord();
    CHECK_TRUE(PerfMonitor::timestampsOk(r));
}

// Straight-line: bytes > 0 and bytes <= allocated -> true.
TEST(PerfMonitor, BytesOk_TypicalInputs_ReturnsTrue) {
    PerfRecord r = makeValidRecord();
    CHECK_TRUE(PerfMonitor::bytesOk(r));
}

// L34 true: bytesOk() is false (bytes = 0), so integrityOk is false -> !integrityOk increments
// integrityErrors_.
TEST(PerfMonitor, Record_IntegrityNotOk_IncrementsIntegrityErrors) {
    PerfMonitor monitor;
    PerfRecord r = makeValidRecord();
    r.bytes = 0;
    monitor.record(r);
    UNSIGNED_LONGS_EQUAL(1, monitor.integrityErrors());
}

// L34 false: both timestampsOk() and bytesOk() are true, so integrityOk is true -> integrityErrors_
// stays 0.
TEST(PerfMonitor, Record_IntegrityOk_IntegrityErrorsStayZero) {
    PerfMonitor monitor;
    PerfRecord r = makeValidRecord();
    monitor.record(r);
    UNSIGNED_LONGS_EQUAL(0, monitor.integrityErrors());
}

// L38 true: coreIdx (0, RESIZE) < kCoreCount (5) -> accumulate() runs on perCore_[0].
TEST(PerfMonitor, Record_CoreIndexWithinRange_AccumulatesPerCoreStats) {
    PerfMonitor monitor;
    PerfRecord r = makeValidRecord();
    monitor.record(r);
    UNSIGNED_LONGS_EQUAL(1, monitor.core(CoreType::RESIZE).count);
}

// L38 false: r.core is cast to a value (5) outside the valid CoreType range, so coreIdx (5) is not
// < kCoreCount (5) -> the per-core accumulate() call is skipped, while perSession_ is still updated.
TEST(PerfMonitor, Record_CoreIndexOutOfRange_SkipsPerCoreAccumulation) {
    PerfMonitor monitor;
    PerfRecord r = makeValidRecord();
    r.core = static_cast<CoreType>(5);
    monitor.record(r);
    UNSIGNED_LONGS_EQUAL(0, monitor.totalCount());
    UNSIGNED_LONGS_EQUAL(1, monitor.session(r.session).count);
}

// L41 true: integrityOk is true -> record() returns Status::OK.
TEST(PerfMonitor, Record_IntegrityOk_ReturnsOk) {
    PerfMonitor monitor;
    PerfRecord r = makeValidRecord();
    Status status = monitor.record(r);
    CHECK(status == Status::OK);
}

// L41 false: integrityOk is false (bytes = 0) -> record() returns Status::INTEGRITY.
TEST(PerfMonitor, Record_IntegrityNotOk_ReturnsIntegrity) {
    PerfMonitor monitor;
    PerfRecord r = makeValidRecord();
    r.bytes = 0;
    Status status = monitor.record(r);
    CHECK(status == Status::INTEGRITY);
}

// L46 true: session(s) for an id never recorded -> it == perSession_.end() -> returns PerfStats{}
// (all fields zero).
TEST(PerfMonitor, Session_UnknownSession_ReturnsZeroStats) {
    PerfMonitor monitor;
    PerfRecord r = makeValidRecord();
    monitor.record(r);
    PerfStats stats = monitor.session(999);
    UNSIGNED_LONGS_EQUAL(0, stats.count);
    UNSIGNED_LONGS_EQUAL(0, stats.failures);
    UNSIGNED_LONGS_EQUAL(0, stats.bytesTotal);
    UNSIGNED_LONGS_EQUAL(0, stats.latencySumNs);
    UNSIGNED_LONGS_EQUAL(0, stats.latencyMaxNs);
}

// L46 false: session(s) for an id that was recorded -> it != perSession_.end() -> returns
// it->second, the accumulated stats for that session (one record: latency = 200-100 = 100,
// wait = 150-100 = 50).
TEST(PerfMonitor, Session_KnownSession_ReturnsAccumulatedStats) {
    PerfMonitor monitor;
    PerfRecord r = makeValidRecord();
    monitor.record(r);
    PerfStats stats = monitor.session(1);
    UNSIGNED_LONGS_EQUAL(1, stats.count);
    UNSIGNED_LONGS_EQUAL(0, stats.failures);
    UNSIGNED_LONGS_EQUAL(50, stats.bytesTotal);
    UNSIGNED_LONGS_EQUAL(100, stats.latencySumNs);
    UNSIGNED_LONGS_EQUAL(100, stats.latencyMaxNs);
}

// Straight-line: total sums count across all perCore_ entries. Two records on different cores ->
// total = 1 + 1 = 2.
TEST(PerfMonitor, TotalCount_TypicalInputs_ReturnsSumAcrossCores) {
    PerfMonitor monitor;
    PerfRecord r1 = makeValidRecord();
    r1.core = CoreType::RESIZE;
    monitor.record(r1);
    PerfRecord r2 = makeValidRecord();
    r2.core = CoreType::CONVOLVE;
    monitor.record(r2);
    UNSIGNED_LONGS_EQUAL(2, monitor.totalCount());
}

// L57 loop 0 iterations of record(): fresh monitor, no records -> every perCore_ entry is
// PerfStats{} (count=0, avg=0, max=0, bytes=0) and integrityErrors_ = 0.
TEST(PerfMonitor, Report_NoRecordsRecorded_ReturnsAllZeroStats) {
    PerfMonitor monitor;
    std::string expected =
        "core 0 RESIZE: count=0 fail=0 avg=0us max=0us bytes=0\n"
        "core 1 CONVOLVE: count=0 fail=0 avg=0us max=0us bytes=0\n"
        "core 2 WARP: count=0 fail=0 avg=0us max=0us bytes=0\n"
        "core 3 HISTOGRAM: count=0 fail=0 avg=0us max=0us bytes=0\n"
        "core 4 MATCH: count=0 fail=0 avg=0us max=0us bytes=0\n"
        "integrity errors=0\n";
    STRCMP_EQUAL(expected.c_str(), monitor.report().c_str());
}

// L57 loop 1 iteration worth of data: one record on RESIZE -> that core's line reflects it
// (count=1, latency=100ns -> avg=0us, max=0us, bytes=50), the remaining cores stay zero.
TEST(PerfMonitor, Report_OneRecordRecorded_ReflectsThatRecord) {
    PerfMonitor monitor;
    PerfRecord r = makeValidRecord();
    monitor.record(r);
    std::string expected =
        "core 0 RESIZE: count=1 fail=0 avg=0us max=0us bytes=50\n"
        "core 1 CONVOLVE: count=0 fail=0 avg=0us max=0us bytes=0\n"
        "core 2 WARP: count=0 fail=0 avg=0us max=0us bytes=0\n"
        "core 3 HISTOGRAM: count=0 fail=0 avg=0us max=0us bytes=0\n"
        "core 4 MATCH: count=0 fail=0 avg=0us max=0us bytes=0\n"
        "integrity errors=0\n";
    STRCMP_EQUAL(expected.c_str(), monitor.report().c_str());
}

// L57 loop many iterations worth of data: two records on RESIZE (count=2, bytesTotal=50+30=80,
// latencySumNs=100+3000=3100 -> avg=1550ns=1us, latencyMaxNs=3000ns=3us), one record on CONVOLVE
// with bytes=0 (fails bytesOk -> integrityErrors_ = 1; status stays OK so failures unaffected).
TEST(PerfMonitor, Report_ManyRecordsRecorded_ReflectsAllRecords) {
    PerfMonitor monitor;

    PerfRecord r1 = makeValidRecord();
    monitor.record(r1);

    PerfRecord r2 = makeValidRecord();
    r2.session = 2;
    r2.bytes = 30;
    r2.tQueued = 0;
    r2.tStarted = 0;
    r2.tFinished = 3000;
    monitor.record(r2);

    PerfRecord r3 = makeValidRecord();
    r3.session = 3;
    r3.core = CoreType::CONVOLVE;
    r3.bytes = 0;
    monitor.record(r3);

    std::string expected =
        "core 0 RESIZE: count=2 fail=0 avg=1us max=3us bytes=80\n"
        "core 1 CONVOLVE: count=1 fail=0 avg=0us max=0us bytes=0\n"
        "core 2 WARP: count=0 fail=0 avg=0us max=0us bytes=0\n"
        "core 3 HISTOGRAM: count=0 fail=0 avg=0us max=0us bytes=0\n"
        "core 4 MATCH: count=0 fail=0 avg=0us max=0us bytes=0\n"
        "integrity errors=1\n";
    STRCMP_EQUAL(expected.c_str(), monitor.report().c_str());
}

// Straight-line: reset() is void, so there is no return value to assert; it clears perCore_,
// perSession_ and integrityErrors_. After recording data (including an integrity failure) and
// resetting, core stats, session stats, totalCount() and integrityErrors() all revert to zero.
TEST(PerfMonitor, Reset_TypicalInputs_ClearsAllStats) {
    PerfMonitor monitor;
    PerfRecord r = makeValidRecord();
    monitor.record(r);
    PerfRecord bad = makeValidRecord();
    bad.bytes = 0;
    monitor.record(bad);

    monitor.reset();

    UNSIGNED_LONGS_EQUAL(0, monitor.totalCount());
    UNSIGNED_LONGS_EQUAL(0, monitor.core(CoreType::RESIZE).count);
    UNSIGNED_LONGS_EQUAL(0, monitor.session(1).count);
    UNSIGNED_LONGS_EQUAL(0, monitor.integrityErrors());
}
