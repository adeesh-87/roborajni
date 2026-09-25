#pragma once
#include <array>
#include <cstdint>
#include <map>
#include <string>
#include "cvaccel/types.hpp"

namespace cvaccel {

struct PerfRecord {
    RequestId request = 0;
    SessionId session = 0;
    CoreType  core = CoreType::RESIZE;
    uint32_t  bytes = 0;         // memory used by the request
    uint32_t  allocated = 0;     // bytes of the handle it used
    TimeNs    tQueued = 0, tStarted = 0, tFinished = 0;
    uint32_t  hwCycles = 0;
    Status    status = Status::OK;
};

struct PerfStats {
    uint64_t count = 0, failures = 0;
    uint64_t bytesTotal = 0;
    TimeNs   latencySumNs = 0, latencyMaxNs = 0;   // finished - queued
    TimeNs   waitSumNs = 0;                        // started - queued
    TimeNs   avgLatencyNs() const { return count ? latencySumNs / count : 0; }
};

// Records every completed request, keeps per-core and per-session statistics, checks integrity.
class PerfMonitor {
public:
    // returns INTEGRITY when the record is inconsistent (it is still counted under integrityErrors)
    Status   record(const PerfRecord& r);
    const PerfStats& core(CoreType c) const { return perCore_[static_cast<unsigned>(c)]; }
    PerfStats session(SessionId s) const;             // zero stats if unknown
    uint64_t integrityErrors() const { return integrityErrors_; }
    uint64_t totalCount() const;
    std::string report() const;                       // human-readable, one line per core
    void     reset();
    // integrity rules, exposed for testing
    static bool timestampsOk(const PerfRecord& r);    // queued <= started <= finished, finished > 0
    static bool bytesOk(const PerfRecord& r);         // 0 < bytes <= allocated
private:
    std::array<PerfStats, kCoreCount> perCore_{};
    std::map<SessionId, PerfStats> perSession_;
    uint64_t integrityErrors_ = 0;
};

}  // namespace cvaccel
