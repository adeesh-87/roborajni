#include "cvaccel/memory_pool.hpp"
#include <algorithm>

namespace cvaccel {

namespace {
size_t alignUp(size_t bytes) {
    return (bytes + kMemAlign - 1) / kMemAlign * kMemAlign;
}
}  // namespace

MemoryPool::MemoryPool(size_t poolBytes, uint64_t physBase, uint8_t* virtBase)
    : poolBytes_(poolBytes), physBase_(physBase), virtBase_(virtBase) {}

Status MemoryPool::allocate(SessionId owner, size_t bytes, MemHandle& outHandle, size_t align) {
    if (align == 0 || (align & (align - 1)) != 0) return Status::INVALID_ARG;   // power of two only
    if (bytes == 0 || bytes > poolBytes_) return Status::INVALID_ARG;
    size_t reserved = alignUp(bytes);
    if (reserved > poolBytes_) return Status::NO_MEMORY;

    size_t cursor = 0;
    auto it = blocks_.begin();
    for (; it != blocks_.end(); ++it) {
        if (it->offset - cursor >= reserved) break;
        cursor = it->offset + it->reserved;
    }
    size_t gapEnd = (it == blocks_.end()) ? poolBytes_ : it->offset;
    if (gapEnd - cursor < reserved) return Status::NO_MEMORY;

    MemBlock blk;
    blk.handle = nextHandle_++;
    blk.owner = owner;
    blk.offset = cursor;
    blk.bytes = bytes;
    blk.reserved = reserved;
    blk.inUse = true;
    blocks_.insert(it, blk);
    outHandle = blk.handle;
    return Status::OK;
}

Status MemoryPool::release(MemHandle h, SessionId owner) {
    for (auto it = blocks_.begin(); it != blocks_.end(); ++it) {
        if (it->handle == h) {
            if (it->owner != owner) return Status::NOT_OWNER;
            blocks_.erase(it);
            return Status::OK;
        }
    }
    return Status::INVALID_ARG;
}

void MemoryPool::releaseAll(SessionId owner) {
    blocks_.erase(std::remove_if(blocks_.begin(), blocks_.end(),
                                  [owner](const MemBlock& b) { return b.owner == owner; }),
                  blocks_.end());
}

const MemBlock* MemoryPool::find(MemHandle h) const {
    for (const auto& b : blocks_) if (b.handle == h) return &b;
    return nullptr;
}

uint64_t MemoryPool::physAddr(MemHandle h) const {
    const MemBlock* b = find(h);
    return b ? physBase_ + b->offset : 0;
}

uint8_t* MemoryPool::map(MemHandle h) {
    const MemBlock* b = find(h);
    if (!b || !virtBase_) return nullptr;
    return virtBase_ + b->offset;
}

size_t MemoryPool::bytesInUse() const {
    size_t total = 0;
    for (const auto& b : blocks_) total += b.reserved;
    return total;
}

size_t MemoryPool::bytesInUse(SessionId owner) const {
    size_t total = 0;
    for (const auto& b : blocks_) if (b.owner == owner) total += b.reserved;
    return total;
}

size_t MemoryPool::largestFree() const {
    size_t largest = 0;
    size_t cursor = 0;
    for (const auto& b : blocks_) {
        largest = std::max(largest, b.offset - cursor);
        cursor = b.offset + b.reserved;
    }
    largest = std::max(largest, poolBytes_ - cursor);
    return largest;
}

}  // namespace cvaccel
