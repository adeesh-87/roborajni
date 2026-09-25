#include "cvaccel/memory_pool.hpp"

#include "CppUTest/TestHarness.h"

TEST_GROUP(MemoryPool) {};

// alignUp() has internal (anonymous-namespace) linkage in src/memory_pool.cpp, so it cannot be
// called directly from this translation unit. It is exercised through MemoryPool::allocate(),
// whose reserved size (visible via bytesInUse()) equals alignUp(bytes) for a single allocation.
TEST(MemoryPool, AlignUp_TypicalBytes_RoundsUpToMemAlign) {
    cvaccel::MemoryPool pool;
    cvaccel::MemHandle handle = 0;
    cvaccel::Status status = pool.allocate(1, 100, handle);
    CHECK(status == cvaccel::Status::OK);
    UNSIGNED_LONGS_EQUAL(128, pool.bytesInUse());   // (100 + 64 - 1) / 64 * 64 == 128
}

// L16: bytes == 0 -> true short-circuits the OR, returns INVALID_ARG before alignUp() runs.
TEST(MemoryPool, Allocate_ZeroBytes_ReturnsInvalidArg) {
    cvaccel::MemoryPool pool;
    cvaccel::MemHandle handle = 0;
    cvaccel::Status status = pool.allocate(1, 0, handle);
    CHECK(status == cvaccel::Status::INVALID_ARG);
}

// L16 false (bytes=50 <= poolBytes_=100): passes the size guard and completes with OK.
TEST(MemoryPool, Allocate_BytesNotExceedingPoolBytes_ReturnsOk) {
    cvaccel::MemoryPool pool(100, 0, nullptr);
    cvaccel::MemHandle handle = 0;
    cvaccel::Status status = pool.allocate(1, 50, handle);
    CHECK(status == cvaccel::Status::OK);
    UNSIGNED_LONGS_EQUAL(0, pool.physAddr(handle));   // reserved = alignUp(50) = 64, fits at offset 0
}

// L18: bytes=100 <= poolBytes_=100 (L16 false), but alignUp(100)=128 > poolBytes_=100 -> NO_MEMORY.
TEST(MemoryPool, Allocate_ReservedExceedsPoolBytes_ReturnsNoMemory) {
    cvaccel::MemoryPool pool(100, 0, nullptr);
    cvaccel::MemHandle handle = 0;
    cvaccel::Status status = pool.allocate(1, 100, handle);
    CHECK(status == cvaccel::Status::NO_MEMORY);
}

// L18 false: alignUp(100)=128 <= poolBytes_ (default 64MB), so allocation proceeds to OK.
TEST(MemoryPool, Allocate_ReservedWithinPoolBytes_ReturnsOk) {
    cvaccel::MemoryPool pool;
    cvaccel::MemHandle handle = 0;
    cvaccel::Status status = pool.allocate(1, 100, handle);
    CHECK(status == cvaccel::Status::OK);
}

// L22: blocks_ is empty, so begin() == end() and the loop body runs 0 times.
TEST(MemoryPool, Allocate_NoExistingBlocks_ReturnsOffsetZero) {
    cvaccel::MemoryPool pool;
    cvaccel::MemHandle handle = 0;
    cvaccel::Status status = pool.allocate(1, 1, handle);
    CHECK(status == cvaccel::Status::OK);
    UNSIGNED_LONGS_EQUAL(0, pool.physAddr(handle));
}

// L22: one existing block, gap before it is 0 (too small), so the loop body runs exactly once
// before ++it reaches end() and the new block is placed right after it.
TEST(MemoryPool, Allocate_SingleExistingBlock_PlacesAfterIt) {
    cvaccel::MemoryPool pool(1024, 0, nullptr);
    cvaccel::MemHandle a = 0;
    CHECK(pool.allocate(1, 64, a) == cvaccel::Status::OK);   // reserved 64, offset 0

    cvaccel::MemHandle b = 0;
    cvaccel::Status status = pool.allocate(1, 64, b);
    CHECK(status == cvaccel::Status::OK);
    UNSIGNED_LONGS_EQUAL(64, pool.physAddr(b));
}

// L22: three existing blocks, none has a fitting gap before it, so the loop body runs three
// times (many iterations) before ++it reaches end().
TEST(MemoryPool, Allocate_ThreeExistingBlocks_PlacesAfterAll) {
    cvaccel::MemoryPool pool(1024, 0, nullptr);
    cvaccel::MemHandle a = 0, b = 0, c = 0;
    CHECK(pool.allocate(1, 64, a) == cvaccel::Status::OK);   // offset 0
    CHECK(pool.allocate(1, 64, b) == cvaccel::Status::OK);   // offset 64
    CHECK(pool.allocate(1, 64, c) == cvaccel::Status::OK);   // offset 128

    cvaccel::MemHandle d = 0;
    cvaccel::Status status = pool.allocate(1, 64, d);
    CHECK(status == cvaccel::Status::OK);
    UNSIGNED_LONGS_EQUAL(192, pool.physAddr(d));
}

