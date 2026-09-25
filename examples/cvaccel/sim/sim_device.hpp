#pragma once
#include <functional>
#include <map>
#include <mutex>
#include <vector>
#include "cvaccel/device.hpp"

namespace cvaccel::sim {

// In-process OS boundary: the pool is heap memory, the clock is steady_clock, and ioctlToClient() delivers the
// wake-up to the handler registered for that fd (the SimTransport of the client).
class SimDevice : public os::IDevice {
public:
    explicit SimDevice(size_t poolBytes = kPoolBytes);
    Status   ioctlToClient(ClientFd clientFd, IoctlCmd cmd, const void* payload, size_t payloadBytes) override;
    TimeNs   nowNs() const override;
    uint64_t poolPhysBase() const override { return 0x80000000ull; }
    uint8_t* poolVirtBase() override { return pool_.data(); }
    // client side registration (used by SimTransport)
    ClientFd registerClient(std::function<void(IoctlCmd, const void*, size_t)> wakeHandler);
    void     unregisterClient(ClientFd fd);
    uint64_t wakeCount() const { return wakes_; }
private:
    std::vector<uint8_t> pool_;
    std::mutex mtx_;
    std::map<ClientFd, std::function<void(IoctlCmd, const void*, size_t)>> clients_;
    ClientFd nextFd_ = 3;
    uint64_t wakes_ = 0;
};

}  // namespace cvaccel::sim
