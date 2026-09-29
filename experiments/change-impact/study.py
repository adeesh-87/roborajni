#!/usr/bin/env python3
"""study.py: change-impact study on the cvaccel toy codebase.

Each scenario makes ONE kind of change to a scratch copy of examples/cvaccel, the way a developer would (production
call sites updated so that production code still compiles, tests untouched). Then:
  build     ninja -k 0 unit_tests unit_tests_wrap   -> compile errors per file, link errors, new warnings
  run       both test binaries                      -> failing TESTs (or crash)
  reach     gcov on the changed production lines    -> did any test even execute the change?
  predict   clangd, BEFORE the change, on the symbol that changes: references and implementations in tests/
            -> which test files a prep script would have flagged; compared with the files that actually broke

  study.py setup            scratch copy + shared --wrap stubs binary + git baseline + clangd index
  study.py run [ID...]      run scenarios (all by default) -> results.json
  study.py report           STUDY.md from results.json
The C scenarios (X*) use a small C module (hal.c / sensor.c) with the same --wrap + CppUMock stub pattern.
"""
import json, os, re, shutil, subprocess, sys, tempfile, gzip, glob

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.realpath(os.path.join(HERE, '..', '..'))
SRC = os.path.join(REPO_ROOT, 'examples', 'cvaccel')
W = os.environ.get('CIS_DIR', '/tmp/claude-0/cis')
R = os.path.join(W, 'repo')
B = os.path.join(R, 'build')
C = os.path.join(W, 'chal')
sys.path.insert(0, os.path.join(REPO_ROOT, 'experiments', 'lsp-vs-graphify'))

PERF_REC = '_ZN7cvaccel11PerfMonitor6recordERKNS_10PerfRecordE'
PHYS = '_ZNK7cvaccel10MemoryPool8physAddrEj'


def sh(cmd, cwd=None, timeout=900):
    r = subprocess.run(cmd, shell=isinstance(cmd, str), cwd=cwd, capture_output=True, text=True, timeout=timeout)
    return r.returncode, r.stdout + r.stderr


# ------------------------------------------------------------------------------------------------ scenarios
# edit: (file, old, new) exact text, must exist; ('*', old, new) = replace in every src/include file; count = all
def E(f, old, new, all_=False):
    return {'f': f, 'old': old, 'new': new, 'all': all_}


