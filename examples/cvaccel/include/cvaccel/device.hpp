#pragma once
#include <cstdint>
#include <cstddef>
#include "cvaccel/types.hpp"

namespace cvaccel::os {

// The OS boundary of the service: how it reaches a client (wake-up ioctl), the clock, and physical memory.
class IDevice {
public:
    virtual ~IDevice() = default;
    // ioctl in the service->client direction: wakes the client that owns clientFd. Returns OK or INVALID_ARG.
    virtual Status  ioctlToClient(ClientFd clientFd, IoctlCmd cmd, const void* payload, size_t payloadBytes) = 0;
    virtual TimeNs  nowNs() const = 0;
    // physical memory backing the pool: the service calls this once at start-up.
    virtual uint64_t poolPhysBase() const = 0;
    virtual uint8_t* poolVirtBase() = 0;
};

}  // namespace cvaccel::os
