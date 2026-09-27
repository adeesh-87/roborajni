| Codebase | Arm | Runs | Tests pass | RESULT: DONE | Branch cov. (mean) | 100% branches | Cost/run | Turns | Time/run | Code lookups | Builds | Denied |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| cvaccel | graphify | 18 | 8/18 | 7/18 | 36% | 4/18 | $0.59 | 66 | 280 s | 38.6 | 11.0 | 5.5 |
| cvaccel | clangd | 18 | 15/18 | 12/18 | 78% | 7/18 | $0.58 | 63 | 323 s | 36.8 | 10.8 | 6.1 |
| cvaccel | grep | 18 | 17/18 | 17/18 | 92% | 11/18 | $0.43 | 42 | 226 s | 22.1 | 7.4 | 0.0 |
| libcanard | graphify | 18 | 16/18 | 14/18 | 65% | 0/18 | $0.64 | 61 | 291 s | 32.5 | 10.2 | 4.7 |
| libcanard | clangd | 18 | 11/18 | 10/18 | 47% | 0/18 | $0.69 | 72 | 311 s | 42.2 | 8.9 | 5.8 |
| libcanard | grep | 18 | 15/18 | 14/18 | 61% | 0/18 | $0.66 | 57 | 259 s | 31.7 | 8.7 | 0.0 |
| all | graphify | 36 | 24/36 | 21/36 | 51% | 4/36 | $0.62 | 64 | 285 s | 35.5 | 10.6 | 5.1 |
| all | clangd | 36 | 26/36 | 22/36 | 63% | 7/36 | $0.64 | 67 | 317 s | 39.5 | 9.9 | 6.0 |
| all | grep | 36 | 32/36 | 31/36 | 77% | 11/36 | $0.55 | 49 | 243 s | 26.9 | 8.1 | 0.0 |

| Codebase | Task | graphify: pass, branch cov. per run | clangd: pass, branch cov. per run | grep: pass, branch cov. per run | graphify $ | clangd $ | grep $ |
|---|---|---|---|---|---|---|---|
| cvaccel | CvAccelService::postConfig | ✗- ✓0/20 ✗- | ✓0/20 ✓19/20 ✓19/20 | ✓19/20 ✓19/20 ✓19/20 | 0.89 | 0.55 | 0.34 |
| cvaccel | Dispatcher::cancelSession | ✗- ✗- ✗- | ✓12/17 ✓13/17 ✓14/17 | ✓16/17 ✗- ✓14/17 | 0.67 | 0.74 | 0.60 |
| cvaccel | Dispatcher::onCompletion | ✗- ✓12/15 ✗- | ✓15/15 ✗- ✓15/15 | ✓15/15 ✓15/15 ✓15/15 | 0.74 | 0.70 | 0.41 |
| cvaccel | Dispatcher::pump | ✗- ✗- ✗- | ✓24/24 ✗6/24 ✓24/24 | ✓24/24 ✓24/24 ✓24/24 | 0.67 | 0.84 | 0.68 |
| cvaccel | MemoryPool::allocate | ✓19/19 ✓17/19 ✓16/19 | ✗17/19 ✓17/19 ✓17/19 | ✓19/19 ✓17/19 ✓19/19 | 0.30 | 0.47 | 0.31 |
| cvaccel | RequestQueue::enqueue | ✓17/17 ✓17/17 ✓17/17 | ✓17/17 ✓17/17 ✓17/17 | ✓17/17 ✓17/17 ✓17/17 | 0.28 | 0.16 | 0.26 |
| libcanard | node_id_occupancy_update | ✓26/36 ✓24/36 ✓26/36 | ✓27/36 ✓26/36 ✓25/36 | ✓28/36 ✓24/36 ✓25/36 | 0.45 | 0.63 | 0.50 |
| libcanard | rx_filter_configure | ✓14/20 ✓16/20 ✓14/20 | ✓14/20 ✓15/20 ✓16/20 | ✗- ✓16/20 ✓16/20 | 0.32 | 0.50 | 0.57 |
| libcanard | rx_parse | ✓73/88 ✓72/88 ✓70/88 | ✓74/88 ✓77/88 ✓75/88 | ✓73/88 ✓75/88 ✓73/88 | 0.81 | 0.85 | 0.46 |
| libcanard | rx_session_complete_slot | ✗- ✓19/28 ✓19/28 | ✗- ✗- ✗- | ✓19/28 ✓19/28 ✓19/28 | 0.75 | 0.73 | 0.59 |
| libcanard | rx_session_update | ✗- ✓36/50 ✓24/50 | ✗- ✗- ✗- | ✗- ✓26/50 ✗- | 0.81 | 0.75 | 1.02 |
| libcanard | tx_push | ✓28/36 ✓28/36 ✓28/36 | ✓26/36 ✗- ✓28/36 | ✓27/36 ✓27/36 ✓27/36 | 0.71 | 0.71 | 0.82 |
