#include "mini_test.h"
#include "logger.hpp"
class FakeBus : public fw::IBus {
public:
    int write(const uint8_t*, uint32_t len) override { return static_cast<int>(len); }
    bool ready() const override { return true; }
};
TEST(Logger, Log_Writes) { FakeBus bus; fw::Clock clk; fw::Logger lg(bus, clk); CHECK(lg.log("x") > 0); }
