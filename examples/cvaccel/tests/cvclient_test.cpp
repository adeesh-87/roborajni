#include "cvclient/cvclient.hpp"

#include "CppUTest/TestHarness.h"

namespace {

class FakeTransport : public cvclient::ITransport {
public:
    cvaccel::ClientFd fd() const override { return 1; }
    cvaccel::Status ioctl(cvaccel::IoctlCmd, void*, size_t) override { return cvaccel::Status::OK; }
    void setWakeHandler(std::function<void(const cvaccel::CompletionInfo&)> h) override { wakeHandler = h; }
    std::function<void(const cvaccel::CompletionInfo&)> wakeHandler;
};

}  // namespace

TEST_GROUP(CvClient) {};

TEST(CvClient, Constructor_TypicalTransport_SessionIsZero) {
    FakeTransport transport;
    cvclient::Client client(transport);
    LONGS_EQUAL(0, client.session());
}
