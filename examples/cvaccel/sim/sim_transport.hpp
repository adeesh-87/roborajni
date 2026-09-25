#pragma once
#include "cvclient/cvclient.hpp"
#include "cvaccel/service.hpp"
#include "sim_device.hpp"

namespace cvaccel::sim {

// Client transport bound directly to a service instance (what open("/dev/cvaccel") + ioctl() is on the SoC).
class SimTransport : public cvclient::ITransport {
public:
    SimTransport(CvAccelService& service, SimDevice& device);
    ~SimTransport() override;
    ClientFd fd() const override { return fd_; }
    Status   ioctl(IoctlCmd cmd, void* payload, size_t bytes) override;
    void     setWakeHandler(std::function<void(const CompletionInfo&)> h) override;
private:
    CvAccelService& service_; SimDevice& device_; ClientFd fd_;
    std::function<void(const CompletionInfo&)> wake_;
};

}  // namespace cvaccel::sim
