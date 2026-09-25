#pragma once
#include <mutex>
#include <unordered_map>
#include "cvaccel/types.hpp"
#include "cvaccel/hw_block.hpp"
#include "cvaccel/device.hpp"
#include "cvaccel/request_queue.hpp"
#include "cvaccel/memory_pool.hpp"
#include "cvaccel/session_manager.hpp"
#include "cvaccel/perf_monitor.hpp"

namespace cvaccel {

// Moves queued requests to free cores and turns hardware completions into client wake-ups.
// Not thread-safe by itself: the service holds its mutex around every call; onCompletion() is called
// by the service's completion handler, also under the mutex.
class Dispatcher {
public:
    Dispatcher(hw::IAccelBlock& hw, os::IDevice& dev, RequestQueue& q, MemoryPool& pool, SessionManager& sm, PerfMonitor& perf);
    // submits as many queued requests as the block accepts; returns how many were started
    unsigned pump();
    // hardware completion for one job: perf record, session bookkeeping, wake-up ioctl. Returns INVALID_ARG for an unknown job.
    Status   onCompletion(const hw::JobResult& res);
    // a session is closing: its running jobs stay in flight but will not wake anybody; queued ones are cancelled (wake with CANCELLED)
    unsigned cancelSession(SessionId session);
    unsigned inFlight() const { return static_cast<unsigned>(running_.size()); }
    bool     isRunning(RequestId id) const { return running_.count(id) != 0; }
private:
    Status   start(Request& r);
    hw::IAccelBlock& hw_; os::IDevice& dev_; RequestQueue& queue_; MemoryPool& pool_; SessionManager& sessions_; PerfMonitor& perf_;
    std::unordered_map<RequestId, Request> running_;     // jobs handed to the hardware
};

}  // namespace cvaccel
