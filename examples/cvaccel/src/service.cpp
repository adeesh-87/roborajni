#include "cvaccel/service.hpp"
#include <vector>

namespace cvaccel {

CvAccelService::CvAccelService(hw::IAccelBlock& hw, os::IDevice& dev)
    : hw_(hw),
      dev_(dev),
      pool_(kPoolBytes, dev.poolPhysBase(), dev.poolVirtBase()),
      dispatcher_(hw_, dev_, queue_, pool_, sessions_, perf_) {
    hw_.setCompletionHandler([this](const hw::JobResult& res) { onHwCompletion(res); });
}

CvAccelService::~CvAccelService() {
    hw_.setCompletionHandler(nullptr);
}

Status CvAccelService::handle(ClientFd clientFd, IoctlCmd cmd, void* payload, size_t payloadBytes) {
    if (payload == nullptr) return Status::INVALID_ARG;
    std::lock_guard<std::mutex> lock(mtx_);
    switch (cmd) {
        case IoctlCmd::OPEN_SESSION:
            if (payloadBytes < sizeof(OpenSessionArgs)) return Status::INVALID_ARG;
            return openSession(clientFd, *static_cast<OpenSessionArgs*>(payload));
        case IoctlCmd::CLOSE_SESSION:
            if (payloadBytes < sizeof(SessionId)) return Status::INVALID_ARG;
            return closeSession(clientFd, *static_cast<SessionId*>(payload));
        case IoctlCmd::ALLOC_MEM:
            if (payloadBytes < sizeof(AllocMemArgs)) return Status::INVALID_ARG;
            return allocMem(clientFd, *static_cast<AllocMemArgs*>(payload));
        case IoctlCmd::FREE_MEM:
            if (payloadBytes < sizeof(FreeMemArgs)) return Status::INVALID_ARG;
            return freeMem(clientFd, *static_cast<FreeMemArgs*>(payload));
        case IoctlCmd::POST_CONFIG:
            if (payloadBytes < sizeof(PostConfigArgs)) return Status::INVALID_ARG;
            return postConfig(clientFd, *static_cast<PostConfigArgs*>(payload));
        case IoctlCmd::SUBMIT:
            if (payloadBytes < sizeof(SubmitArgs)) return Status::INVALID_ARG;
            return submit(clientFd, *static_cast<SubmitArgs*>(payload));
        case IoctlCmd::GET_STATS:
            if (payloadBytes < sizeof(GetStatsArgs)) return Status::INVALID_ARG;
            return getStats(clientFd, *static_cast<GetStatsArgs*>(payload));
        case IoctlCmd::WAKE:
        default:
            return Status::INVALID_ARG;   // service -> client only, or unknown command
    }
}

Status CvAccelService::openSession(ClientFd fd, OpenSessionArgs& a) {
    SessionId id = 0;
    Status st = sessions_.open(fd, a.priority, id);
    if (st == Status::OK) a.outSession = id;
    return st;
}

Status CvAccelService::closeSession(ClientFd fd, SessionId s) {
    if (!sessions_.owns(s, fd)) return Status::NOT_OWNER;
    dispatcher_.cancelSession(s);
    for (auto it = posted_.begin(); it != posted_.end();) {
        if (it->second.session == s) it = posted_.erase(it);
        else ++it;
    }
    pool_.releaseAll(s);
    return sessions_.close(s);
}

Status CvAccelService::allocMem(ClientFd fd, AllocMemArgs& a) {
    if (!sessions_.owns(a.session, fd)) return Status::NOT_OWNER;
    MemHandle h = 0;
    Status st = pool_.allocate(a.session, a.bytes, h);
    if (st != Status::OK) return st;
    a.outHandle = h;
    if (SessionInfo* si = sessions_.find(a.session)) si->bytesAllocated += a.bytes;
    return Status::OK;
}

Status CvAccelService::freeMem(ClientFd fd, FreeMemArgs& a) {
    if (!sessions_.owns(a.session, fd)) return Status::NOT_OWNER;
    const MemBlock* blk = pool_.find(a.handle);
    uint64_t bytes = blk ? blk->bytes : 0;
    Status st = pool_.release(a.handle, a.session);
    if (st != Status::OK) return st;
    if (SessionInfo* si = sessions_.find(a.session)) {
        si->bytesAllocated = (bytes <= si->bytesAllocated) ? si->bytesAllocated - bytes : 0;
    }
    return Status::OK;
}

Status CvAccelService::postConfig(ClientFd fd, PostConfigArgs& a) {
    if (!sessions_.owns(a.session, fd)) return Status::NOT_OWNER;
    if (static_cast<unsigned>(a.core) >= kCoreCount) return Status::INVALID_ARG;
    const MemBlock* blk = pool_.find(a.handle);
    if (!blk || blk->owner != a.session) return Status::INVALID_ARG;
    if (a.bytes == 0 || a.bytes > blk->bytes) return Status::INVALID_ARG;

    Request r;
    r.id = nextRequest_++;
    r.session = a.session;
    r.clientFd = fd;
    r.mem = a.handle;
    r.core = a.core;
    if (const SessionInfo* si = sessions_.find(a.session)) r.priority = si->priority;
    for (unsigned i = 0; i < kConfigWords; ++i) r.config[i] = a.config[i];
    r.bytes = a.bytes;

    posted_.emplace(r.id, r);
    a.outRequest = r.id;
    return Status::OK;
}

Status CvAccelService::submit(ClientFd fd, SubmitArgs& a) {
    auto it = posted_.find(a.request);
    if (it == posted_.end()) return Status::INVALID_ARG;
    if (it->second.session != a.session || !sessions_.owns(a.session, fd)) return Status::NOT_OWNER;

    it->second.tQueued = dev_.nowNs();
    Status st = queue_.enqueue(it->second);
    if (st != Status::OK) return st;   // e.g. QUEUE_FULL: leave it posted so the client can retry

    posted_.erase(it);
    if (SessionInfo* si = sessions_.find(a.session)) ++si->openRequests;

    dispatcher_.pump();
    return Status::OK;
}

Status CvAccelService::getStats(ClientFd fd, GetStatsArgs& a) {
    if (!sessions_.owns(a.session, fd)) return Status::NOT_OWNER;
    PerfStats s = perf_.session(a.session);
    a.outCount = s.count;
    a.outAvgLatencyNs = s.avgLatencyNs();
    a.outBytes = s.bytesTotal;
    a.outIntegrityErrors = perf_.integrityErrors();
    return Status::OK;
}

void CvAccelService::clientDisconnected(ClientFd clientFd) {
    std::lock_guard<std::mutex> lock(mtx_);
    std::vector<SessionId> ids;
    sessions_.forEachOfClient(clientFd, [&ids](const SessionInfo& s) { ids.push_back(s.id); });
    for (SessionId id : ids) closeSession(clientFd, id);
}

void CvAccelService::onHwCompletion(const hw::JobResult& res) {
    std::lock_guard<std::mutex> lock(mtx_);
    dispatcher_.onCompletion(res);
    dispatcher_.pump();
}

unsigned CvAccelService::pump() {
    std::lock_guard<std::mutex> lock(mtx_);
    return dispatcher_.pump();
}

unsigned CvAccelService::queued() const {
    std::lock_guard<std::mutex> lock(mtx_);
    return queue_.sizeTotal();
}

}  // namespace cvaccel
