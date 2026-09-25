#pragma once
#include <cstdint>
#include <cstddef>

namespace cvaccel {

enum class CoreType : uint8_t { RESIZE = 0, CONVOLVE = 1, WARP = 2, HISTOGRAM = 3, MATCH = 4 };
constexpr unsigned kCoreCount = 5;

enum class Status : int8_t {
    OK = 0, INVALID_ARG = -1, NO_SESSION = -2, NO_MEMORY = -3, NOT_OWNER = -4,
    QUEUE_FULL = -5, HW_ERROR = -6, CANCELLED = -7, BUSY = -8, INTEGRITY = -9
};

using SessionId = uint16_t;   // 0 = invalid
using MemHandle = uint32_t;   // 0 = invalid
using RequestId = uint32_t;   // 0 = invalid
using ClientFd  = int;        // the client's device file descriptor (identity for the wake-up ioctl)
using TimeNs    = uint64_t;

constexpr unsigned kMaxSessions   = 16;
constexpr unsigned kMaxQueuePerCore = 32;
constexpr size_t   kPoolBytes     = 64u * 1024u * 1024u;
constexpr size_t   kMemAlign      = 64;
constexpr unsigned kConfigWords   = 8;
constexpr uint32_t kMaxJobBytes   = 8u * 1024u * 1024u;

enum class Priority : uint8_t { LOW = 0, NORMAL = 1, HIGH = 2, URGENT = 3 };

// ioctl command numbers (client -> service and service -> client)
enum class IoctlCmd : uint32_t {
    OPEN_SESSION = 0x100, CLOSE_SESSION, ALLOC_MEM, FREE_MEM, POST_CONFIG, SUBMIT, GET_STATS,
    WAKE = 0x200            // service -> client: a request completed
};

struct CompletionInfo {
    RequestId request;
    SessionId session;
    Status    status;
    TimeNs    latencyNs;     // finished - queued
    uint32_t  hwCycles;      // reported by the block
};

}  // namespace cvaccel
