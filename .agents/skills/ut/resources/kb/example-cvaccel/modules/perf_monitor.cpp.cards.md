# Cards for src/perf_monitor.cpp (9 functions)

## accumulate  (src/perf_monitor.cpp:11-19)
Signature: void accumulate(PerfStats& s, const PerfRecord& r, bool ok)
Params: s (PerfStats& s); r (const PerfRecord& r); ok (bool ok)
Decisions (drive each outcome; loops: 0, 1, many):
  L13    if       (!ok)
Callers: PerfMonitor::record() (src/perf_monitor.cpp)
Existing tests calling it directly: none

## PerfMonitor::timestampsOk  (src/perf_monitor.cpp:22-24)
Signature: bool PerfMonitor::timestampsOk(const PerfRecord& r)
Params: r (const PerfRecord& r)
Decisions: none (straight-line code)
Returns: r.tFinished > 0 && r.tQueued <= r.tStarted && r...
Callers: PerfMonitor::record() (src/perf_monitor.cpp)
Existing tests calling it directly: TEST(PerfMonitor, TimestampsOk_TypicalInputs_ReturnsTrue) (tests/perf_monitor_test.cpp:L51)

## PerfMonitor::coreBytesOk  (src/perf_monitor.cpp:26-26)
Signature: bool PerfMonitor::coreBytesOk(const PerfRecord& r)
Params: r (const PerfRecord& r)
Decisions: none (straight-line code)
Returns: r.bytes <= kMaxJobBytes
Callers: PerfMonitor::record() (src/perf_monitor.cpp)
Existing tests calling it directly: TEST(CvAccelService, PerfMonitorCoreBytesOk_TypicalInputs_ReturnsTrue) (tests/service_test.cpp:L1884); TEST(PerfMonitor, CoreBytesOk_BytesAtLimit_ReturnsTrue) (tests/perf_monitor_test.cpp:L64)

## PerfMonitor::bytesOk  (src/perf_monitor.cpp:28-30)
Signature: bool PerfMonitor::bytesOk(const PerfRecord& r)
Params: r (const PerfRecord& r)
Decisions: none (straight-line code)
Returns: r.bytes > 0 && r.bytes <= r.allocated
Callers: PerfMonitor::record() (src/perf_monitor.cpp)
Existing tests calling it directly: TEST(PerfMonitor, BytesOk_TypicalInputs_ReturnsTrue) (tests/perf_monitor_test.cpp:L57)

## PerfMonitor::record  (src/perf_monitor.cpp:32-44)
Signature: Status PerfMonitor::record(const PerfRecord& r)
Params: r (const PerfRecord& r)
Decisions (drive each outcome; loops: 0, 1, many):
  L36    if       (!integrityOk)
  L40    if       (coreIdx < kCoreCount)
  L43    ?:       integrityOk
Returns: integrityOk ? Status::OK : Status::INTEGRITY
Calls: PerfMonitor::bytesOk() (src/perf_monitor.cpp:L28); PerfMonitor::coreBytesOk() (src/perf_monitor.cpp:L26); PerfMonitor::timestampsOk() (src/perf_monitor.cpp:L22); accumulate() (src/perf_monitor.cpp:L11)
Callers: Dispatcher::onCompletion() (src/dispatcher.cpp); Dispatcher::pump() (src/dispatcher.cpp)
Existing tests calling it directly: TEST(CvAccelService, PerfMonitorRecord_CoreIndexOutOfRange_SkipsPerCoreAccumulation) (tests/service_test.cpp:L1856); TEST(CvAccelService, PerfMonitorRecord_CoreIndexWithinRange_AccumulatesPerCoreStats) (tests/service_test.cpp:L1847); TEST(CvAccelService, PerfMonitorRecord_IntegrityNotOk_IncrementsIntegrityErrors) (tests/service_test.cpp:L1829); TEST(CvAccelService, PerfMonitorRecord_IntegrityNotOk_ReturnsIntegrity) (tests/service_test.cpp:L1874); TEST(CvAccelService, PerfMonitorRecord_IntegrityOk_IntegrityErrorsStayZero) (tests/service_test.cpp:L1839); TEST(CvAccelService, PerfMonitorRecord_IntegrityOk_ReturnsOk) (tests/service_test.cpp:L1866); TEST(PerfMonitor, Accumulate_StatusNotOk_IncrementsFailures) (tests/perf_monitor_test.cpp:L32); TEST(PerfMonitor, Accumulate_StatusOk_FailuresStayZero) (tests/perf_monitor_test.cpp:L42)