// L23 true: after freeing the middle block, the gap between the first and third blocks
// (64 bytes) is exactly big enough, so the loop breaks early and the freed slot is reused.
TEST(MemoryPool, Allocate_GapBetweenBlocksFits_ReusesGap) {
    cvaccel::MemoryPool pool(1024, 0, nullptr);
    cvaccel::MemHandle a = 0, b = 0, c = 0;
    CHECK(pool.allocate(1, 64, a) == cvaccel::Status::OK);   // offset 0
    CHECK(pool.allocate(1, 64, b) == cvaccel::Status::OK);   // offset 64
    CHECK(pool.allocate(1, 64, c) == cvaccel::Status::OK);   // offset 128
    CHECK(pool.release(b, 1) == cvaccel::Status::OK);

    cvaccel::MemHandle d = 0;
    cvaccel::Status status = pool.allocate(1, 64, d);
    CHECK(status == cvaccel::Status::OK);
    UNSIGNED_LONGS_EQUAL(64, pool.physAddr(d));   // reuses b's freed offset
}

// L23 false: after freeing the first block, the gap before the remaining block (64 bytes) is
// not big enough for a 128-byte request, so the loop continues past it instead of breaking.
TEST(MemoryPool, Allocate_GapBetweenBlocksTooSmall_SkipsGap) {
    cvaccel::MemoryPool pool(1024, 0, nullptr);
    cvaccel::MemHandle a = 0, b = 0;
    CHECK(pool.allocate(1, 64, a) == cvaccel::Status::OK);   // offset 0
    CHECK(pool.allocate(1, 64, b) == cvaccel::Status::OK);   // offset 64
    CHECK(pool.release(a, 1) == cvaccel::Status::OK);

    cvaccel::MemHandle c = 0;
    cvaccel::Status status = pool.allocate(1, 100, c);   // reserved 128, gap of 64 is too small
    CHECK(status == cvaccel::Status::OK);
    UNSIGNED_LONGS_EQUAL(128, pool.physAddr(c));
}

// L26 true: after checking two real blocks with no fitting gap, the loop reaches end() and the
// new block is placed after the last one.
TEST(MemoryPool, Allocate_NoFittingGapAmongBlocks_PlacesAfterLast) {
    cvaccel::MemoryPool pool(1024, 0, nullptr);
    cvaccel::MemHandle a = 0, b = 0;
    CHECK(pool.allocate(1, 64, a) == cvaccel::Status::OK);   // offset 0
    CHECK(pool.allocate(1, 64, b) == cvaccel::Status::OK);   // offset 64

    cvaccel::MemHandle c = 0;
    cvaccel::Status status = pool.allocate(1, 64, c);
    CHECK(status == cvaccel::Status::OK);
    UNSIGNED_LONGS_EQUAL(128, pool.physAddr(c));
}

// L26 false: after freeing the first block, the gap before the remaining block (64 bytes) fits
// a 64-byte request, so the loop breaks with it pointing at a real block, not end().
TEST(MemoryPool, Allocate_GapAtStartFits_PlacesBeforeFirstBlock) {
    cvaccel::MemoryPool pool(1024, 0, nullptr);
    cvaccel::MemHandle a = 0, b = 0, c = 0;
    CHECK(pool.allocate(1, 64, a) == cvaccel::Status::OK);   // offset 0
    CHECK(pool.allocate(1, 64, b) == cvaccel::Status::OK);   // offset 64
    CHECK(pool.allocate(1, 64, c) == cvaccel::Status::OK);   // offset 128
    CHECK(pool.release(a, 1) == cvaccel::Status::OK);

    cvaccel::MemHandle d = 0;
    cvaccel::Status status = pool.allocate(1, 64, d);
    CHECK(status == cvaccel::Status::OK);
    UNSIGNED_LONGS_EQUAL(0, pool.physAddr(d));   // gapEnd = b's offset (64), not poolBytes_
}

// L27 true: one 64-byte block leaves only 36 bytes before the pool end, not enough for another
// 64-byte reservation, so allocation fails with NO_MEMORY even though L16/L18 passed.
TEST(MemoryPool, Allocate_RemainingSpaceTooSmall_ReturnsNoMemory) {
    cvaccel::MemoryPool pool(100, 0, nullptr);
    cvaccel::MemHandle a = 0;
    CHECK(pool.allocate(1, 64, a) == cvaccel::Status::OK);   // offset 0, reserved 64

    cvaccel::MemHandle b = 0;
    cvaccel::Status status = pool.allocate(1, 64, b);   // 100 - 64 = 36 < 64
    CHECK(status == cvaccel::Status::NO_MEMORY);
}

