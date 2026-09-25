#include "cvaccel/dispatcher.hpp"
#include <vector>

namespace cvaccel {

namespace {
uint32_t reservedBytesOf(const MemoryPool& pool, MemHandle h) {
    const MemBlock* blk = pool.find(h);
    return blk ? static_cast<uint32_t>(blk->reserved) : 0;
}
}  // namespace

Dispatcher::Dispatcher(hw::IAccelBlock& hw, os::IDevice& dev, RequestQueue& q, MemoryPool& pool,
                        SessionManager& sm, PerfMonitor& perf)
    : hw_(hw), dev_(dev), queue_(q), pool_(pool), sessions_(sm), perf_(perf) {}

Status Dispatcher::start(Request& r) {
    hw::JobDesc job{};
    job.jobId = r.id;
    job.core = r.core;
    job.physAddr = pool_.physAddr(r.mem);
    job.bytes = r.bytes;
    for (unsigned i = 0; i < kConfigWords; ++i) job.config[i] = r.config[i];

    Status st = hw_.submit(job);
    if (st == Status::OK) {
        r.tStarted = dev_.nowNs();
        running_.emplace(r.id, r);
    }
    return st;
}

unsigned Dispatcher::pump() {
    unsigned started = 0;
    for (unsigned c = 0; c < kCoreCount; ++c) {
        CoreType core = static_cast<CoreType>(c);
        while (!hw_.isBusy(core)) {
            Request r;
            if (!queue_.dequeue(core, r)) break;

            Status st = start(r);
            if (st == Status::OK) {
                ++started;
                continue;
            }
            if (st == Status::BUSY) {
                // The block refused right after reporting itself free (a race in a real driver);
                // put the request back where it came from and stop trying this core for now.
                queue_.enqueue(r);
                break;
            }

            // The job never made it to hardware: fail it in place, exactly like a completion.
            TimeNs now = dev_.nowNs();
            PerfRecord rec;
            rec.request = r.id;
            rec.session = r.session;
            rec.core = r.core;
            rec.bytes = r.bytes;
            rec.allocated = reservedBytesOf(pool_, r.mem);
            rec.tQueued = r.tQueued;
            rec.tStarted = now;
            rec.tFinished = now;
            rec.hwCycles = 0;
            rec.status = st;
            perf_.record(rec);

            CompletionInfo info{};
            info.request = r.id;
            info.session = r.session;
            info.status = st;
            info.latencyNs = rec.tFinished - rec.tQueued;
            info.hwCycles = 0;
            if (r.clientFd != -1) {
                // See onCompletion(): this in-process sim's wake handler never calls back into
                // the service, so it is safe to hold the service mutex while calling it here.
                dev_.ioctlToClient(r.clientFd, IoctlCmd::WAKE, &info, sizeof(info));
            }

            SessionInfo* si = sessions_.find(r.session);
            if (si && si->openRequests > 0) --si->openRequests;
        }
    }
    return started;
}

Status Dispatcher::onCompletion(const hw::JobResult& res) {
    auto it = running_.find(res.jobId);
    if (it == running_.end()) return Status::INVALID_ARG;
    Request r = it->second;

    PerfRecord rec;
    rec.request = r.id;
    rec.session = r.session;
    rec.core = r.core;
    rec.bytes = r.bytes;
    rec.allocated = reservedBytesOf(pool_, r.mem);
    rec.tQueued = r.tQueued;
    rec.tStarted = r.tStarted;
    rec.tFinished = dev_.nowNs();
    rec.hwCycles = res.hwCycles;
    rec.status = res.status;
    perf_.record(rec);

    SessionInfo* si = sessions_.find(r.session);
    if (si && si->openRequests > 0) --si->openRequests;

    // r.clientFd is set to -1 by cancelSession() for jobs whose session closed while they were
    // still running (see below), so this also covers "the session is no longer active".
    if (r.clientFd != -1) {
        CompletionInfo info{};
        info.request = r.id;
        info.session = r.session;
        info.status = res.status;
        info.latencyNs = rec.tFinished - rec.tQueued;
        info.hwCycles = res.hwCycles;
        // Not calling this under mtx_ would let a queued completion race a session close; in this
        // in-process sim the client's wake handler never calls back into the service, so holding
        // the service mutex (via the caller) across this ioctl is safe.
        dev_.ioctlToClient(r.clientFd, IoctlCmd::WAKE, &info, sizeof(info));
    }

    running_.erase(it);
    return Status::OK;
}

unsigned Dispatcher::cancelSession(SessionId session) {
    std::vector<RequestId> removed;
    queue_.cancelSession(session, removed);

    SessionInfo* si = sessions_.find(session);
    ClientFd fd = si ? si->clientFd : -1;

    for (RequestId id : removed) {
        if (fd != -1) {
            CompletionInfo info{};
            info.request = id;
            info.session = session;
            info.status = Status::CANCELLED;
            info.latencyNs = 0;
            info.hwCycles = 0;
            dev_.ioctlToClient(fd, IoctlCmd::WAKE, &info, sizeof(info));
        }
        if (si && si->openRequests > 0) --si->openRequests;
    }

    // Jobs already handed to the hardware keep running; mark them so their completion is silent.
    for (auto& kv : running_) {
        if (kv.second.session == session) kv.second.clientFd = -1;
    }

    return static_cast<unsigned>(removed.size());
}

}  // namespace cvaccel