## PerfMonitor::session  (src/perf_monitor.cpp:46-49)
Signature: PerfStats PerfMonitor::session(SessionId s) const
Params: s (SessionId s)
Decisions (drive each outcome; loops: 0, 1, many):
  L48    ?:       it == perSession_.end()
Returns: it == perSession_.end() ? PerfStats{} : it->second
Callers: CvAccelService::getStats() (src/service.cpp)
Existing tests calling it directly: TEST(CvAccelService, PerfMonitorRecord_CoreIndexOutOfRange_SkipsPerCoreAccumulation) (tests/service_test.cpp:L1856); TEST(CvClient, Constructor_TypicalTransport_SessionIsZero) (tests/cvclient_test.cpp:L19); TEST(PerfMonitor, Record_CoreIndexOutOfRange_SkipsPerCoreAccumulation) (tests/perf_monitor_test.cpp:L99); TEST(PerfMonitor, Reset_TypicalInputs_ClearsAllStats) (tests/perf_monitor_test.cpp:L233); TEST(PerfMonitor, Session_KnownSession_ReturnsAccumulatedStats) (tests/perf_monitor_test.cpp:L142); TEST(PerfMonitor, Session_UnknownSession_ReturnsZeroStats) (tests/perf_monitor_test.cpp:L127)

## PerfMonitor::totalCount  (src/perf_monitor.cpp:51-55)
Signature: uint64_t PerfMonitor::totalCount() const
Decisions: none (straight-line code)
Returns: total
Existing tests calling it directly: TEST(CvAccelService, PerfMonitorRecord_CoreIndexOutOfRange_SkipsPerCoreAccumulation) (tests/service_test.cpp:L1856); TEST(Dispatcher, OnCompletion_L90_JobIdNotInRunning_ReturnsInvalidArg) (tests/dispatcher_test.cpp:L472); TEST(Dispatcher, Pump_L43_StatusNotOk_DoesNotIncrementStarted) (tests/dispatcher_test.cpp:L375); TEST(Dispatcher, Pump_L47_StatusBusy_ReEnqueuesRequestAndBreaks) (tests/dispatcher_test.cpp:L395); TEST(Dispatcher, Pump_L47_StatusNotBusy_RecordsFailureInPlace) (tests/dispatcher_test.cpp:L415); TEST(PerfMonitor, Record_CoreIndexOutOfRange_SkipsPerCoreAccumulation) (tests/perf_monitor_test.cpp:L99); TEST(PerfMonitor, Reset_TypicalInputs_ClearsAllStats) (tests/perf_monitor_test.cpp:L233); TEST(PerfMonitor, TotalCount_TypicalInputs_ReturnsSumAcrossCores) (tests/perf_monitor_test.cpp:L156)

## PerfMonitor::report  (src/perf_monitor.cpp:57-69)
Signature: std::string PerfMonitor::report() const
Decisions (drive each outcome; loops: 0, 1, many):
  L59    for      (unsigned i = 0; i < kCoreCount; ++i)
Returns: out
Existing tests calling it directly: TEST(PerfMonitor, Report_ManyRecordsRecorded_ReflectsAllRecords) (tests/perf_monitor_test.cpp:L200); TEST(PerfMonitor, Report_NoRecordsRecorded_ReturnsAllZeroStats) (tests/perf_monitor_test.cpp:L169); TEST(PerfMonitor, Report_OneRecordRecorded_ReflectsThatRecord) (tests/perf_monitor_test.cpp:L183)

## PerfMonitor::reset  (src/perf_monitor.cpp:71-75)
Signature: void PerfMonitor::reset()
Decisions: none (straight-line code)
Existing tests calling it directly: TEST(PerfMonitor, Reset_TypicalInputs_ClearsAllStats) (tests/perf_monitor_test.cpp:L233)
# dependencies of src/perf_monitor.cpp  (mock/stub candidates first; 'in-scope code' = another scanned file, often an existing mock)
