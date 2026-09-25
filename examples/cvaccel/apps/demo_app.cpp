// Integration demo: 3 client threads exercise every CoreType through the simulated SoC stack.
#include <atomic>
#include <cstdio>
#include <thread>
#include <vector>

#include "cvaccel/service.hpp"
#include "cvclient/cvclient.hpp"
#include "sim_accel_block.hpp"
#include "sim_device.hpp"
#include "sim_transport.hpp"

using namespace cvaccel;

namespace {

constexpr unsigned kClients = 3;
constexpr unsigned kRequestsPerClient = 4;
constexpr uint32_t kAllocBytes = 16 * 1024;
constexpr uint32_t kReqBytes = 1024;

void clientWork(unsigned idx, CvAccelService& service, sim::SimDevice& device, std::atomic<bool>& allOk) {
    sim::SimTransport transport(service, device);
    cvclient::Client client(transport);

    Priority prio = static_cast<Priority>(idx % 3);
    Status s = client.openSession(prio);
    if (s != Status::OK) {
        std::printf("client %u failed to open session: %d\n", idx, static_cast<int>(s));
        allOk = false;
        return;
    }

    MemHandle mem = 0;
    s = client.allocMem(kAllocBytes, mem);
    if (s != Status::OK) {
        std::printf("client %u failed to alloc mem: %d\n", idx, static_cast<int>(s));
        allOk = false;
        client.closeSession();
        return;
    }

    std::vector<RequestId> requests;
    for (unsigned j = 0; j < kRequestsPerClient; ++j) {
        CoreType core = static_cast<CoreType>(j % kCoreCount);
        uint32_t config[kConfigWords] = {};
        config[0] = idx;
        config[1] = kReqBytes;
        RequestId req = 0;
        s = client.postConfig(mem, core, kReqBytes, config, req);
        if (s != Status::OK) {
            std::printf("client %u failed to post config: %d\n", idx, static_cast<int>(s));
            allOk = false;
            continue;
        }
        s = client.submit(req);
        if (s != Status::OK) {
            std::printf("client %u failed to submit request %u: %d\n", idx, req, static_cast<int>(s));
            allOk = false;
            continue;
        }
        requests.push_back(req);
    }

    for (RequestId req : requests) {
        cvclient::Completion c{};
        s = client.wait(req, c, 2000);
        if (s != Status::OK || c.status != Status::OK) allOk = false;
        std::printf("client %u request %u status %d latency %lluus\n", idx, req, static_cast<int>(c.status),
                    static_cast<unsigned long long>(c.latencyNs / 1000));
    }

    client.freeMem(mem);
    client.closeSession();
}

}  // namespace

int main() {
    sim::SimDevice device;
    sim::SimAccelBlock block;
    CvAccelService service(block, device);

    std::atomic<bool> allOk{true};
    std::vector<std::thread> threads;
    for (unsigned i = 0; i < kClients; ++i) {
        threads.emplace_back(clientWork, i, std::ref(service), std::ref(device), std::ref(allOk));
    }
    for (auto& t : threads) t.join();

    std::printf("%s", service.perf().report().c_str());

    bool ok = allOk.load() && service.perf().integrityErrors() == 0;
    return ok ? 0 : 1;
}
