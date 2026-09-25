#include <vector>  // request_queue.hpp uses std::vector without including it
#include "cvaccel/request_queue.hpp"
#include <algorithm>

namespace cvaccel {

namespace {
bool higherOrEqualPriority(Priority a, Priority b) {
    return static_cast<uint8_t>(a) >= static_cast<uint8_t>(b);
}
}  // namespace

Status RequestQueue::enqueue(const Request& r) {
    for (const auto& q : queues_) for (const auto& x : q) if (x.id == r.id) return Status::INVALID_ARG;   // duplicate id
    unsigned coreIdx = static_cast<unsigned>(r.core);
    if (coreIdx >= kCoreCount) return Status::INVALID_ARG;
    std::deque<Request>& q = queues_[coreIdx];
    if (q.size() >= kMaxQueuePerCore) return Status::QUEUE_FULL;

    // Insert before the first entry with strictly lower priority, keeping FIFO within a priority.
    auto it = q.begin();
    while (it != q.end() && higherOrEqualPriority(it->priority, r.priority)) ++it;
    q.insert(it, r);
    return Status::OK;
}

bool RequestQueue::dequeue(CoreType core, Request& out) {
    unsigned coreIdx = static_cast<unsigned>(core);
    if (coreIdx >= kCoreCount) return false;
    std::deque<Request>& q = queues_[coreIdx];
    if (q.empty()) return false;
    out = q.front();
    q.pop_front();
    return true;
}

bool RequestQueue::peek(CoreType core, Request& out) const {
    unsigned coreIdx = static_cast<unsigned>(core);
    if (coreIdx >= kCoreCount) return false;
    const std::deque<Request>& q = queues_[coreIdx];
    if (q.empty()) return false;
    out = q.front();
    return true;
}

unsigned RequestQueue::size(CoreType core) const {
    unsigned coreIdx = static_cast<unsigned>(core);
    if (coreIdx >= kCoreCount) return 0;
    return static_cast<unsigned>(queues_[coreIdx].size());
}

unsigned RequestQueue::sizeTotal() const {
    unsigned total = 0;
    for (const auto& q : queues_) total += static_cast<unsigned>(q.size());
    return total;
}

unsigned RequestQueue::cancelSession(SessionId session, std::vector<RequestId>& removed) {
    unsigned count = 0;
    for (auto& q : queues_) {
        for (auto it = q.begin(); it != q.end();) {
            if (it->session == session) {
                removed.push_back(it->id);
                it = q.erase(it);
                ++count;
            } else {
                ++it;
            }
        }
    }
    return count;
}

}  // namespace cvaccel
