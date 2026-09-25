# Cards for src/memory_pool.cpp (10 functions)

## alignUp  (src/memory_pool.cpp:7-9)
Signature: size_t alignUp(size_t bytes)
Params: bytes (size_t bytes)
Decisions: none (straight-line code)
Returns: (bytes + kMemAlign - 1) / kMemAlign * kMemAlign
Callers: MemoryPool::allocate() (src/memory_pool.cpp)
Existing tests calling it directly: none

## MemoryPool::MemoryPool  (src/memory_pool.cpp:12-13)
Signature: MemoryPool::MemoryPool(size_t poolBytes, uint64_t physBase, uint8_t* virtBase) : poolBytes_(poolBytes), physBase_(physBase), virtBase_(vi...
Params: poolBytes (size_t poolBytes); physBase (uint64_t physBase); virtBase (uint8_t* virtBase)
Decisions: none (straight-line code)
Existing tests calling it directly: none

## MemoryPool::allocate  (src/memory_pool.cpp:15-40)
Signature: Status MemoryPool::allocate(SessionId owner, size_t bytes, MemHandle& outHandle, size_t align)
Params: owner (SessionId owner); bytes (size_t bytes); outHandle (MemHandle& outHandle); align (size_t align)
Decisions (drive each outcome; loops: 0, 1, many):
  L16    if       (align == 0 || (align & (align - 1)) != 0) [2 sub-conditions: each must flip the outcome alone]
  L17    if       (bytes == 0 || bytes > poolBytes_) [2 sub-conditions: each must flip the outcome alone]
  L19    if       (reserved > poolBytes_)
  L23    for      (; it != blocks_.end(); ++it)
  L24    if       (it->offset - cursor >= reserved)
  L27    ?:       (it == blocks_.end())
  L28    if       (gapEnd - cursor < reserved)
Returns: Status::INVALID_ARG | Status::NO_MEMORY | Status::OK
Calls: alignUp() (src/memory_pool.cpp:L7)
Callers: CvAccelService::allocMem() (src/service.cpp)
Existing tests calling it directly: TEST(CvAccelService, FreeMem_L84BytesGreaterThanBytesAllocated_ClampsToZero) (tests/service_test.cpp:L863); TEST(CvAccelService, MemoryPoolAllocate_AlignPowerOfTwo_ProceedsPastAlignCheck) (tests/service_test.cpp:L1673); TEST(CvAccelService, MemoryPoolAllocate_AlignZero_ReturnsInvalidArg) (tests/service_test.cpp:L1664); TEST(CvAccelService, MemoryPoolAllocate_BytesWithinPoolBytes_ProceedsPastByteCheck) (tests/service_test.cpp:L1691); TEST(CvAccelService, MemoryPoolAllocate_GapAtStartFits_PlacesBeforeFirstBlock) (tests/service_test.cpp:L1801); TEST(CvAccelService, MemoryPoolAllocate_GapBetweenBlocksFits_ReusesGap) (tests/service_test.cpp:L1756); TEST(CvAccelService, MemoryPoolAllocate_GapBetweenBlocksTooSmall_SkipsGap) (tests/service_test.cpp:L1772); TEST(CvAccelService, MemoryPoolAllocate_NoExistingBlocks_PlacesAtOffsetZero) (tests/service_test.cpp:L1718)

## MemoryPool::release  (src/memory_pool.cpp:42-51)
Signature: Status MemoryPool::release(MemHandle h, SessionId owner)
Params: h (MemHandle h); owner (SessionId owner)
Decisions (drive each outcome; loops: 0, 1, many):
  L43    for      (auto it = blocks_.begin(); it != blocks_.end(); ++it)
  L44    if       (it->handle == h)
  L45    if       (it->owner != owner)
Returns: Status::NOT_OWNER | Status::OK | Status::INVALID_ARG
Callers: CvAccelService::freeMem() (src/service.cpp)
Existing tests calling it directly: TEST(CvAccelService, MemoryPoolAllocate_GapAtStartFits_PlacesBeforeFirstBlock) (tests/service_test.cpp:L1801); TEST(CvAccelService, MemoryPoolAllocate_GapBetweenBlocksFits_ReusesGap) (tests/service_test.cpp:L1756); TEST(CvAccelService, MemoryPoolAllocate_GapBetweenBlocksTooSmall_SkipsGap) (tests/service_test.cpp:L1772); TEST(MemoryPool, Allocate_GapAtStartFits_PlacesBeforeFirstBlock) (tests/memory_pool_test.cpp:L135); TEST(MemoryPool, Allocate_GapBetweenBlocksFits_ReusesGap) (tests/memory_pool_test.cpp:L90); TEST(MemoryPool, Allocate_GapBetweenBlocksTooSmall_SkipsGap) (tests/memory_pool_test.cpp:L106); TEST(MemoryPool, Release_EmptyPool_ReturnsInvalidArg) (tests/memory_pool_test.cpp:L172); TEST(MemoryPool, Release_HandleMatches_RemovesBlock) (tests/memory_pool_test.cpp:L201)

## MemoryPool::releaseAll  (src/memory_pool.cpp:53-57)
Signature: void MemoryPool::releaseAll(SessionId owner)
Params: owner (SessionId owner)
Decisions: none (straight-line code)
Returns: b.owner == owner
Callers: CvAccelService::closeSession() (src/service.cpp)
Existing tests calling it directly: TEST(MemoryPool, ReleaseAll_TypicalInputs_RemovesOnlyMatchingOwnerBlocks) (tests/memory_pool_test.cpp:L239)

## MemoryPool::find  (src/memory_pool.cpp:59-62)
Signature: const MemBlock* MemoryPool::find(MemHandle h) const
Params: h (MemHandle h)
Decisions (drive each outcome; loops: 0, 1, many):
  L60    if       (b.handle == h)
Returns: &b | nullptr
Callers: MemoryPool::map() (src/memory_pool.cpp); MemoryPool::physAddr() (src/memory_pool.cpp); blockBytesOf() (src/dispatcher.cpp)
Existing tests calling it directly: TEST(MemoryPool, Find_HandleMatches_ReturnsPointerToBlock) (tests/memory_pool_test.cpp:L254); TEST(MemoryPool, Find_HandleNotFound_ReturnsNullptr) (tests/memory_pool_test.cpp:L265); TEST(MemoryPool, ReleaseAll_TypicalInputs_RemovesOnlyMatchingOwnerBlocks) (tests/memory_pool_test.cpp:L239); TEST(MemoryPool, Release_HandleMatches_RemovesBlock) (tests/memory_pool_test.cpp:L201)

## MemoryPool::physAddr  (src/memory_pool.cpp:64-67)
Signature: uint64_t MemoryPool::physAddr(MemHandle h) const
Params: h (MemHandle h)
Decisions (drive each outcome; loops: 0, 1, many):
  L66    ?:       b
Returns: b ? physBase_ + b->offset : 0
Calls: MemoryPool::find() (src/memory_pool.cpp:L59)
Callers: Dispatcher::start() (src/dispatcher.cpp)
Existing tests calling it directly: TEST(CvAccelService, MemoryPoolAllocate_GapAtStartFits_PlacesBeforeFirstBlock) (tests/service_test.cpp:L1801); TEST(CvAccelService, MemoryPoolAllocate_GapBetweenBlocksFits_ReusesGap) (tests/service_test.cpp:L1756); TEST(CvAccelService, MemoryPoolAllocate_GapBetweenBlocksTooSmall_SkipsGap) (tests/service_test.cpp:L1772); TEST(CvAccelService, MemoryPoolAllocate_NoExistingBlocks_PlacesAtOffsetZero) (tests/service_test.cpp:L1718); TEST(CvAccelService, MemoryPoolAllocate_NoFittingGapAmongBlocks_PlacesAfterLast) (tests/service_test.cpp:L1787); TEST(CvAccelService, MemoryPoolAllocate_SingleExistingBlock_PlacesAfterIt) (tests/service_test.cpp:L1728); TEST(CvAccelService, MemoryPoolAllocate_ThreeExistingBlocks_PlacesAfterAll) (tests/service_test.cpp:L1741); TEST(MemoryPool, Allocate_BytesNotExceedingPoolBytes_ReturnsOk) (tests/memory_pool_test.cpp:L27)

## MemoryPool::map  (src/memory_pool.cpp:69-73)
Signature: uint8_t* MemoryPool::map(MemHandle h)
Params: h (MemHandle h)
Decisions (drive each outcome; loops: 0, 1, many):
  L71    if       (!b || !virtBase_) [2 sub-conditions: each must flip the outcome alone]
Returns: nullptr | virtBase_ + b->offset
Calls: MemoryPool::find() (src/memory_pool.cpp:L59)
Existing tests calling it directly: TEST(MemoryPool, Map_HandleFoundWithVirtBase_ReturnsVirtBasePlusOffset) (tests/memory_pool_test.cpp:L299); TEST(MemoryPool, Map_NoVirtBase_ReturnsNullptr) (tests/memory_pool_test.cpp:L290)

## MemoryPool::bytesInUse  (src/memory_pool.cpp:75-79)
Signature: size_t MemoryPool::bytesInUse() const
Decisions: none (straight-line code)
Returns: total
Existing tests calling it directly: TEST(MemoryPool, AlignUp_TypicalBytes_RoundsUpToMemAlign) (tests/memory_pool_test.cpp:L10); TEST(MemoryPool, Allocate_RemainingSpaceSufficient_ReturnsOk) (tests/memory_pool_test.cpp:L162); TEST(MemoryPool, BytesInUse_TwoBlocks_ReturnsSumOfReservedBytes) (tests/memory_pool_test.cpp:L308)

## MemoryPool::largestFree  (src/memory_pool.cpp:87-96)
Signature: size_t MemoryPool::largestFree() const
Decisions: none (straight-line code)
Returns: largest
Existing tests calling it directly: TEST(MemoryPool, LargestFree_SingleBlock_ReturnsTailGap) (tests/memory_pool_test.cpp:L318)
# dependencies of src/memory_pool.cpp  (mock/stub candidates first; 'in-scope code' = another scanned file, often an existing mock)
