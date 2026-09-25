#pragma once
#include <array>
#include "cvaccel/types.hpp"

namespace cvaccel {

struct SessionInfo {
    SessionId id = 0;
    ClientFd  clientFd = -1;
    Priority  priority = Priority::NORMAL;
    uint32_t  openRequests = 0;    // queued or running
    uint64_t  bytesAllocated = 0;
    bool      active = false;
};

// Up to kMaxSessions sessions. Ids are 1..kMaxSessions, reused after close.
class SessionManager {
public:
    Status open(ClientFd clientFd, Priority prio, SessionId& outId);
    Status close(SessionId id);                       // NO_SESSION if not active
    SessionInfo* find(SessionId id);                  // nullptr if not active
    const SessionInfo* find(SessionId id) const;
    bool owns(SessionId id, ClientFd clientFd) const; // session active and belongs to that fd
    unsigned activeCount() const;
    // every active session of a client (used when a client disconnects)
    template <class F> void forEachOfClient(ClientFd fd, F&& f) { for (auto& s : sessions_) if (s.active && s.clientFd == fd) f(s); }
private:
    std::array<SessionInfo, kMaxSessions> sessions_{};
};

}  // namespace cvaccel
