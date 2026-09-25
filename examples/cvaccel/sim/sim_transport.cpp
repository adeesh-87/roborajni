#include "sim_transport.hpp"

namespace cvaccel::sim {

SimTransport::SimTransport(CvAccelService& service, SimDevice& device)
    : service_(service),
      device_(device),
      fd_(device.registerClient([this](IoctlCmd cmd, const void* payload, size_t bytes) {
          if (cmd == IoctlCmd::WAKE && bytes >= sizeof(CompletionInfo) && wake_) {
              wake_(*static_cast<const CompletionInfo*>(payload));
          }
      })) {}

SimTransport::~SimTransport() {
    device_.unregisterClient(fd_);
    service_.clientDisconnected(fd_);
}

Status SimTransport::ioctl(IoctlCmd cmd, void* payload, size_t bytes) {
    return service_.handle(fd_, cmd, payload, bytes);
}

void SimTransport::setWakeHandler(std::function<void(const CompletionInfo&)> h) {
    wake_ = std::move(h);
}

}  // namespace cvaccel::sim
