#pragma once
#include <array>
#include <atomic>
#include <condition_variable>
#include <deque>
#include <functional>
#include <mutex>
#include <thread>
#include "cvaccel/hw_block.hpp"

namespace cvaccel::sim {

// Simulated accelerator block: one worker thread per core. A job takes latencyNsPerKiB * bytes/1024 + baseLatencyNs
// of wall time, then the completion handler is called from the core's thread. Each core accepts at most one job at
// a time (submit returns BUSY otherwise). failNext(core) makes the next job on that core complete with HW_ERROR.
class SimAccelBlock : public hw::IAccelBlock {
public:
    explicit SimAccelBlock(uint64_t baseLatencyNs = 20000, uint64_t latencyNsPerKiB = 1000);
    ~SimAccelBlock() override;
    Status   submit(const hw::JobDesc& job) override;
    bool     isBusy(CoreType core) const override;
    void     setCompletionHandler(std::function<void(const hw::JobResult&)> handler) override;
    void     failNext(CoreType core);
    uint64_t jobsDone() const { return done_.load(); }
private:
    struct Core { std::thread thread; std::mutex m; std::condition_variable cv; bool hasJob = false; hw::JobDesc job{}; bool failNext = false; std::atomic<bool> busy{false}; };
    void run(unsigned coreIndex);
    std::array<Core, kCoreCount> cores_;
    std::function<void(const hw::JobResult&)> handler_;
    std::mutex handlerMtx_;
    std::atomic<bool> stop_{false};
    std::atomic<uint64_t> done_{0};
    uint64_t baseLatencyNs_, latencyNsPerKiB_;
};

}  // namespace cvaccel::sim