// L27 false: the pool has ample remaining space (kPoolBytes - 0 >= 256), so allocation succeeds.
TEST(MemoryPool, Allocate_RemainingSpaceSufficient_ReturnsOk) {
    cvaccel::MemoryPool pool;
    cvaccel::MemHandle handle = 0;
    cvaccel::Status status = pool.allocate(1, 256, handle);
    CHECK(status == cvaccel::Status::OK);
    UNSIGNED_LONGS_EQUAL(256, pool.bytesInUse());
}

// L42: blocks_ is empty, so begin() == end() and the loop body runs 0 times, falling through to
// the INVALID_ARG return.
TEST(MemoryPool, Release_EmptyPool_ReturnsInvalidArg) {
    cvaccel::MemoryPool pool;
    cvaccel::Status status = pool.release(1, 1);
    CHECK(status == cvaccel::Status::INVALID_ARG);
}

// L42: a single block in the pool matches on the first (only) iteration, so the loop body runs
// exactly once.
TEST(MemoryPool, Release_SingleBlockPool_ReturnsOk) {
    cvaccel::MemoryPool pool;
    cvaccel::MemHandle a = 0;
    CHECK(pool.allocate(1, 64, a) == cvaccel::Status::OK);
    cvaccel::Status status = pool.release(a, 1);
    CHECK(status == cvaccel::Status::OK);
}

// L42: three blocks exist and the released handle belongs to the last one, so the loop checks
// the first two (no match) before matching the third -- many iterations.
TEST(MemoryPool, Release_MatchIsLastOfThreeBlocks_ReturnsOk) {
    cvaccel::MemoryPool pool(1024, 0, nullptr);
    cvaccel::MemHandle a = 0, b = 0, c = 0;
    CHECK(pool.allocate(1, 64, a) == cvaccel::Status::OK);
    CHECK(pool.allocate(1, 64, b) == cvaccel::Status::OK);
    CHECK(pool.allocate(1, 64, c) == cvaccel::Status::OK);
    cvaccel::Status status = pool.release(c, 1);
    CHECK(status == cvaccel::Status::OK);
}

// L43 true: it->handle == h matches, so the block is erased and find() can no longer locate it.
TEST(MemoryPool, Release_HandleMatches_RemovesBlock) {
    cvaccel::MemoryPool pool;
    cvaccel::MemHandle a = 0;
    CHECK(pool.allocate(1, 64, a) == cvaccel::Status::OK);
    CHECK(pool.release(a, 1) == cvaccel::Status::OK);
    POINTERS_EQUAL(nullptr, pool.find(a));
}

// L43 false: no block's handle matches h, so the loop runs to end() without erasing anything and
// falls through to INVALID_ARG.
TEST(MemoryPool, Release_HandleNotFound_ReturnsInvalidArg) {
    cvaccel::MemoryPool pool;
    cvaccel::MemHandle a = 0;
    CHECK(pool.allocate(1, 64, a) == cvaccel::Status::OK);
    cvaccel::Status status = pool.release(999, 1);
    CHECK(status == cvaccel::Status::INVALID_ARG);
}

// L44 true: it->owner != owner, so release refuses to erase the block and returns NOT_OWNER.
TEST(MemoryPool, Release_OwnerMismatch_ReturnsNotOwner) {
    cvaccel::MemoryPool pool;
    cvaccel::MemHandle a = 0;
    CHECK(pool.allocate(1, 64, a) == cvaccel::Status::OK);
    cvaccel::Status status = pool.release(a, 2);
    CHECK(status == cvaccel::Status::NOT_OWNER);
}

// L44 false: it->owner == owner, so the block is erased and release succeeds with OK.
TEST(MemoryPool, Release_OwnerMatches_ReturnsOk) {
    cvaccel::MemoryPool pool;
    cvaccel::MemHandle a = 0;
    CHECK(pool.allocate(1, 64, a) == cvaccel::Status::OK);
    cvaccel::Status status = pool.release(a, 1);
    CHECK(status == cvaccel::Status::OK);
}

// releaseAll straight-line: erases every block whose b.owner == owner, leaving blocks owned by
// other sessions untouched.
TEST(MemoryPool, ReleaseAll_TypicalInputs_RemovesOnlyMatchingOwnerBlocks) {
    cvaccel::MemoryPool pool(1024, 0, nullptr);
    cvaccel::MemHandle a = 0, b = 0, c = 0;
    CHECK(pool.allocate(1, 64, a) == cvaccel::Status::OK);
    CHECK(pool.allocate(2, 64, b) == cvaccel::Status::OK);
    CHECK(pool.allocate(1, 64, c) == cvaccel::Status::OK);

    pool.releaseAll(1);

    POINTERS_EQUAL(nullptr, pool.find(a));
    POINTERS_EQUAL(nullptr, pool.find(c));
    CHECK(pool.find(b) != nullptr);
}

