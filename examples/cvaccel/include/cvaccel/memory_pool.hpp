#pragma once
#include <cstdint>
#include <cstddef>
#include <vector>
#include "cvaccel/types.hpp"

namespace cvaccel {

struct MemBlock {
    MemHandle handle = 0;
    SessionId owner = 0;
    size_t    offset = 0;     // from pool base, kMemAlign aligned
    size_t    bytes = 0;      // requested size
    size_t    reserved = 0;   // rounded up to kMemAlign
    bool      inUse = false;
};

// First-fit allocator over one contiguous pool of poolBytes. Handles start at 1 and are never reused
// within a run (so a stale handle is detected). Free blocks are coalesced.
class MemoryPool {
public:
    explicit MemoryPool(size_t poolBytes = kPoolBytes, uint64_t physBase = 0, uint8_t* virtBase = nullptr);
    Status    allocate(SessionId owner, size_t bytes, MemHandle& outHandle);   // NO_MEMORY, INVALID_ARG (0 or > pool)
    Status    release(MemHandle h, SessionId owner);                          // NOT_OWNER if owner differs
    void      releaseAll(SessionId owner);
    const MemBlock* find(MemHandle h) const;
    uint64_t  physAddr(MemHandle h) const;                                     // 0 if unknown
    uint8_t*  map(MemHandle h);                                                // nullptr if unknown or no virt base
    size_t    bytesInUse() const;
    size_t    bytesInUse(SessionId owner) const;
    size_t    largestFree() const;
    size_t    capacity() const { return poolBytes_; }
private:
    size_t    poolBytes_;
    uint64_t  physBase_;
    uint8_t*  virtBase_;
    MemHandle nextHandle_ = 1;
    std::vector<MemBlock> blocks_;   // ordered by offset; gaps are free
};

}  // namespace cvaccel
