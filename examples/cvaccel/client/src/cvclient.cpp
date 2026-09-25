#include "cvclient/cvclient.hpp"

#include <chrono>
#include <condition_variable>
#include <map>
#include <mutex>

#include "cvaccel/service.hpp"

namespace cvclient {

using namespace cvaccel;

struct Client::Impl {
    std::mutex mtx;
    std::condition_variable cv;
    std::map<RequestId, Completion> completions;
};

Client::Client(ITransport& t) : impl_(new Impl), t_(t) {
    t_.setWakeHandler([this](const CompletionInfo& ci) {
        std::lock_guard<std::mutex> lock(impl_->mtx);
        impl_->completions[ci.request] = Completion{ci.request, ci.status, ci.latencyNs, ci.hwCycles};
        impl_->cv.notify_all();
    });
}

Client::~Client() {
    if (session_ != 0) closeSession();
    delete impl_;
}

Status Client::openSession(Priority prio) {
    OpenSessionArgs a{prio, 0};
    Status s = t_.ioctl(IoctlCmd::OPEN_SESSION, &a, sizeof a);
    if (s == Status::OK) session_ = a.outSession;
    return s;
}

Status Client::closeSession() {
    if (session_ == 0) return Status::NO_SESSION;
    SubmitArgs a{session_, 0};
    Status s = t_.ioctl(IoctlCmd::CLOSE_SESSION, &a, sizeof a);
    session_ = 0;
    return s;
}

Status Client::allocMem(uint32_t bytes, MemHandle& out) {
    if (session_ == 0) return Status::NO_SESSION;
    AllocMemArgs a{session_, bytes, 0};
    Status s = t_.ioctl(IoctlCmd::ALLOC_MEM, &a, sizeof a);
    if (s == Status::OK) out = a.outHandle;
    return s;
}

Status Client::freeMem(MemHandle h) {
    if (session_ == 0) return Status::NO_SESSION;
    FreeMemArgs a{session_, h};
    return t_.ioctl(IoctlCmd::FREE_MEM, &a, sizeof a);
}

Status Client::postConfig(MemHandle mem, CoreType core, uint32_t bytes,
                           const uint32_t config[kConfigWords], RequestId& out) {
    if (session_ == 0) return Status::NO_SESSION;
    PostConfigArgs a{};
    a.session = session_;
    a.handle = mem;
    a.core = core;
    a.bytes = bytes;
    for (unsigned i = 0; i < kConfigWords; ++i) a.config[i] = config[i];
    Status s = t_.ioctl(IoctlCmd::POST_CONFIG, &a, sizeof a);
    if (s == Status::OK) out = a.outRequest;
    return s;
}

Status Client::submit(RequestId r) {
    if (session_ == 0) return Status::NO_SESSION;
    SubmitArgs a{session_, r};
    return t_.ioctl(IoctlCmd::SUBMIT, &a, sizeof a);
}

Status Client::wait(RequestId r, Completion& out, uint32_t timeoutMs) {
    std::unique_lock<std::mutex> lock(impl_->mtx);
    auto it = impl_->completions.find(r);
    if (it != impl_->completions.end()) {
        out = it->second;
        impl_->completions.erase(it);
        return Status::OK;
    }
    bool got = impl_->cv.wait_for(lock, std::chrono::milliseconds(timeoutMs), [&] {
        it = impl_->completions.find(r);
        return it != impl_->completions.end();
    });
    if (!got) return Status::BUSY;
    out = it->second;
    impl_->completions.erase(it);
    return Status::OK;
}

Status Client::getStats(uint64_t& count, uint64_t& avgLatencyNs, uint64_t& bytes, uint64_t& integrityErrors) {
    if (session_ == 0) return Status::NO_SESSION;
    GetStatsArgs a{};
    a.session = session_;
    Status s = t_.ioctl(IoctlCmd::GET_STATS, &a, sizeof a);
    if (s == Status::OK) {
        count = a.outCount;
        avgLatencyNs = a.outAvgLatencyNs;
        bytes = a.outBytes;
        integrityErrors = a.outIntegrityErrors;
    }
    return s;
}

}  // namespace cvclient
