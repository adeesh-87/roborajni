#pragma once
#include <cstdint>
#include <functional>
#include "cvaccel/types.hpp"

namespace cvaccel::hw {

struct JobDesc {
    uint32_t jobId;                    // == RequestId
    CoreType core;
    uint64_t physAddr;
    uint32_t bytes;
    uint32_t config[kConfigWords];
};

struct JobResult {
    uint32_t jobId;
    Status   status;                   // OK or HW_ERROR
    uint32_t hwCycles;
};

// The accelerator block. One implementation talks to registers; the sim runs a thread per core.
// submit() returns BUSY when the core cannot accept another job right now (the dispatcher retries later).
// Completions arrive on the callback, possibly from another thread.
class IAccelBlock {
public:
    virtual ~IAccelBlock() = default;
    virtual Status   submit(const JobDesc& job) = 0;
    virtual bool     isBusy(CoreType core) const = 0;
    virtual void     setCompletionHandler(std::function<void(const JobResult&)> handler) = 0;
    virtual unsigned coreCount() const { return kCoreCount; }
};

}  // namespace cvaccel::hw
