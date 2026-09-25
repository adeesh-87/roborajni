#pragma once
#include <cstdint>
#include <cstddef>
#include <mutex>
#include "cvaccel/types.hpp"
#include "cvaccel/hw_block.hpp"
#include "cvaccel/device.hpp"
#include "cvaccel/session_manager.hpp"
#include "cvaccel/memory_pool.hpp"
#include "cvaccel/request_queue.hpp"
#include "cvaccel/dispatcher.hpp"
#include "cvaccel/perf_monitor.hpp"

namespace cvaccel {

// Payloads of the client -> service ioctls (POD, copied through the ioctl boundary)
struct OpenSessionArgs  { Priority priority; SessionId outSession; };
struct AllocMemArgs     { SessionId session; uint32_t bytes; MemHandle outHandle; };
struct FreeMemArgs      { SessionId session; MemHandle handle; };
struct PostConfigArgs   { SessionId session; MemHandle handle; CoreType core; uint32_t bytes; uint32_t config[kConfigWords]; RequestId outRequest; };
struct SubmitArgs       { SessionId session; RequestId request; };
struct GetStatsArgs     { SessionId session; uint64_t outCount; uint64_t outAvgLatencyNs; uint64_t outBytes; uint64_t outIntegrityErrors; };

// The base app: one instance per SoC. handle() is the ioctl entry point for every client command.
class CvAccelService {
public:
    CvAccelService(hw::IAccelBlock& hw, os::IDevice& dev);
    ~CvAccelService();
    // dispatches on cmd; payload must point to the matching *Args struct of at least payloadBytes
    Status   handle(ClientFd clientFd, IoctlCmd cmd, void* payload, size_t payloadBytes);
    // a client's fd was closed: close all its sessions
    void     clientDisconnected(ClientFd clientFd);
    // completion path: called by the block's completion handler (any thread)
    void     onHwCompletion(const hw::JobResult& res);
    // maintenance: retry submissions the block refused earlier (call periodically or after a completion)
    unsigned pump();
    const PerfMonitor& perf() const { return perf_; }
    MemoryPool&        pool()       { return pool_; }
    const SessionManager& sessions() const { return sessions_; }
    unsigned queued() const;
private:
    Status openSession(ClientFd fd, OpenSessionArgs& a);
    Status closeSession(ClientFd fd, SessionId s);
    Status allocMem(ClientFd fd, AllocMemArgs& a);
    Status freeMem(ClientFd fd, FreeMemArgs& a);
    Status postConfig(ClientFd fd, PostConfigArgs& a);
    Status submit(ClientFd fd, SubmitArgs& a);
    Status getStats(ClientFd fd, GetStatsArgs& a);

    hw::IAccelBlock& hw_; os::IDevice& dev_;
    mutable std::mutex mtx_;
    SessionManager sessions_; MemoryPool pool_; RequestQueue queue_; PerfMonitor perf_; Dispatcher dispatcher_;
    std::unordered_map<RequestId, Request> posted_;   // configured, not yet submitted
    RequestId nextRequest_ = 1;
};

}  // namespace cvaccel