SCENARIOS = [
    # ---------------------------------------------------------------- behaviour (function body)
    dict(id='B1', cat='Function body', title='Refactor with identical behaviour',
         change='RequestQueue::sizeTotal sums size(c) per core instead of iterating the deques',
         sym=('src/request_queue.cpp', 'unsigned RequestQueue::sizeTotal', 'sizeTotal'),
         edits=[E('src/request_queue.cpp', 'for (const auto& q : queues_) total += static_cast<unsigned>(q.size());',
                  'for (unsigned c = 0; c < kCoreCount; ++c) total += size(static_cast<CoreType>(c));')]),
    dict(id='B2', cat='Function body', title='Off-by-one in a tested boundary',
         change='RequestQueue::enqueue: `q.size() >= kMaxQueuePerCore` becomes `>` (queue accepts one too many)',
         sym=('src/request_queue.cpp', 'Status RequestQueue::enqueue', 'enqueue'),
         edits=[E('src/request_queue.cpp', 'if (q.size() >= kMaxQueuePerCore)', 'if (q.size() > kMaxQueuePerCore)')]),
    dict(id='B3', cat='Function body', title='Off-by-one in a boundary nobody tests exactly',
         change='MemoryPool::allocate: `gapEnd - cursor < reserved` becomes `<=` (an exactly fitting gap is refused)',
         sym=('src/memory_pool.cpp', 'Status MemoryPool::allocate', 'allocate'),
         edits=[E('src/memory_pool.cpp', 'if (gapEnd - cursor < reserved) return Status::NO_MEMORY;',
                  'if (gapEnd - cursor <= reserved) return Status::NO_MEMORY;')]),
    dict(id='B4', cat='Function body', title='Different error code returned',
         change='MemoryPool::release returns NOT_OWNER instead of INVALID_ARG for an unknown handle',
         sym=('src/memory_pool.cpp', 'Status MemoryPool::release', 'release'),
         edits=[E('src/memory_pool.cpp', '    return Status::INVALID_ARG;\n}\n\nvoid MemoryPool::releaseAll',
                  '    return Status::NOT_OWNER;\n}\n\nvoid MemoryPool::releaseAll')]),
    dict(id='B5', cat='Function body', title='New branch (new validation)',
         change='RequestQueue::enqueue rejects requests with bytes > kMaxJobBytes (new early return)',
         sym=('src/request_queue.cpp', 'Status RequestQueue::enqueue', 'enqueue'),
         edits=[E('src/request_queue.cpp', '    if (coreIdx >= kCoreCount) return Status::INVALID_ARG;\n',
                  '    if (coreIdx >= kCoreCount) return Status::INVALID_ARG;\n    if (r.bytes > kMaxJobBytes) return Status::INVALID_ARG;\n')]),
    dict(id='B6', cat='Function body', title='Side effect removed',
         change='Dispatcher::onCompletion no longer decrements the session\'s openRequests',
         sym=('src/dispatcher.cpp', 'Status Dispatcher::onCompletion', 'onCompletion'),
         edits=[E('src/dispatcher.cpp', '    perf_.record(rec);\n\n    SessionInfo* si = sessions_.find(r.session);\n    if (si && si->openRequests > 0) --si->openRequests;\n\n    // r.clientFd',
                  '    perf_.record(rec);\n\n    // r.clientFd')]),
    dict(id='B7', cat='Function body', title='Extra call to a collaborator',
         change='Dispatcher::start calls pool_.physAddr() twice (a redundant "is it mapped" check)',
         sym=('src/dispatcher.cpp', 'Status Dispatcher::start', 'start'),
         edits=[E('src/dispatcher.cpp', 'job.physAddr = pool_.physAddr(r.mem);',
                  'job.physAddr = pool_.physAddr(r.mem) ? pool_.physAddr(r.mem) : 0;')]),
    dict(id='B8', cat='Function body', title='Call order changed',
         change='Dispatcher::onCompletion records the perf record after the wake-up ioctl instead of before',
         sym=('src/dispatcher.cpp', 'Status Dispatcher::onCompletion', 'onCompletion'),
         edits=[E('src/dispatcher.cpp', '    perf_.record(rec);\n\n    SessionInfo* si = sessions_.find(r.session);',
                  '    SessionInfo* si = sessions_.find(r.session);'),
                E('src/dispatcher.cpp', '    running_.erase(it);\n    return Status::OK;', '    perf_.record(rec);\n    running_.erase(it);\n    return Status::OK;')]),
    dict(id='B9', cat='Function body', title='Wrong argument passed to a collaborator',
         change='Dispatcher passes sizeof(info) - 1 as the payload size of every wake-up ioctl',
         sym=('include/cvaccel/device.hpp', 'ioctlToClient', 'ioctlToClient'),
         edits=[E('src/dispatcher.cpp', 'IoctlCmd::WAKE, &info, sizeof(info));', 'IoctlCmd::WAKE, &info, sizeof(info) - 1);', True)]),
    # ---------------------------------------------------------------- function signature
    dict(id='G1', cat='Signature', title='Parameter added, with a default value',
         change='RequestQueue::size(CoreType, bool includeRunning = false)',
         sym=('include/cvaccel/request_queue.hpp', 'unsigned size(CoreType core) const;', 'size'),
         edits=[E('include/cvaccel/request_queue.hpp', 'unsigned size(CoreType core) const;', 'unsigned size(CoreType core, bool includeRunning = false) const;'),
                E('src/request_queue.cpp', 'unsigned RequestQueue::size(CoreType core) const {', 'unsigned RequestQueue::size(CoreType core, bool includeRunning) const {\n    (void)includeRunning;')]),
    dict(id='G2', cat='Signature', title='Parameter added, no default (production callers updated)',
         change='MemoryPool::release(MemHandle, SessionId, bool force); service.cpp passes false',
         sym=('include/cvaccel/memory_pool.hpp', 'Status    release(', 'release'),
         edits=[E('include/cvaccel/memory_pool.hpp', 'Status    release(MemHandle h, SessionId owner);', 'Status    release(MemHandle h, SessionId owner, bool force);'),
                E('src/memory_pool.cpp', 'Status MemoryPool::release(MemHandle h, SessionId owner) {', 'Status MemoryPool::release(MemHandle h, SessionId owner, bool force) {\n    (void)force;'),
                E('src/service.cpp', 'pool_.release(a.handle, a.session)', 'pool_.release(a.handle, a.session, false)')]),
    dict(id='G3', cat='Signature', title='Type alias widened',
         change='using SessionId = uint16_t becomes uint32_t',
         sym=('include/cvaccel/types.hpp', 'using SessionId', 'SessionId'),
         edits=[E('include/cvaccel/types.hpp', 'using SessionId = uint16_t;', 'using SessionId = uint32_t;')]),
    dict(id='G4', cat='Signature', title='Return type bool becomes an enum class',
         change='RequestQueue::dequeue returns Status instead of bool; the dispatcher checks != Status::OK',
         sym=('include/cvaccel/request_queue.hpp', 'bool     dequeue(', 'dequeue'),
         edits=[E('include/cvaccel/request_queue.hpp', 'bool     dequeue(CoreType core, Request& out);', 'Status   dequeue(CoreType core, Request& out);'),
                E('src/request_queue.cpp', 'bool RequestQueue::dequeue(CoreType core, Request& out) {\n    unsigned coreIdx = static_cast<unsigned>(core);\n    if (coreIdx >= kCoreCount) return false;\n    std::deque<Request>& q = queues_[coreIdx];\n    if (q.empty()) return false;\n    out = q.front();\n    q.pop_front();\n    return true;',
                  'Status RequestQueue::dequeue(CoreType core, Request& out) {\n    unsigned coreIdx = static_cast<unsigned>(core);\n    if (coreIdx >= kCoreCount) return Status::INVALID_ARG;\n    std::deque<Request>& q = queues_[coreIdx];\n    if (q.empty()) return Status::BUSY;\n    out = q.front();\n    q.pop_front();\n    return Status::OK;'),
                E('src/dispatcher.cpp', 'if (!queue_.dequeue(core, r)) break;', 'if (queue_.dequeue(core, r) != Status::OK) break;')]),
    dict(id='G5', cat='Signature', title='Function renamed (production callers updated)',
         change='RequestQueue::sizeTotal becomes totalSize',
         sym=('include/cvaccel/request_queue.hpp', 'sizeTotal', 'sizeTotal'),
         edits=[E('*', 'sizeTotal', 'totalSize', True)]),
    dict(id='G6', cat='Signature', title='Function removed (only tests used it)',
         change='MemoryPool::largestFree deleted',
         sym=('include/cvaccel/memory_pool.hpp', 'largestFree', 'largestFree'),
         edits=[E('include/cvaccel/memory_pool.hpp', '    size_t    largestFree() const;\n', ''),
                E('src/memory_pool.cpp', 'size_t MemoryPool::largestFree() const {', 'static size_t largestFree_removed(const std::vector<MemBlock>& blocks_, size_t poolBytes_) {')]),
    dict(id='G7', cat='Signature', title='Test-only public helpers made private',
         change='PerfMonitor::timestampsOk/bytesOk/coreBytesOk ("exposed for testing") moved to private:',
         sym=('include/cvaccel/perf_monitor.hpp', 'static bool timestampsOk', 'timestampsOk'),
         edits=[E('include/cvaccel/perf_monitor.hpp', '    // integrity rules, exposed for testing\n    static bool timestampsOk(const PerfRecord& r);    // queued <= started <= finished, finished > 0\n    static bool bytesOk(const PerfRecord& r);         // 0 < bytes <= allocated\n    static bool coreBytesOk(const PerfRecord& r);     // bytes <= kMaxJobBytes for that core\nprivate:\n',
                  'private:\n    static bool timestampsOk(const PerfRecord& r);\n    static bool bytesOk(const PerfRecord& r);\n    static bool coreBytesOk(const PerfRecord& r);\n')]),
    dict(id='G8', cat='Signature', title='Overload added that makes calls ambiguous',
         change='MemoryPool gains bytesInUse(uint32_t tag) next to bytesInUse(SessionId)',
         sym=('include/cvaccel/memory_pool.hpp', 'size_t    bytesInUse(SessionId owner) const;', 'bytesInUse'),
         edits=[E('include/cvaccel/memory_pool.hpp', '    size_t    bytesInUse(SessionId owner) const;\n', '    size_t    bytesInUse(SessionId owner) const;\n    size_t    bytesInUse(uint32_t tag) const;\n'),
                E('src/memory_pool.cpp', 'const MemBlock* MemoryPool::find(', 'size_t MemoryPool::bytesInUse(uint32_t) const { return 0; }\n\nconst MemBlock* MemoryPool::find(')]),
    dict(id='G9', cat='Signature', title='Overload added that tests silently switch to',
         change='MemoryPool gains release(MemHandle, int legacyOwner) (a shim without the owner check); tests pass int literals',
         sym=('include/cvaccel/memory_pool.hpp', 'Status    release(', 'release'),
         edits=[E('include/cvaccel/memory_pool.hpp', '    Status    release(MemHandle h, SessionId owner);                          // NOT_OWNER if owner differs\n',
                  '    Status    release(MemHandle h, SessionId owner);                          // NOT_OWNER if owner differs\n    Status    release(MemHandle h, int legacyOwner);\n'),
                E('src/memory_pool.cpp', 'void MemoryPool::releaseAll(', 'Status MemoryPool::release(MemHandle h, int) { for (auto it = blocks_.begin(); it != blocks_.end(); ++it) if (it->handle == h) { blocks_.erase(it); return Status::OK; } return Status::INVALID_ARG; }\n\nvoid MemoryPool::releaseAll(')]),
    # ---------------------------------------------------------------- interfaces (virtual)
    dict(id='V1', cat='Interface', title='Pure virtual method added',
         change='IAccelBlock gains `virtual void reset() = 0;`',
         sym=('include/cvaccel/hw_block.hpp', 'class IAccelBlock', 'IAccelBlock'), impl=True,
         edits=[E('include/cvaccel/hw_block.hpp', '    virtual unsigned coreCount() const { return kCoreCount; }', '    virtual void     reset() = 0;\n    virtual unsigned coreCount() const { return kCoreCount; }')]),
    dict(id='V2', cat='Interface', title='Virtual method with a default body added',
         change='IAccelBlock gains `virtual void reset() {}`',
         sym=('include/cvaccel/hw_block.hpp', 'class IAccelBlock', 'IAccelBlock'), impl=True,
         edits=[E('include/cvaccel/hw_block.hpp', '    virtual unsigned coreCount() const { return kCoreCount; }', '    virtual void     reset() {}\n    virtual unsigned coreCount() const { return kCoreCount; }')]),
    dict(id='V3', cat='Interface', title='const dropped from a pure virtual',
         change='IDevice::nowNs() const becomes nowNs()',
         sym=('include/cvaccel/device.hpp', 'nowNs', 'nowNs'), impl=True,
         edits=[E('include/cvaccel/device.hpp', 'virtual TimeNs  nowNs() const = 0;', 'virtual TimeNs  nowNs() = 0;')]),
    dict(id='V4', cat='Interface', title='Parameter with default added to a pure virtual',
         change='IAccelBlock::isBusy(CoreType, bool strict = false)',
         sym=('include/cvaccel/hw_block.hpp', 'isBusy', 'isBusy'), impl=True,
         edits=[E('include/cvaccel/hw_block.hpp', 'virtual bool     isBusy(CoreType core) const = 0;', 'virtual bool     isBusy(CoreType core, bool strict = false) const = 0;')]),
    dict(id='V5', cat='Interface', title='Return type of a pure virtual changed',
         change='IDevice::nowNs returns int64_t instead of TimeNs (uint64_t)',
         sym=('include/cvaccel/device.hpp', 'nowNs', 'nowNs'), impl=True,
         edits=[E('include/cvaccel/device.hpp', 'virtual TimeNs  nowNs() const = 0;', 'virtual int64_t nowNs() const = 0;')]),
    # ---------------------------------------------------------------- types, enums, constants
    dict(id='T1', cat='Type', title='Field added at the end of a struct (with initializer)',
         change='Request gains `uint32_t flags = 0;`',
         sym=('include/cvaccel/request_queue.hpp', 'struct Request', 'Request'),
         edits=[E('include/cvaccel/request_queue.hpp', '    TimeNs    tStarted = 0;\n};', '    TimeNs    tStarted = 0;\n    uint32_t  flags = 0;\n};')]),
    dict(id='T2', cat='Type', title='Field inserted in the middle of a struct built with {...}',
         change='hw::JobResult gains `CoreType core;` between jobId and status',
         sym=('include/cvaccel/hw_block.hpp', 'struct JobResult', 'JobResult'),
         edits=[E('include/cvaccel/hw_block.hpp', '    uint32_t jobId;\n    Status   status;', '    uint32_t jobId;\n    CoreType core;\n    Status   status;')]),
    dict(id='T3', cat='Type', title='Fields of the same type reordered',
         change='hw::JobResult becomes { hwCycles, status, jobId } (both ends are uint32_t)',
         sym=('include/cvaccel/hw_block.hpp', 'struct JobResult', 'JobResult'),
         edits=[E('include/cvaccel/hw_block.hpp', 'struct JobResult {\n    uint32_t jobId;\n    Status   status;                   // OK or HW_ERROR\n    uint32_t hwCycles;\n};',
                  'struct JobResult {\n    uint32_t hwCycles;\n    Status   status;                   // OK or HW_ERROR\n    uint32_t jobId;\n};')]),
    dict(id='T4', cat='Type', title='Field renamed (production updated)',
         change='SessionInfo::openRequests becomes pendingRequests',
         sym=('include/cvaccel/session_manager.hpp', 'openRequests', 'openRequests'),
         edits=[E('*', 'openRequests', 'pendingRequests', True)]),
    dict(id='T5', cat='Type', title='Field narrowed',
         change='CompletionInfo::latencyNs TimeNs (64 bit) becomes uint32_t',
         sym=('include/cvaccel/types.hpp', 'latencyNs', 'latencyNs'),
         edits=[E('include/cvaccel/types.hpp', 'TimeNs    latencyNs;', 'uint32_t  latencyNs;')]),
    dict(id='T6', cat='Enum', title='Enumerator inserted in the middle (values shift), count updated',
         change='CoreType gains CROP = 1 (CONVOLVE..MATCH shift by one), kCoreCount 5 -> 6',
         sym=('include/cvaccel/types.hpp', 'enum class CoreType', 'CoreType'),
         edits=[E('include/cvaccel/types.hpp', '{ RESIZE = 0, CONVOLVE = 1, WARP = 2, HISTOGRAM = 3, MATCH = 4 };\nconstexpr unsigned kCoreCount = 5;',
                  '{ RESIZE = 0, CROP = 1, CONVOLVE = 2, WARP = 3, HISTOGRAM = 4, MATCH = 5 };\nconstexpr unsigned kCoreCount = 6;')]),
    dict(id='T7', cat='Enum', title='Enumerator added at the end',
         change='Priority gains CRITICAL = 4',
         sym=('include/cvaccel/types.hpp', 'enum class Priority', 'Priority'),
         edits=[E('include/cvaccel/types.hpp', 'URGENT = 3 };', 'URGENT = 3, CRITICAL = 4 };')]),
    dict(id='T8', cat='Constant', title='Constant changed; tests use the constant',
         change='kMaxQueuePerCore 32 -> 16',
         sym=('include/cvaccel/types.hpp', 'kMaxQueuePerCore', 'kMaxQueuePerCore'),
         edits=[E('include/cvaccel/types.hpp', 'constexpr unsigned kMaxQueuePerCore = 32;', 'constexpr unsigned kMaxQueuePerCore = 16;')]),
    dict(id='T9', cat='Constant', title='Constant changed; tests hard-code its value',
         change='kMemAlign 64 -> 128',
         sym=('include/cvaccel/types.hpp', 'kMemAlign', 'kMemAlign'),
         edits=[E('include/cvaccel/types.hpp', 'constexpr size_t   kMemAlign      = 64;', 'constexpr size_t   kMemAlign      = 128;')]),
    # ---------------------------------------------------------------- construction, headers, build
    dict(id='K1', cat='Construction', title='Constructor parameter added (production updated)',
         change='Dispatcher(..., unsigned maxInFlight); CvAccelService passes 64',
         sym=('include/cvaccel/dispatcher.hpp', '    Dispatcher(', 'Dispatcher'),
         edits=[E('include/cvaccel/dispatcher.hpp', 'SessionManager& sm, PerfMonitor& perf);', 'SessionManager& sm, PerfMonitor& perf, unsigned maxInFlight);'),
                E('src/dispatcher.cpp', '                        SessionManager& sm, PerfMonitor& perf)\n    : hw_(hw)', '                        SessionManager& sm, PerfMonitor& perf, unsigned maxInFlight)\n    : hw_(hw)'),
                E('src/dispatcher.cpp', 'sessions_(sm), perf_(perf) {}', 'sessions_(sm), perf_(perf) { (void)maxInFlight; }'),
                E('src/service.cpp', 'dispatcher_(hw_, dev_, queue_, pool_, sessions_, perf_)', 'dispatcher_(hw_, dev_, queue_, pool_, sessions_, perf_, 64)')]),
    dict(id='K2', cat='Construction', title='Default constructor argument changed',
         change='MemoryPool(size_t poolBytes = kPoolBytes ...) default becomes 4096 (production passes it explicitly)',
         sym=('include/cvaccel/memory_pool.hpp', 'explicit MemoryPool(', 'MemoryPool'),
         edits=[E('include/cvaccel/memory_pool.hpp', 'explicit MemoryPool(size_t poolBytes = kPoolBytes,', 'explicit MemoryPool(size_t poolBytes = 4096,')]),
    dict(id='H1', cat='Header', title='Header stops including what tests relied on',
         change='dispatcher.hpp forward-declares SessionManager and PerfMonitor instead of including their headers',
         sym=('include/cvaccel/dispatcher.hpp', 'class Dispatcher', 'Dispatcher'),
         edits=[E('include/cvaccel/dispatcher.hpp', '#include "cvaccel/session_manager.hpp"\n#include "cvaccel/perf_monitor.hpp"\n', ''),
                E('include/cvaccel/dispatcher.hpp', 'namespace cvaccel {\n', 'namespace cvaccel {\nclass SessionManager;\nclass PerfMonitor;\n'),
                E('src/dispatcher.cpp', '#include "cvaccel/dispatcher.hpp"\n', '#include "cvaccel/dispatcher.hpp"\n#include "cvaccel/session_manager.hpp"\n#include "cvaccel/perf_monitor.hpp"\n')]),
    dict(id='H2', cat='Header', title='Namespace renamed (production updated)',
         change='cvaccel::hw becomes cvaccel::hwif',
         sym=('include/cvaccel/hw_block.hpp', 'namespace cvaccel::hw', 'hw'),
         edits=[E('include/cvaccel/hw_block.hpp', 'namespace cvaccel::hw {', 'namespace cvaccel::hwif {'), E('*', 'hw::', 'hwif::', True)]),
    dict(id='H3', cat='Build', title='Function moved to a new source file',
         change='PerfMonitor::report moved from perf_monitor.cpp to new src/perf_report.cpp (the app build globs src/*.cpp; the test build lists files)',
         sym=('src/perf_monitor.cpp', 'std::string PerfMonitor::report', 'report'),
         edits=[E('src/perf_monitor.cpp', 'std::string PerfMonitor::report() const {', 'std::string PerfMonitor::report_moved() const {'),
                E('include/cvaccel/perf_monitor.hpp', '    void     reset();', '    void     reset();\n    std::string report_moved() const;')],
         new_files={'src/perf_report.cpp': '#include "cvaccel/perf_monitor.hpp"\nnamespace cvaccel {\nstd::string PerfMonitor::report() const { return report_moved(); }\n}\n'}),
    # ---------------------------------------------------------------- the shared --wrap + CppUMock stubs
    dict(id='W1', cat='Wrap stubs', title='Strict wrap stubs linked into the existing test binary',
         change='tests/CMakeLists.txt: unit_tests also links cvaccel_wrap_stubs.cpp with `--wrap` for record() and physAddr()',
         sym=('src/perf_monitor.cpp', 'Status PerfMonitor::record', 'record'),
         edits=[E('tests/CMakeLists.txt', 'add_executable(unit_tests ${UT_SOURCES} ${UT_CODE_UNDER_TEST})',
                  'add_executable(unit_tests ${UT_SOURCES} ${UT_CODE_UNDER_TEST} ${CMAKE_CURRENT_SOURCE_DIR}/stubs/cvaccel_wrap_stubs.cpp)\n'
                  'target_link_options(unit_tests PRIVATE "LINKER:--wrap=' + PERF_REC + '" "LINKER:--wrap=' + PHYS + '")')]),
    dict(id='W2', cat='Wrap stubs', title='Wrapped C++ function gets a defaulted parameter (mangled name changes)',
         change='MemoryPool::physAddr(MemHandle, bool strict = false) const',
         sym=('include/cvaccel/memory_pool.hpp', 'physAddr', 'physAddr'),
         edits=[E('include/cvaccel/memory_pool.hpp', 'uint64_t  physAddr(MemHandle h) const;', 'uint64_t  physAddr(MemHandle h, bool strict = false) const;'),
                E('src/memory_pool.cpp', 'uint64_t MemoryPool::physAddr(MemHandle h) const {', 'uint64_t MemoryPool::physAddr(MemHandle h, bool strict) const {\n    (void)strict;')]),
    dict(id='W3', cat='Wrap stubs', title='Wrapped function moved inline into its header',
         change='MemoryPool::physAddr defined in memory_pool.hpp (inline) instead of memory_pool.cpp',
         sym=('include/cvaccel/memory_pool.hpp', 'physAddr', 'physAddr'),
         edits=[E('include/cvaccel/memory_pool.hpp', 'uint64_t  physAddr(MemHandle h) const;', 'uint64_t  physAddr(MemHandle h) const { const MemBlock* b = find(h); return b ? physBase_ + b->offset : 0; }'),
                E('src/memory_pool.cpp', 'uint64_t MemoryPool::physAddr(MemHandle h) const {\n    const MemBlock* b = find(h);\n    return b ? physBase_ + b->offset : 0;\n}\n', '')]),
    dict(id='W4', cat='Wrap stubs', title='Function added to the --wrap list, stub not written',
         change='UT_WRAPPED gains MemoryPool::find (mangled); no `__wrap_` function exists',
         sym=('include/cvaccel/memory_pool.hpp', 'const MemBlock* find', 'find'),
         edits=[E('tests/CMakeLists.txt', 'set(UT_WRAPPED ' + PERF_REC, 'set(UT_WRAPPED _ZNK7cvaccel10MemoryPool4findEj ' + PERF_REC)]),
    dict(id='W5', cat='Wrap stubs', title='Stub exists, --wrap flag dropped',
         change='UT_WRAPPED loses physAddr (the stub still defines `__wrap_...physAddr`)',
         sym=('include/cvaccel/memory_pool.hpp', 'physAddr', 'physAddr'),
         edits=[E('tests/CMakeLists.txt', ' ' + PHYS + ')', ')')]),
    dict(id='W6', cat='Wrap stubs', title='Production stops calling the wrapped function',
         change='Dispatcher::start computes the physical address from pool_.find() instead of pool_.physAddr()',
         sym=('src/dispatcher.cpp', 'Status Dispatcher::start', 'start'),
         edits=[E('src/dispatcher.cpp', 'job.physAddr = pool_.physAddr(r.mem);',
                  'job.physAddr = pool_.find(r.mem) ? pool_.find(r.mem)->offset : 0;')]),
    # ---------------------------------------------------------------- C module with the same stub pattern
    dict(id='X1', cat='Wrap stubs (C)', title='C function gets a new parameter; stub declares its own `__real_` prototype',
         change='`hal_read(int reg)` becomes `hal_read(int reg, int bank)`; sensor.c updated; the stub is not', c=True,
         sym=('hal.h', 'hal_read', 'hal_read'), c_edits='param', c_guard=False),
    dict(id='X2', cat='Wrap stubs (C)', title='Same change; stub declares `__real_`/`__wrap_` with `__typeof__(hal_read)`',
         change='as X1, but the stub file uses `extern "C" __typeof__(hal_read) __real_hal_read, __wrap_hal_read;`', c=True,
         sym=('hal.h', 'hal_read', 'hal_read'), c_edits='param', c_guard=True),
    dict(id='X3', cat='Wrap stubs (C)', title='C function return type changed; stub not updated (no guard)',
         change='int hal_read(int) becomes double hal_read(int) (sensor.c updated, the stub is not)', c=True,
         sym=('hal.h', 'hal_read', 'hal_read'), c_edits='ret', c_guard=False),
]


