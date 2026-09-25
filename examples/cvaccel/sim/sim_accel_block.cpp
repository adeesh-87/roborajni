#include "sim_accel_block.hpp"
#include <chrono>

namespace cvaccel::sim {

SimAccelBlock::SimAccelBlock(uint64_t baseLatencyNs, uint64_t latencyNsPerKiB)
    : baseLatencyNs_(baseLatencyNs), latencyNsPerKiB_(latencyNsPerKiB) {
    for (unsigned i = 0; i < kCoreCount; ++i) {
        cores_[i].thread = std::thread(&SimAccelBlock::run, this, i);
    }
}

SimAccelBlock::~SimAccelBlock() {
    stop_.store(true);
    for (auto& c : cores_) c.cv.notify_all();
    for (auto& c : cores_) {
        if (c.thread.joinable()) c.thread.join();
    }
}

Status SimAccelBlock::submit(const hw::JobDesc& job) {
    unsigned idx = static_cast<unsigned>(job.core);
    if (idx >= kCoreCount) return Status::INVALID_ARG;
    Core& c = cores_[idx];
    {
        std::lock_guard<std::mutex> lock(c.m);
        if (c.hasJob) return Status::BUSY;
        c.job = job;
        c.hasJob = true;
        c.busy.store(true);
    }
    c.cv.notify_one();
    return Status::OK;
}

bool SimAccelBlock::isBusy(CoreType core) const {
    unsigned idx = static_cast<unsigned>(core);
    if (idx >= kCoreCount) return false;
    return cores_[idx].busy.load();
}

void SimAccelBlock::setCompletionHandler(std::function<void(const hw::JobResult&)> handler) {
    std::lock_guard<std::mutex> lock(handlerMtx_);
    handler_ = std::move(handler);
}

void SimAccelBlock::failNext(CoreType core) {
    unsigned idx = static_cast<unsigned>(core);
    if (idx >= kCoreCount) return;
    Core& c = cores_[idx];
    std::lock_guard<std::mutex> lock(c.m);
    c.failNext = true;
}

void SimAccelBlock::run(unsigned coreIndex) {
    Core& c = cores_[coreIndex];
    for (;;) {
        hw::JobDesc job;
        bool fail = false;
        {
            std::unique_lock<std::mutex> lock(c.m);
            c.cv.wait(lock, [&] { return c.hasJob || stop_.load(); });
            if (!c.hasJob) return;   // woken only for shutdown
            job = c.job;
            fail = c.failNext;
            c.failNext = false;
        }

        uint64_t latencyNs = baseLatencyNs_ + latencyNsPerKiB_ * (job.bytes / 1024);
        std::this_thread::sleep_for(std::chrono::nanoseconds(latencyNs));

        hw::JobResult result;
        result.jobId = job.jobId;
        result.status = fail ? Status::HW_ERROR : Status::OK;
        result.hwCycles = job.bytes / 4 + 100;

        std::function<void(const hw::JobResult&)> handlerCopy;
        {
            std::lock_guard<std::mutex> lock(handlerMtx_);
            handlerCopy = handler_;
        }
        if (handlerCopy) handlerCopy(result);

        {
            std::lock_guard<std::mutex> lock(c.m);
            c.hasJob = false;
            c.busy.store(false);
        }
        done_.fetch_add(1);
    }
}

}  // namespace cvaccel::sim
