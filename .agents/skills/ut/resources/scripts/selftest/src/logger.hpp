#pragma once
#include <cstdint>
#include <string>
namespace fw {
class IBus {
public:
    virtual ~IBus() = default;
    virtual int write(const uint8_t* data, uint32_t len) = 0;
    virtual bool ready() const = 0;
};
class Clock { public: uint32_t now() const; };
class Logger {
public:
    Logger(IBus& bus, const Clock& clock) : bus_(bus), clock_(clock) {}
    int log(const std::string& msg);
    int flush();
private:
    int emit(const std::string& line);
    IBus& bus_;
    const Clock& clock_;
    uint32_t count_ = 0;
};
}