# ------------------------------------------------------------------------------------------------ setup
def setup():
    if os.path.exists(R):
        shutil.rmtree(R)
    shutil.copytree(SRC, R, ignore=shutil.ignore_patterns('build*', '.cache'))
    shutil.copytree(os.path.join(HERE, 'files', 'tests'), os.path.join(R, 'tests'), dirs_exist_ok=True)
    with open(os.path.join(R, 'tests', 'CMakeLists.txt'), 'a') as f:
        f.write(open(os.path.join(HERE, 'files', 'wrap_binary.cmake')).read())
    sh('git init -q && git add -A && git -c user.email=s@s -c user.name=s commit -qm base', R)
    os.makedirs(B, exist_ok=True)
    rc, out = sh(['cmake', '-G', 'Ninja', '-DBUILD_UNIT_TESTS=ON', '-DCMAKE_BUILD_TYPE=Debug', '-DCMAKE_CXX_FLAGS=--coverage -O0', '..'], B)
    rc, out = sh(['ninja', 'unit_tests', 'unit_tests_wrap'], B)
    print('base build', rc)
    base = {}
    for b in ('unit_tests', 'unit_tests_wrap'):
        rc, o = sh([os.path.join(B, 'tests', b)], B)
        base[b] = re.findall(r'^(OK|Errors) \(.*\)$', o, re.M)
        print(b, rc, o.strip().splitlines()[-1])
    # C module
    if os.path.exists(C):
        shutil.rmtree(C)
    shutil.copytree(os.path.join(HERE, 'files', 'chal'), C)
    sh('git init -q && git add -A && git -c user.email=s@s -c user.name=s commit -qm base', C)
    print('C base:', c_build_run(C)['summary'])
    # clangd index over the base (tests included in the compile DB)
    predict_all()