// L59 true: b.handle == h matches, so find() returns a pointer to that block.
TEST(MemoryPool, Find_HandleMatches_ReturnsPointerToBlock) {
    cvaccel::MemoryPool pool;
    cvaccel::MemHandle a = 0;
    CHECK(pool.allocate(1, 64, a) == cvaccel::Status::OK);
    const cvaccel::MemBlock* block = pool.find(a);
    CHECK(block != nullptr);
    UNSIGNED_LONGS_EQUAL(a, block->handle);
}

// L59 false: no block's handle matches h, so the loop runs to completion and find() returns
// nullptr.
TEST(MemoryPool, Find_HandleNotFound_ReturnsNullptr) {
    cvaccel::MemoryPool pool;
    cvaccel::MemHandle a = 0;
    CHECK(pool.allocate(1, 64, a) == cvaccel::Status::OK);
    const cvaccel::MemBlock* block = pool.find(999);
    POINTERS_EQUAL(nullptr, block);
}

// L65: find(h) returns a non-null block, so physAddr returns physBase_ + b->offset.
TEST(MemoryPool, PhysAddr_HandleFound_ReturnsPhysBasePlusOffset) {
    cvaccel::MemoryPool pool(1024, 0x1000, nullptr);
    cvaccel::MemHandle a = 0, b = 0;
    CHECK(pool.allocate(1, 64, a) == cvaccel::Status::OK);   // offset 0
    CHECK(pool.allocate(1, 64, b) == cvaccel::Status::OK);   // offset 64
    UNSIGNED_LONGS_EQUAL(0x1000 + 64, pool.physAddr(b));
}

// L65: find(h) returns nullptr, so physAddr short-circuits to 0 instead of dereferencing b.
TEST(MemoryPool, PhysAddr_HandleNotFound_ReturnsZero) {
    cvaccel::MemoryPool pool(1024, 0x1000, nullptr);
    UNSIGNED_LONGS_EQUAL(0, pool.physAddr(999));
}

// L70 true: b is found (handle valid) but virtBase_ is null, so !virtBase_ alone flips the OR
// to true and map() returns nullptr without dereferencing virtBase_.
TEST(MemoryPool, Map_NoVirtBase_ReturnsNullptr) {
    cvaccel::MemoryPool pool(1024, 0, nullptr);
    cvaccel::MemHandle a = 0;
    CHECK(pool.allocate(1, 64, a) == cvaccel::Status::OK);
    POINTERS_EQUAL(nullptr, pool.map(a));
}

// L70 false: b is found (handle valid) and virtBase_ is non-null, so both sub-conditions are
// false and map() returns virtBase_ + b->offset.
TEST(MemoryPool, Map_HandleFoundWithVirtBase_ReturnsVirtBasePlusOffset) {
    uint8_t buffer[1024];
    cvaccel::MemoryPool pool(1024, 0, buffer);
    cvaccel::MemHandle a = 0;
    CHECK(pool.allocate(1, 64, a) == cvaccel::Status::OK);   // offset 0
    POINTERS_EQUAL(buffer, pool.map(a));
}

// Straight-line: total sums reserved (aligned) bytes across all blocks, not requested bytes.
TEST(MemoryPool, BytesInUse_TwoBlocks_ReturnsSumOfReservedBytes) {
    cvaccel::MemoryPool pool(1024, 0, nullptr);
    cvaccel::MemHandle a = 0, b = 0;
    CHECK(pool.allocate(1, 64, a) == cvaccel::Status::OK);    // reserved 64
    CHECK(pool.allocate(1, 100, b) == cvaccel::Status::OK);   // reserved 128
    UNSIGNED_LONGS_EQUAL(192, pool.bytesInUse());
}

// Straight-line: with one block (offset 0, reserved 64) in a 1024-byte pool, the gap before it
// is 0 and the tail gap after it is poolBytes_ - 64 = 960, which is the larger of the two.
TEST(MemoryPool, LargestFree_SingleBlock_ReturnsTailGap) {
    cvaccel::MemoryPool pool(1024, 0, nullptr);
    cvaccel::MemHandle a = 0;
    CHECK(pool.allocate(1, 64, a) == cvaccel::Status::OK);   // offset 0, reserved 64
    UNSIGNED_LONGS_EQUAL(960, pool.largestFree());
}
