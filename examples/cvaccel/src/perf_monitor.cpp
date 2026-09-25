#include "cvaccel/perf_monitor.hpp"
#include <algorithm>
#include <array>

namespace cvaccel {

namespace {
constexpr std::array<const char*, kCoreCount> kCoreNames = {
    "RESIZE", "CONVOLVE", "WARP", "HISTOGRAM", "MATCH"};

void accumulate(PerfStats& s, const PerfRecord& r, bool ok) {
    ++s.count;
    if (!ok) ++s.failures;
    s.bytesTotal += r.bytes;
    TimeNs latency = r.tFinished - r.tQueued;
    s.latencySumNs += latency;
    s.latencyMaxNs = std::max(s.latencyMaxNs, latency);
    s.waitSumNs += (r.tStarted - r.tQueued);
}
}  // namespace

bool PerfMonitor::timestampsOk(const PerfRecord& r) {
    return r.tFinished > 0 && r.tQueued <= r.tStarted && r.tStarted <= r.tFinished;
}

bool PerfMonitor::bytesOk(const PerfRecord& r) {
    return r.bytes > 0 && r.bytes <= r.allocated;
}

Status PerfMonitor::record(const PerfRecord& r) {
    bool tsOk = timestampsOk(r);
    bool byOk = bytesOk(r);
    bool integrityOk = tsOk && byOk;
    if (!integrityOk) ++integrityErrors_;

    bool statusOk = (r.status == Status::OK);
    unsigned coreIdx = static_cast<unsigned>(r.core);
    if (coreIdx < kCoreCount) accumulate(perCore_[coreIdx], r, statusOk);
    accumulate(perSession_[r.session], r, statusOk);

    return integrityOk ? Status::OK : Status::INTEGRITY;
}

PerfStats PerfMonitor::session(SessionId s) const {
    auto it = perSession_.find(s);
    return it == perSession_.end() ? PerfStats{} : it->second;
}

uint64_t PerfMonitor::totalCount() const {
    uint64_t total = 0;
    for (const auto& s : perCore_) total += s.count;
    return total;
}

std::string PerfMonitor::report() const {
    std::string out;
    for (unsigned i = 0; i < kCoreCount; ++i) {
        const PerfStats& s = perCore_[i];
        out += "core " + std::to_string(i) + " " + kCoreNames[i] + ": count=" +
               std::to_string(s.count) + " fail=" + std::to_string(s.failures) +
               " avg=" + std::to_string(s.avgLatencyNs() / 1000) + "us max=" +
               std::to_string(s.latencyMaxNs / 1000) + "us bytes=" +
               std::to_string(s.bytesTotal) + "\n";
    }
    out += "integrity errors=" + std::to_string(integrityErrors_) + "\n";
    return out;
}

void PerfMonitor::reset() {
    perCore_ = std::array<PerfStats, kCoreCount>{};
    perSession_.clear();
    integrityErrors_ = 0;
}

}  // namespace cvaccel