def c_build_run(d):
    rc, out = sh('gcc -c -O0 hal.c sensor.c && g++ -o t tests/main.cpp tests/sensor_test.cpp stubs/hal_wrap_stubs.cpp hal.o sensor.o '
                 '-I. -lCppUTestExt -lCppUTest -Wl,--wrap=hal_read', d)
    res = {'build_log': out, 'built': rc == 0}
    if rc == 0:
        rc2, o2 = sh('./t -v', d)
        res['run'] = o2
        res['summary'] = (re.findall(r'^(?:OK|Errors) \(.*\)$', o2, re.M) or [o2.strip()[-200:]])[-1]
        res['failed'] = re.findall(r'Failure in (TEST\([^)]*\))', o2)
    else:
        res['summary'] = 'BUILD FAILED'
    return res


# ------------------------------------------------------------------------------------------------ one scenario
def apply(s):
    root = C if s.get('c') else R
    sh('git checkout -q -- . && git clean -qfd -e build', root)
    if s.get('c'):
        return c_apply(s)
    for e in s['edits']:
        files = [e['f']] if e['f'] != '*' else [os.path.relpath(p, R) for p in
                                                  glob.glob(os.path.join(R, 'src', '*.cpp')) + glob.glob(os.path.join(R, 'include', 'cvaccel', '*.hpp'))
                                                  + glob.glob(os.path.join(R, 'client', 'src', '*.cpp')) + glob.glob(os.path.join(R, 'client', 'include', '*', '*.hpp'))]
        hit = False
        for f in files:
            p = os.path.join(R, f)
            t = open(p).read()
            if e['old'] in t:
                hit = True
                t = t.replace(e['old'], e['new']) if (e['all'] or e['f'] == '*') else t.replace(e['old'], e['new'], 1)
                open(p, 'w').write(t)
        if not hit:
            raise SystemExit(f"{s['id']}: edit text not found: {e['old'][:60]!r}")
    for f, text in s.get('new_files', {}).items():
        open(os.path.join(R, f), 'w').write(text)


