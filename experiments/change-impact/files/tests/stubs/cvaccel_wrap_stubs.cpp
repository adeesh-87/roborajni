// Shared stubs (the project's --wrap + CppUMock pattern): every wrapped function records the call, returns the
// test's value when the test gave one, and otherwise runs the real function (__real_).
// C++ functions are wrapped by their mangled names (see tests/CMakeLists.txt: target_link_options ... --wrap=).
#include "cvaccel/perf_monitor.hpp"          // project and std headers first: CppUTest redefines new/delete
#include "cvaccel/memory_pool.hpp"
#include "CppUTestExt/MockSupport.h"
using namespace cvaccel;

// Status PerfMonitor::record(const PerfRecord&)
extern "C" Status __real__ZN7cvaccel11PerfMonitor6recordERKNS_10PerfRecordE(PerfMonitor* self, const PerfRecord& r);
extern "C" Status __wrap__ZN7cvaccel11PerfMonitor6recordERKNS_10PerfRecordE(PerfMonitor* self, const PerfRecord& r) {
    mock("PerfMonitor::record").actualCall("PerfMonitor::record")
        .withUnsignedIntParameter("request", r.request).withIntParameter("status", static_cast<int>(r.status));
    if (mock("PerfMonitor::record").hasReturnValue())
        return static_cast<Status>(mock("PerfMonitor::record").intReturnValue());
    return __real__ZN7cvaccel11PerfMonitor6recordERKNS_10PerfRecordE(self, r);
}

// uint64_t MemoryPool::physAddr(MemHandle) const
extern "C" uint64_t __real__ZNK7cvaccel10MemoryPool8physAddrEj(const MemoryPool* self, MemHandle h);
extern "C" uint64_t __wrap__ZNK7cvaccel10MemoryPool8physAddrEj(const MemoryPool* self, MemHandle h) {
    mock("MemoryPool::physAddr").actualCall("MemoryPool::physAddr").withUnsignedIntParameter("h", h);
    if (mock("MemoryPool::physAddr").hasReturnValue())
        return mock("MemoryPool::physAddr").unsignedLongLongIntReturnValue();
    return __real__ZNK7cvaccel10MemoryPool8physAddrEj(self, h);
}
