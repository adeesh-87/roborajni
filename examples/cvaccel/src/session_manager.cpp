#include "cvaccel/session_manager.hpp"

namespace cvaccel {

Status SessionManager::open(ClientFd clientFd, Priority prio, SessionId& outId) {
    for (unsigned i = 0; i < kMaxSessions; ++i) {
        SessionInfo& s = sessions_[i];
        if (!s.active) {
            s.id = static_cast<SessionId>(i + 1);
            s.clientFd = clientFd;
            s.priority = prio;
            s.openRequests = 0;
            s.bytesAllocated = 0;
            s.active = true;
            outId = s.id;
            return Status::OK;
        }
    }
    return Status::NO_MEMORY;
}

Status SessionManager::close(SessionId id) {
    SessionInfo* s = find(id);
    if (!s) return Status::NO_SESSION;
    *s = SessionInfo{};
    return Status::OK;
}

SessionInfo* SessionManager::find(SessionId id) {
    if (id == 0 || id > kMaxSessions) return nullptr;
    SessionInfo& s = sessions_[id - 1];
    if (!s.active || s.id != id) return nullptr;
    return &s;
}

const SessionInfo* SessionManager::find(SessionId id) const {
    if (id == 0 || id > kMaxSessions) return nullptr;
    const SessionInfo& s = sessions_[id - 1];
    if (!s.active || s.id != id) return nullptr;
    return &s;
}

bool SessionManager::owns(SessionId id, ClientFd clientFd) const {
    const SessionInfo* s = find(id);
    return s != nullptr && s->clientFd == clientFd;
}


}  // namespace cvaccel