def c_apply(s):
    h = open(os.path.join(C, 'hal.h')).read()
    c = open(os.path.join(C, 'hal.c')).read()
    se = open(os.path.join(C, 'sensor.c')).read()
    st = open(os.path.join(C, 'stubs', 'hal_wrap_stubs.cpp')).read()
    if s['c_edits'] == 'param':
        h = h.replace('int hal_read(int reg);', 'int hal_read(int reg, int bank);')
        c = c.replace('int hal_read(int reg) { return reg * 10; }', 'int hal_read(int reg, int bank) { return reg * 10 + bank * 1000; }')
        se = se.replace('hal_read(reg)', 'hal_read(reg, 0)')
    else:
        h = h.replace('int hal_read(int reg);', 'double hal_read(int reg);')
        c = c.replace('int hal_read(int reg) { return reg * 10; }', 'double hal_read(int reg) { return reg * 10.0; }')
        se = se.replace('int sensor_get(int reg) { return hal_read(reg) / 2; }', 'int sensor_get(int reg) { return (int)(hal_read(reg) / 2); }')
    if s['c_guard']:
        st = st.replace('extern "C" int __real_hal_read(int reg);', 'extern "C" __typeof__(hal_read) __real_hal_read, __wrap_hal_read;')
    for n, t in (('hal.h', h), ('hal.c', c), ('sensor.c', se), ('stubs/hal_wrap_stubs.cpp', st)):
        open(os.path.join(C, n), 'w').write(t)


ERR = re.compile(r'^(\.\./)*([^\s:]+\.(?:cpp|hpp|c|h)):(\d+):(\d+): (?:fatal )?error: (.*)$')


def parse_build(log):
    errs, files, link = [], {}, []
    for l in log.splitlines():
        m = ERR.match(l.strip())
        if m:
            f = os.path.normpath(m.group(2)).replace(R + '/', '')
            f = re.sub(r'^.*?/(tests|src|include|client)/', r'\1/', f) if not f.startswith(('tests', 'src', 'include', 'client')) else f
            files[f] = files.get(f, 0) + 1
            errs.append(f'{f}:{m.group(3)}: {m.group(5)}')
        elif 'undefined reference' in l or 'multiple definition' in l or 'ld returned' in l:
            link.append(re.sub(r'^.*?: ', '', l.strip())[:220])
    return errs, files, link


def warnings(log):
    return sorted({re.sub(r'^(\.\./)*', '', l.strip()) for l in log.splitlines() if ': warning:' in l})


def run_tests():
    out = {}
    for b in ('unit_tests', 'unit_tests_wrap'):
        p = os.path.join(B, 'tests', b)
        if not os.path.exists(p):
            out[b] = {'ran': False}
            continue
        try:
            rc, o = sh([p], B, timeout=120)
        except subprocess.TimeoutExpired:
            out[b] = {'ran': True, 'summary': 'TIMEOUT', 'failed': []}
            continue
        fails = re.findall(r'Failure in (TEST\([^)]*\))', o)
        summ = re.findall(r'^(?:OK|Errors) \(.*\)$', o, re.M)
        detail = re.findall(r'Failure in TEST\([^)]*\)\n\s*(.*)', o)
        out[b] = {'ran': True, 'rc': rc, 'summary': summ[-1] if summ else f'CRASHED (exit {rc}): ' + o.strip()[-160:].replace('\n', ' | '),
                  'failed': fails, 'detail': [d.strip()[:160] for d in detail[:5]], 'tail': o[-1500:]}
    return out


def changed_lines():
    rc, d = sh('git diff -U0 --no-color -- src client/src', R)
    res, cur = {}, None
    for l in d.splitlines():
        if l.startswith('+++ b/'):
            cur = l[6:]
        m = re.match(r'^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@', l)
        if m and cur:
            a, n = int(m.group(1)), int(m.group(2) or 1)
            res.setdefault(cur, set()).update(range(a, a + n) if n else [a])
    return res


def reach(chg):
    """changed production lines: executable ones and those some test executed (gcov, both binaries)"""
    ex = run = br = brt = 0
    detail = []
    tmp = tempfile.mkdtemp()
    brs = {}
    for f, lines in chg.items():
        hits = {}
        for gcda in glob.glob(os.path.join(B, 'tests', 'CMakeFiles', '*', '__', f + '.gcda')):
            sh(['gcov', '--json-format', '--branch-probabilities', '-o', os.path.dirname(gcda), gcda], tmp)
            for g in glob.glob(os.path.join(tmp, '*.gcov.json.gz')):
                for jf in json.load(gzip.open(g))['files']:
                    if jf['file'].endswith(f):
                        for ln in jf['lines']:
                            if ln['line_number'] in lines:
                                hits[ln['line_number']] = hits.get(ln['line_number'], 0) + ln['count']
                                for k, b in enumerate(ln.get('branches', [])):
                                    if not b.get('throw'):
                                        bk = (f, ln['line_number'], k)
                                        brs[bk] = brs.get(bk, 0) + b['count']
                os.remove(g)
        e, r_ = len(hits), sum(1 for v in hits.values() if v > 0)
        ex += e
        run += r_
        if e:
            detail.append(f'{f}: {r_}/{e}')
    shutil.rmtree(tmp, ignore_errors=True)
    return {'executable': ex, 'executed': run, 'branches': len(brs), 'branches_taken': sum(1 for v in brs.values() if v > 0), 'detail': detail}


def run_one(s):
    apply(s)
    if s.get('c'):
        r = c_build_run(C)
        errs, files, link = parse_build(r['build_log'])
        return {'id': s['id'], 'build_ok': r['built'], 'errors': errs[:12], 'error_files': files, 'link': link[:6],
                'tests': {'unit_tests': {'ran': r['built'], 'summary': r['summary'], 'failed': r.get('failed', []),
                                         'tail': r.get('run', '')[-1200:]}},
                'reach': None, 'warnings_new': [w for w in warnings(r['build_log'])][:6], 'diff': sh('git diff --no-color', C)[1]}
    for b in ('unit_tests', 'unit_tests_wrap'):
        p = os.path.join(B, 'tests', b)
        if os.path.exists(p):
            os.remove(p)
    for g in glob.glob(os.path.join(B, '**', '*.gcda'), recursive=True):
        os.remove(g)
    if any(e['f'] == 'tests/CMakeLists.txt' for e in s['edits']):
        sh(['cmake', '..'], B)
    rc, log = sh(['ninja', '-k', '0', 'unit_tests', 'unit_tests_wrap'], B)
    errs, files, link = parse_build(log)
    base_w = set(json.load(open(os.path.join(W, 'base_warnings.json')))) if os.path.exists(os.path.join(W, 'base_warnings.json')) else set()
    tests = run_tests()
    chg = changed_lines()
    return {'id': s['id'], 'build_ok': rc == 0, 'errors': errs[:12], 'error_count': len(errs), 'error_files': files, 'link': link[:6],
            'warnings_new': [w for w in warnings(log) if w not in base_w][:6], 'tests': tests, 'reach': reach(chg),
            'diff': sh('git diff --no-color', R)[1]}


