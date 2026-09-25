# Scenarios
Generated from the clang index (2026-09-25 09:48). One scenario per entry point (a public function no production code calls). Each file is a Mermaid sequence diagram written for reading, not rendering.

## Module overview (production calls between modules; number = call sites)
```mermaid
flowchart LR
  Client -->|8| ITransport
  CvAccelService -->|6| Dispatcher
  CvAccelService -->|2| IAccelBlock
  CvAccelService -->|3| IDevice
  CvAccelService -->|6| MemoryPool
  CvAccelService -->|2| PerfMonitor
  CvAccelService -->|1| PerfStats
  CvAccelService -->|2| RequestQueue
  CvAccelService -->|13| SessionManager
  Dispatcher -->|2| IAccelBlock
  Dispatcher -->|6| IDevice
  Dispatcher -->|1| MemoryPool
  Dispatcher -->|2| PerfMonitor
  Dispatcher -->|3| RequestQueue
  Dispatcher -->|3| SessionManager
  Dispatcher -->|2| dispatcher
  MemoryPool -->|1| memory_pool
  PerfMonitor -->|1| PerfStats
  PerfMonitor -->|2| perf_monitor
  RequestQueue -->|1| request_queue
  SessionManager -->|1| f
  dispatcher -->|1| MemoryPool
```

## Catalog
| Scenario (entry point) | Defined at | Participants | Messages | File |
|---|---|---|---|---|
| Client::openSession | examples/cvaccel/client/src/cvclient.cpp:33 | 2 | 1 | (not included) scenarios/Client__openSession.md |
| Client::allocMem | examples/cvaccel/client/src/cvclient.cpp:48 | 2 | 1 | (not included) scenarios/Client__allocMem.md |
| Client::freeMem | examples/cvaccel/client/src/cvclient.cpp:56 | 2 | 1 | (not included) scenarios/Client__freeMem.md |
| Client::postConfig | examples/cvaccel/client/src/cvclient.cpp:62 | 2 | 1 | (not included) scenarios/Client__postConfig.md |
| Client::submit | examples/cvaccel/client/src/cvclient.cpp:76 | 2 | 1 | (not included) scenarios/Client__submit.md |
| Client::getStats | examples/cvaccel/client/src/cvclient.cpp:100 | 2 | 1 | (not included) scenarios/Client__getStats.md |
| MemoryPool::map | examples/cvaccel/src/memory_pool.cpp:69 | 1 | 1 | (not included) scenarios/MemoryPool__map.md |
| PerfMonitor::report | examples/cvaccel/src/perf_monitor.cpp:57 | 2 | 1 | (not included) scenarios/PerfMonitor__report.md |
| CvAccelService::handle | examples/cvaccel/src/service.cpp:18 | 12 | 60 | (not included) scenarios/CvAccelService__handle.md |
| CvAccelService::clientDisconnected | examples/cvaccel/src/service.cpp:137 | 7 | 13 | (not included) scenarios/CvAccelService__clientDisconnected.md |
| CvAccelService::pump | examples/cvaccel/src/service.cpp:150 | 11 | 21 | (not included) scenarios/CvAccelService__pump.md |
| CvAccelService::queued | examples/cvaccel/src/service.cpp:155 | 2 | 1 | (not included) scenarios/CvAccelService__queued.md |
