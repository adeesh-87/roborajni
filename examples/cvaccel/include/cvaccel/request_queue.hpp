#pragma once
#include <array>
#include <deque>
#include <vector>
#include "cvaccel/types.hpp"

namespace cvaccel {

struct Request {
    RequestId id = 0;
    SessionId session = 0;
    ClientFd  clientFd = -1;
    MemHandle mem = 0;
    CoreType  core = CoreType::RESIZE;
    Priority  priority = Priority::NORMAL;
    uint32_t  config[kConfigWords] = {};
    uint32_t  bytes = 0;
    TimeNs    tQueued = 0;
    TimeNs    tStarted = 0;
};

// One FIFO per core; dequeue returns the highest priority first, FIFO inside a priority.
class RequestQueue {
public:
    Status   enqueue(const Request& r);                 // QUEUE_FULL at kMaxQueuePerCore, INVALID_ARG for a bad core
    bool     dequeue(CoreType core, Request& out);      // false when empty
    bool     peek(CoreType core, Request& out) const;
    unsigned size(CoreType core) const;
    unsigned sizeTotal() const;
    // removes every queued request of the session; returns how many were removed (their ids appended to removed)
    unsigned cancelSession(SessionId session, std::vector<RequestId>& removed);
private:
    std::array<std::deque<Request>, kCoreCount> queues_{};
};

}  // namespace cvaccel