# ------------------------------------------------------------------------------------------------ clangd prediction
def predict_all():
    from clangd_cli import Client, uri, path_of
    c = Client(R, B)
    ents = json.load(open(os.path.join(B, 'compile_commands.json')))
    c.open(os.path.join(ents[0]['directory'], ents[0]['file']))
    c.wait_index(600)
    import time
    for _ in range(200):
        if c.request('workspace/symbol', {'query': 'a'}):
            break
        time.sleep(0.1)
    containers = {}

    def enclosing(f, line):
        """innermost function or TEST block around a 1-based line of file f: (kind, name, start line)"""
        if f not in containers:
            fp = os.path.join(R, f)
            c.open(fp)
            out, stack = [], list(c.request('textDocument/documentSymbol', {'textDocument': {'uri': uri(fp)}}) or [])
            src = open(fp, errors='replace').read().splitlines()
            while stack:
                x = stack.pop()
                if x.get('kind') in (6, 9, 12) or x['name'] in ('TEST', 'TEST_F', 'IGNORE_TEST'):
                    a, b = x['range']['start']['line'], x['range']['end']['line']
                    nm = x['name']
                    if nm in ('TEST', 'TEST_F', 'IGNORE_TEST'):
                        m = re.search(r'\b(?:IGNORE_)?TEST(?:_F)?\s*\(\s*(\w+)\s*,\s*(\w+)', src[a])
                        nm = f'TEST({m.group(1)}, {m.group(2)})' if m else nm
                    out.append((a + 1, b + 1, nm, x['selectionRange']['start'], x['name'].startswith(('TEST', 'IGNORE'))))
                stack += x.get('children', [])
            containers[f] = out
        enc = [x for x in containers[f] if x[0] <= line <= x[1]]
        return min(enc, key=lambda x: x[1] - x[0]) if enc else None

    def refs_at(fp, pos):
        return c.request('textDocument/references', {'textDocument': {'uri': uri(fp)}, 'position': pos, 'context': {'includeDeclaration': False}}) or []

    def tests_reaching(fp, pos, hops=2):
        """TEST blocks referencing the symbol directly, and through production callers up to `hops` levels"""
        direct, trans, seen = set(), set(), set()
        frontier = [(fp, pos)]
        for h in range(hops + 1):
            nxt = []
            for f0, p0 in frontier:
                for r in refs_at(f0, p0):
                    rf = os.path.relpath(path_of(r['uri']), R)
                    if rf.startswith('..'):
                        continue
                    e = enclosing(rf, r['range']['start']['line'] + 1)
                    if not e:
                        continue
                    if e[4]:
                        (direct if h == 0 else trans).add(e[2])
                    elif not rf.startswith('tests/') and (rf, e[0]) not in seen:
                        seen.add((rf, e[0]))
                        nxt.append((os.path.join(R, rf), e[3]))
            frontier = nxt
        return direct, trans - direct

    pred = {}
    for s in SCENARIOS:
        if s.get('c'):
            continue
        f, pat, name = s['sym']
        p = os.path.join(R, f)
        lines = open(p).read().splitlines()
        ln = next(i for i, l in enumerate(lines) if pat in l)
        col = lines[ln].find(name, lines[ln].find(pat) if pat in lines[ln] else 0)
        c.open(p)
        pos = {'line': ln, 'character': max(col, 0)}
        refs = c.request('textDocument/references', {'textDocument': {'uri': uri(p)}, 'position': pos, 'context': {'includeDeclaration': False}}) or []
        found = {}
        for r in refs:
            rf = os.path.relpath(path_of(r['uri']), R)
            found.setdefault(rf, 0)
            found[rf] += 1
        impls = []
        if s.get('impl'):
            # the interface's methods: implementations (fakes) of each pure virtual
            for i, l in enumerate(lines):
                m = re.search(r'virtual\s+[\w:<>]+\s+(\w+)\(', l)
                if m and ln <= i < ln + 15:
                    im = c.request('textDocument/implementation', {'textDocument': {'uri': uri(p)},
                                                                    'position': {'line': i, 'character': l.find(m.group(1))}}) or []
                    impls += [f"{os.path.relpath(path_of(x['uri']), R)}:{x['range']['start']['line'] + 1}" for x in im]
        d_t, t_t = tests_reaching(p, pos)
        pred_tests = {'direct': sorted(d_t), 'transitive': sorted(t_t)}
        pred[s['id']] = {'tests': pred_tests, 'test_refs': {k: v for k, v in found.items() if k.startswith('tests/')},
                         'prod_refs': {k: v for k, v in found.items() if not k.startswith('tests/')},
                         'impls': sorted(set(impls))}
    c.close()
    json.dump(pred, open(os.path.join(W, 'predict.json'), 'w'), indent=1)
    print('predictions for', len(pred), 'scenarios')


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'run'
    if cmd == 'setup':
        setup()
        # base warnings (so only new ones are reported)
        sh('git checkout -q -- .', R)
        for g in glob.glob(os.path.join(B, '**', '*.o'), recursive=True):
            os.remove(g)
        rc, log = sh(['ninja', 'unit_tests', 'unit_tests_wrap'], B)
        json.dump(warnings(log), open(os.path.join(W, 'base_warnings.json'), 'w'))
        return
    if cmd == 'run':
        ids = sys.argv[2:]
        out_p = os.path.join(W, 'results.json')
        res = json.load(open(out_p)) if os.path.exists(out_p) else {}
        for s in SCENARIOS:
            if ids and s['id'] not in ids:
                continue
            r = run_one(s)
            res[s['id']] = r
            t = r['tests']
            print(f"{s['id']:3s} build={'ok' if r['build_ok'] else 'FAIL'} errs={sum(r['error_files'].values())} files={list(r['error_files'])[:4]} "
                  f"link={len(r['link'])} " + ' '.join(f"{k}:{v.get('summary', '-')[:60]}" for k, v in t.items()), flush=True)
            json.dump(res, open(out_p, 'w'), indent=1)
        sh('git checkout -q -- . && git clean -qfd -e build', R)
        sh('git checkout -q -- . && git clean -qfd', C)


if __name__ == '__main__' and (len(sys.argv) < 2 or sys.argv[1] != 'report'):
    main()


