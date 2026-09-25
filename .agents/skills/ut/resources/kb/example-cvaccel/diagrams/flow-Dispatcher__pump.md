%% Flow of Dispatcher::pump  examples/cvaccel/src/dispatcher.cpp:34-86
%% Lnn = source line. T/F = condition true/false. "Nx" = times taken in the imported coverage run; NOT HIT = never taken.
%% Coverage: missing outcomes: L82 if (si && si->openRequests > 0): only 1/4 branch outcomes hit
flowchart TD
  S(["start"])
  d36{"L36 for unsigned c = 0; c < kCoreCount; ++c"}
  d38{"L38 while !hw_.isBusy(core)"}
  c38["L38 hw_.isBusy(); L40 queue_.dequeue()"]
  d40{"L40 if !queue_.dequeue(core, r)"}
  c42["L42 start()"]
  d43{"L43 if st == Status::OK"}
  d47{"L47 if st == Status::BUSY"}
  c50["L50 queue_.enqueue()"]
  c55["L55 dev_.nowNs(); L61 blockBytesOf(); L67 perf_.record()"]
  d75{"L75 if r.clientFd != -1"}
  c78["L78 dev_.ioctlToClient()"]
  c81["L81 sessions_.find()"]
  d82{"L82 if si && si->openRequests > 0 [2 sub-conditions]"}
  r85(["L85 return started"])
  S --> d36
  d36 -->|"loop 375x"| d38
  d38 -->|"loop 239x"| c38
  c38 --> d40
  d40 -->|"F 40x"| c42
  c42 --> d43
  d43 -->|"T 32x"| d38
  d43 -->|"F 8x"| d47
  d47 -->|"T 1x"| c50
  d47 -->|"F 7x"| c55
  c55 --> d75
  d75 -->|"T 1x"| c78
  c78 --> c81
  d75 -->|"F 6x"| c81
  c81 --> d82
  d82 -->|"T (1/4 branch outcomes hit)"| d38
  d82 -->|"F"| d38
  d38 -->|"done 175x"| d36
  d40 -->|"T 199x"| d36
  c50 --> d36
  d36 -->|"done 75x"| r85
