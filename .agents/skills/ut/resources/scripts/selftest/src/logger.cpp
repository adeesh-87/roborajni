#include "logger.hpp"
namespace fw {
uint32_t Clock::now() const { return 42u; }
int Logger::emit(const std::string& line)
{
    if (!bus_.ready()) { return -1; }
    return bus_.write(reinterpret_cast<const uint8_t*>(line.data()), static_cast<uint32_t>(line.size()));
}
int Logger::log(const std::string& msg)
{
    ++count_;
    return emit(std::to_string(clock_.now()) + " " + msg);
}
int Logger::flush() { return emit(std::string("\n")); }
}