# ------------------------------------------------------------------------------------------------ report
LESSON = {
    'B1': 'Nothing to do. The prep script should report "impacted, still passing" and stop.',
    'B2': 'Run the impacted tests. A failing test that runs the changed line is a work item: "is the new behaviour intended? then update the expected value, else it is a bug". A weak model must not decide that alone.',
    'B3': 'Same as B2. Two of the failures are in service_test (the service tests exercise MemoryPool directly), found only through references.',
    'B4': 'Same as B2. Error-code changes break every test that pins the code, including tests of callers (service FreeMem).',
    'B5': 'Silent. The new branch is reached, but its reject side is never taken (branch coverage of the diff: 1 of 2). Only diff coverage produces the work item "add a test with bytes > kMaxJobBytes".',
    'B6': 'Caught by the 2 tests that assert openRequests. Nothing flags a deleted side effect that no test asserts; diff coverage has no lines to measure for a deletion.',
    'B7': 'Hand-written fakes that only count some calls stay silent. The strict CppUMock wrap caught it ("Unexpected additional (2nd) call"). Interaction changes are only visible to strict mocks.',
    'B8': 'Silent in both binaries: neither the fakes nor CppUMock check order by default (CppUMock can: mock().strictOrder()).',
    'B9': 'Silent: the fakes ignore the payload size. A stub that records every parameter (withParameter in the wrapper) plus one expectation would catch it.',
    'G1': 'Silent and harmless. The new parameter value (true) has no test: diff coverage shows the new code path, if any.',
    'G2': 'Compile errors in exactly the files clangd predicted. Mechanical fix: the prep script can patch every call (add the new argument) and hand a model only the choice of value.',
    'G3': 'Silent. A wider alias rarely breaks tests; the risk is in serialisation and packed structs, which these tests do not cover.',
    'G4': 'Compile errors only where a test negates the result (!dequeue). Mechanical fix (`!= Status::OK`).',
    'G5': 'Compile errors; a rename is fully mechanical (clangd rename applies it to the tests).',
    'G6': 'Compile error in the only user, a test. Needs a human: delete the test, or keep the function?',
    'G7': 'Compile errors: tests used "exposed for testing" members. This is a test-seam decision (access), not a code fix; follow the project\'s recorded seam.',
    'G8': 'Silent: no call passes a type that makes the overloads ambiguous. Ambiguity only appears with literals of a third type.',
    'G9': 'Silent at build; 1 test fails. Tests passing the int literal 1 now bind to the new overload (exact match beats the uint16_t conversion). Nothing warns.',
    'V1': 'Every fake becomes abstract: 99 errors in 3 test files. clangd "implementation" on the interface finds all the fakes (and the sim). Mechanical: add the method to each fake.',
    'V2': 'Nothing breaks. The fakes do not override the new method, which may matter to a test later.',
    'V3': 'The fakes\' `override` stops matching: errors in every fake. Mechanical: follow the new signature.',
    'V4': 'Same as V3 (a default argument does not keep overrides valid).',
    'V5': '"conflicting return type" in every fake. Mechanical.',
    'T1': 'Nothing (the new field has an initializer).',
    'T2': 'Positional `{999, Status::OK, 0}` initialisers stop compiling where the types differ. Mechanical, but the value for the new field is a choice.',
    'T3': 'Compiles (same types), then 6 tests fail with misleading messages (unknown job, wrong counts). Positional initialisation of same-typed fields is a trap: prefer designated initialisers in tests.',
    'T4': 'Compile errors with a "did you mean pendingRequests" hint. Mechanical rename.',
    'T5': 'Silent: no test reads latencyNs at all (clangd: 0 test references). The prep script can flag "changed field, no test references it".',
    'T6': '3 test failures, then a crash: `kCoreNames` is a std::array sized kCoreCount with 5 initializers, so the 6th name is nullptr and report() dereferences it. Tests using `static_cast<CoreType>(5)` as "invalid core" silently became valid-core tests.',
    'T7': 'Nothing: no switch over Priority without default, no table sized by it.',
    'T8': 'All pass, but 112 fewer checks ran: the tests loop up to the constant and adapted. Comments saying "32" are now stale.',
    'T9': '16 failures: the tests hard-code 64 and 128 instead of kMemAlign. clangd predicted no test (no reference to the constant); only transitive callers of allocate() or a test run finds them.',
    'K1': 'Every fixture that builds a Dispatcher fails to compile (clangd predicted exactly those files). Mechanical: pass the new argument.',
    'K2': 'Silent: every test passes an explicit size or allocates little.',
    'H1': '78 errors in the one test that got SessionManager/PerfMonitor through dispatcher.hpp. References do not show this; the include graph does. Mechanical: add the includes.',
    'H2': '177 errors. Mechanical rename. clangd references on a namespace name returned nothing: a text search is needed here.',
    'H3': 'Link error only in the test binary: the app build globs src/*.cpp, the unit-test build lists its sources. The prep script should compare new source files with the test source list.',
    'W1': '74 of 215 existing tests fail with "Unexpected call": strict stubs change every test in the binary that reaches a wrapped function. Adopt them per binary, or give existing groups ignoreOtherCalls() in setup().',
    'W2': 'Link error naming the OLD signature (the stub and the --wrap list still use the old mangled name). clangd did not flag the stub file: mangled extern "C" names are invisible to it. Regenerate wrappers from declarations.',
    'W3': 'Silent bypass: the call is compiled inline in the caller\'s object, so `--wrap` never sees it. The mocked test gets the real value. Check that every wrapped function is defined out of line, in another object than its callers.',
    'W4': 'Clear link error (undefined `__wrap_...`). The prep script can check the wrap list against the stub file before building.',
    'W5': 'Clear link error (undefined `__real_...`), because `__real_` only exists with `--wrap`. Good: this mistake cannot pass silently.',
    'W6': 'The test that mocked physAddr fails (its value is not used and its expectation is not met). Strict expectations catch removed calls.',
    'X1': 'Compiles and links; 2 of 3 tests fail with garbage values: the stub still calls `__real_hal_read(reg)` without `bank`, so the real function reads an undefined register. Silent ABI mismatch.',
    'X2': 'The same change with `__typeof__(hal_read)` declarations in the stub: a compile error in the stub, at the exact line. Use this guard in every C stub.',
    'X3': 'Compiles and links; the mocked test fails (the wrapper returns an int where the caller reads a double register), the real-path tests pass by accident.',
}
GROUP_FILE = {'CvAccelService': 'tests/service_test.cpp', 'MemoryPool': 'tests/memory_pool_test.cpp', 'RequestQueue': 'tests/request_queue_test.cpp',
              'RequestQueueEnqueue': 'tests/request_queue_test.cpp', 'Dispatcher': 'tests/dispatcher_test.cpp', 'DispatcherWrap': 'tests/wrap/dispatcher_wrap_test.cpp',
              'PerfMonitor': 'tests/perf_monitor_test.cpp', 'SessionManager': 'tests/session_manager_test.cpp', 'Sensor': 'tests/sensor_test.cpp'}


def outcome(x):
    fails = [t for b in x['tests'].values() for t in (b.get('failed') or [])]
    crashed = any(str(b.get('summary', '')).startswith(('CRASHED', 'TIMEOUT')) for b in x['tests'].values())
    nerr = sum(x['error_files'].values())
    if nerr:
        return 'compile', f"{nerr} compile error(s) in {len(x['error_files'])} file(s)", fails, crashed
    if x['link']:
        return 'link', 'link error', fails, crashed
    if crashed:
        return 'crash', f'{len(fails)} failing test(s), then a crash', fails, crashed
    if fails:
        return 'test', f'{len(fails)} failing test(s)', fails, crashed
    return 'silent', 'builds, all tests pass', fails, crashed


