#include "sim_device.hpp"
#include <chrono>

namespace cvaccel::sim {

SimDevice::SimDevice(size_t poolBytes) : pool_(poolBytes) {}

Status SimDevice::ioctlToClient(ClientFd clientFd, IoctlCmd cmd, const void* payload, size_t payloadBytes) {
    std::function<void(IoctlCmd, const void*, size_t)> handler;
    {
        std::lock_guard<std::mutex> lock(mtx_);
        auto it = clients_.find(clientFd);
        if (it == clients_.end()) return Status::INVALID_ARG;
        handler = it->second;
    }
    // Called with the handler copied and mtx_ released, so the client's handler may call back
    // into this device (or the service) without deadlocking.
    if (handler) handler(cmd, payload, payloadBytes);
    ++wakes_;   // calls into one SimDevice are serialized by the service's own mutex in practice
    return Status::OK;
}

TimeNs SimDevice::nowNs() const {
    using namespace std::chrono;
    return static_cast<TimeNs>(duration_cast<nanoseconds>(steady_clock::now().time_since_epoch()).count());
}

ClientFd SimDevice::registerClient(std::function<void(IoctlCmd, const void*, size_t)> wakeHandler) {
    std::lock_guard<std::mutex> lock(mtx_);
    ClientFd fd = nextFd_++;
    clients_[fd] = std::move(wakeHandler);
    return fd;
}

void SimDevice::unregisterClient(ClientFd fd) {
    std::lock_guard<std::mutex> lock(mtx_);
    clients_.erase(fd);
}

}  // namespace cvaccel::sim
