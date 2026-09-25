#pragma once
#include <cstdint>
#include <cstddef>
#include <functional>
#include "cvaccel/types.hpp"

namespace cvclient {

// Transport between a client application and the service: on the SoC an open("/dev/cvaccel") fd and ioctl();
// in-process the sim connects it straight to CvAccelService::handle. Wake-ups arrive on onWake (any thread).
class ITransport {
public:
    virtual ~ITransport() = default;
    virtual cvaccel::ClientFd fd() const = 0;
    virtual cvaccel::Status   ioctl(cvaccel::IoctlCmd cmd, void* payload, size_t bytes) = 0;
    virtual void setWakeHandler(std::function<void(const cvaccel::CompletionInfo&)> h) = 0;
};

struct Completion { cvaccel::RequestId request; cvaccel::Status status; uint64_t latencyNs; uint32_t hwCycles; };

// Client-side API (static library libcvclient). One Client per session. Thread-safe wait.
class Client {
public:
    explicit Client(ITransport& t);
    ~Client();
    cvaccel::Status openSession(cvaccel::Priority prio);
    cvaccel::Status closeSession();
    cvaccel::Status allocMem(uint32_t bytes, cvaccel::MemHandle& out);
    cvaccel::Status freeMem(cvaccel::MemHandle h);
    // posts a configuration for core with the given memory; returns the request id
    cvaccel::Status postConfig(cvaccel::MemHandle mem, cvaccel::CoreType core, uint32_t bytes, const uint32_t config[cvaccel::kConfigWords], cvaccel::RequestId& out);
    cvaccel::Status submit(cvaccel::RequestId r);
    // blocks until the request completes or timeoutMs passes (BUSY on timeout)
    cvaccel::Status wait(cvaccel::RequestId r, Completion& out, uint32_t timeoutMs);
    cvaccel::Status getStats(uint64_t& count, uint64_t& avgLatencyNs, uint64_t& bytes, uint64_t& integrityErrors);
    cvaccel::SessionId session() const { return session_; }
private:
    struct Impl; Impl* impl_;
    ITransport& t_;
    cvaccel::SessionId session_ = 0;
};

}  // namespace cvclient