def report():
    res = json.load(open(os.path.join(W, 'results.json')))
    pred = json.load(open(os.path.join(W, 'predict.json')))
    L = []
    counts = {}
    rows = []
    for s in SCENARIOS:
        x = res[s['id']]
        kind, what, fails, crashed = outcome(x)
        counts[kind] = counts.get(kind, 0) + 1
        p = pred.get(s['id'])
        if s.get('c'):
            flag = 'n/a (not in the clangd index)'
        elif kind in ('compile', 'link'):
            pfiles = set(p['test_refs']) | {i.rsplit(':', 1)[0] for i in p['impls'] if i.startswith('tests/')}
            afiles = {f for f in x['error_files'] if f.startswith('tests/')}
            if not afiles:
                flag = 'files: none to predict (link step)' if kind == 'link' else 'n/a'
            else:
                hit = afiles & pfiles
                flag = f"files: {len(hit)}/{len(afiles)} predicted" + (f" (+{len(pfiles - afiles)} extra)" if pfiles - afiles else '')
        elif fails:
            d, t = set(p['tests']['direct']), set(p['tests']['transitive'])
            fs = set(fails)
            flag = f"TESTs: {len(fs & d)}/{len(fs)} direct, {len(fs & (d | t))}/{len(fs)} incl. callers (flagged {len(d)} + {len(t)})"
        else:
            n = len(p['tests']['direct']) + len(p['tests']['transitive']) if p else 0
            flag = f'nothing failed; {n} TESTs would have been flagged' if p else 'n/a'
        r = x.get('reach')
        reach = '-' if not r or not r['executable'] else f"{r['executed']}/{r['executable']} lines" + (f", {r['branches_taken']}/{r['branches']} branches" if r.get('branches') else '')
        rows.append((s, kind, what, fails, flag, reach, x))
    icon = {'compile': '🟥 compiler', 'link': '🟧 linker', 'test': '🟨 tests', 'crash': '🟪 crash', 'silent': '⬜ nothing'}
    L.append('# Change-impact study: one change at a time on the cvaccel toy codebase\n')
    L.append('Each row is one kind of change made the way a developer would make it: production code, including its call '
             'sites, is updated until it compiles, and the tests are left untouched. Then the unit tests are built and run, '
             'and the results are recorded. Every scenario was actually run; nothing below is a guess.\n')
    L.append('**Setup**:')
    L.append('- `examples/cvaccel`: C++17, 7 production files, 215 CppUTest tests with hand-written fakes of the '
             '`IAccelBlock` / `IDevice` interfaces.')
    L.append('- A second test binary, `unit_tests_wrap`, uses your shared-stub pattern: `--wrap` plus CppUMock with '
             'passthrough to `__real_`, on `PerfMonitor::record` and `MemoryPool::physAddr` by their mangled names.')
    L.append('- A tiny C module (`hal_read` / `sensor_get`) shows the same pattern for C functions (X1–X3).')
    L.append('- GCC 13, GNU ld, Ninja, gcov, clangd 22. The script is `study.py`; raw results are in `results/`.\n')
    L.append('**Columns**:')
    L.append('- **Caught by**: the first thing that noticed the change.')
    L.append('- **Change reached by tests**: changed production lines (and their branches) executed by any test (gcov).')
    L.append('- **clangd before the change**: what a prep script would have flagged from references and implementations '
             'of the changed symbol, taken before the edit, against what actually broke. "direct" means TEST blocks that '
             'reference the symbol; "incl. callers" adds TEST blocks that reach it through up to 2 levels of production '
             'callers.\n')
    L.append('## Summary\n')
    L.append('| Caught by | Scenarios |\n|---|---|')
    for k in ('compile', 'link', 'test', 'crash', 'silent'):
        L.append(f"| {icon[k]} | {counts.get(k, 0)}: {', '.join(r[0]['id'] for r in rows if r[1] == k)} |")
    L.append('')
    L.append('Main findings:')
    L.append('1. **Structural changes fail loudly, and clangd predicts them.** Signatures, interfaces, fields, '
             'constructors and namespaces all break the build (G2, G4–G7, V1, V3–V5, T2, T4, K1, H1, H2). clangd '
             'flagged the broken test files beforehand in all but two cases:')
    L.append('   - G7: three members were made private, and the prediction asked about only one of them;')
    L.append('   - H2: clangd returns no references for a namespace name, so a text search is needed.')
    L.append('   Most fixes are mechanical: a script can patch them and leave only value choices to a model.')
    L.append('2. **Behaviour changes are caught only by tests that pin the exact value.** For B2–B4, B6, B7, G9, T3, T6 and T9:')
    L.append('   - direct references found 19 of the 39 failing TESTs (0 of 16 in T9);')
    L.append('   - adding production callers found all 39, but flagged 34–127 of the 215 TESTs per change.')
    L.append('   The precise list is "TESTs that execute the changed lines", which needs coverage per test (a traced run).')
    L.append('3. **Silent changes cluster:**')
    L.append('   - new branches (B5: the change is reached, but only branch coverage shows the untested side);')
    L.append('   - interaction changes (B8 order, B9 wrong argument; B7 extra call is silent with the hand-written fakes and caught only by the strict wrap stubs);')
    L.append('   - widened, narrowed or unused types and constants (G3, T5, T7, T8, K2);')
    L.append('   - overload resolution silently moving to a new overload (G9).')
    L.append('   Diff coverage plus "changed symbol with no test reference" catch most of them; strict mocks catch the '
             'interaction ones.')
    L.append('4. **Hard-coded values in tests hide from static analysis** (T9: 16 failures, 0 references to `kMemAlign` '
             'in tests). Same-typed positional initialisers compile after a reorder and then fail confusingly (T3).')
    L.append('5. **Your `--wrap` + CppUMock stubs:**')
    L.append('   - A signature change of a wrapped C++ function gives a clear link error (W2), and so do both wrap-list '
             'mistakes (W4: flag without a stub, W5: stub without a flag). The stub file is invisible to clangd, so a '
             'prep script must regenerate or check wrappers from the declarations.')
    L.append('   - Moving a wrapped function inline bypasses the wrap silently (W3).')
    L.append('   - Adopting strict stubs in an existing binary fails 74 of 215 tests until those groups ignore the '
             'wrapped calls (W1).')
    L.append('   - In C, an unguarded stub turns a signature change into garbage values at run time (X1, X3). '
             'Declaring `__real_`/`__wrap_` with `__typeof__(fn)` turns it into a compile error at the stub line (X2).\n')
    cats = []
    for s, *_ in rows:
        if s['cat'] not in cats:
            cats.append(s['cat'])
    for cat in cats:
        L.append(f'## {cat}\n')
        L.append('| # | Change | Caught by | What happened | Change reached by tests | clangd before the change | What the prep script / agent must do |')
        L.append('|---|---|---|---|---|---|---|')
        for s, kind, what, fails, flag, reach, x in rows:
            if s['cat'] != cat:
                continue
            files = ', '.join(f"`{os.path.basename(f)}` ({n})" for f, n in sorted(x['error_files'].items(), key=lambda kv: -kv[1])[:4])
            happened = what + (f': {files}' if files else '')
            if fails:
                happened += '<br>' + '<br>'.join(f'`{t}`' for t in fails[:4]) + (f'<br>… +{len(fails) - 4}' if len(fails) > 4 else '')
            if x['link']:
                happened += '<br>`' + x['link'][0][:110].replace('|', '\\|') + '`'
            L.append(f"| {s['id']} | **{s['title']}**<br>{s['change']} | {icon[kind]} | {happened} | {reach} | {flag} | {LESSON.get(s['id'], '')} |")
        L.append('')
    L.append('## What this means for the prep script\n')
    L.append('| Change kind (from the git diff) | How it shows up | Detection before the build | Work item for the model |')
    L.append('|---|---|---|---|')
    L.append('| Signature, rename, removed or private member, ctor parameter, namespace | compile errors | clangd references (files exact in this study) | Mostly a script patch; the model chooses values only (G2, K1, T2) |')
    L.append('| Pure virtual added or changed | compile errors in every fake | clangd `implementation` on the interface | Script adds or updates the override in each fake |')
    L.append('| Body: boundary, error code, removed side effect | failing tests | TESTs that execute the changed lines (coverage per test), or references + callers (over-flags) | "Intended or bug?" per failing test; never auto-update an expected value |')
    L.append('| Body: new branch or validation | silent | branch coverage of the diff | "Add a test that takes <condition> at <file:line>" |')
    L.append('| Interaction: extra, missing or reordered call, argument | silent with fakes; strict mocks catch count and arguments | diff shows calls added or removed | Update expectations; stubs should record all parameters |')
    L.append('| Type width, constant, enum, default argument | often silent; crashes where a table is sized by a count (T6) | changed symbol has 0 or few test references; grep for literals equal to the old value (T9) | Review item listing tests that hard-code the old value |')
    L.append('| Header includes, new source file | compile errors (H1) or a test-only link error (H3) | include graph; new file vs the test source list | Script patch |')
    L.append('| Wrapped function: signature, inline, wrap list | link errors (W2, W4, W5) or a silent bypass (W3) | compare declarations, `nm` symbols and the wrap list; clangd does not see mangled stubs | Regenerate the wrapper; for C, `__typeof__` guards |')
    L.append('')
    L.append('## Details per scenario\n')
    for s, kind, what, fails, flag, reach, x in rows:
        L.append(f"<details><summary><b>{s['id']}</b> {s['title']} ({icon[kind]})</summary>\n")
        L.append('```diff\n' + '\n'.join(l for l in x['diff'].splitlines() if not l.startswith('index '))[:2500] + '\n```')
        if x['errors']:
            L.append('First errors:\n```\n' + '\n'.join(x['errors'][:6]) + '\n```')
        if x['link']:
            L.append('Link:\n```\n' + '\n'.join(x['link'][:3]) + '\n```')
        for b, t in x['tests'].items():
            if t.get('ran'):
                L.append(f"`{b}`: {t.get('summary', '')[:200]}" + ('<br>' + '<br>'.join(f'`{f}`' for f in (t.get('failed') or [])[:8]) if t.get('failed') else ''))
                if t.get('detail'):
                    L.append('```\n' + '\n'.join(t['detail'][:3]) + '\n```')
            else:
                L.append(f'`{b}`: not built')
        L.append('\n</details>\n')
    open(os.path.join(HERE, 'STUDY.md'), 'w').write('\n'.join(L) + '\n')
    print('wrote STUDY.md', counts)


if __name__ == '__main__' and len(sys.argv) > 1 and sys.argv[1] == 'report':
    report()
