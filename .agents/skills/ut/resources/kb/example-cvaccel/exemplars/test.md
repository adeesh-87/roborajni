# Test exemplar: /tmp/claude-0/-home-user-roborajni/b4020067-36df-5cb5-a6cf-14371abb2f61/scratchpad/cvrepo/tests/session_manager_test.cpp  (approved: no; DRAFT picked by testscan)
Copy this shape for every new test. Verbatim from the repo; the right column names each part.

```cpp
#include "cvaccel/session_manager.hpp"                                 // header of the code under test / helper

#include "CppUTest/TestHarness.h"                                      // framework header

TEST_GROUP(SessionManager) {};                                         // test group: one per source file

// L6: fresh manager, slot 0 is already inactive, so the loop body matches on i=0 -- 0 iterations
// skipped before the match.
TEST(SessionManager, Open_NoActiveSessions_ReturnsOkWithFirstId) {     // one test = one behaviour: <Function>_<Condition>_<Expected>
    cvaccel::SessionManager mgr;
    cvaccel::SessionId id = 0;
    cvaccel::Status st = mgr.open(1, cvaccel::Priority::NORMAL, id);
    CHECK(st == cvaccel::Status::OK);                                  // assert: expected value first
    LONGS_EQUAL(1, id);                                                // assert: expected value first
}

// L6: slot 0 is already active (opened once), so the loop skips i=0 and matches at i=1 --
// 1 iteration skipped before the match.
TEST(SessionManager, Open_OneActiveSession_ReturnsOkWithSecondId) {    // one test = one behaviour: <Function>_<Condition>_<Expected>
    cvaccel::SessionManager mgr;
    cvaccel::SessionId id1 = 0, id2 = 0;
    CHECK(mgr.open(1, cvaccel::Priority::NORMAL, id1) == cvaccel::Status::OK);

    cvaccel::Status st = mgr.open(2, cvaccel::Priority::NORMAL, id2);
    CHECK(st == cvaccel::Status::OK);                                  // assert: expected value first
    LONGS_EQUAL(2, id2);                                               // assert: expected value first
}

// L6: slots 0-2 are already active (three prior opens), so the loop skips i=0,1,2 and matches
// at i=3 -- many iterations skipped before the match.
TEST(SessionManager, Open_ThreeActiveSessions_ReturnsOkWithFourthId) {
    cvaccel::SessionManager mgr;
    cvaccel::SessionId id1 = 0, id2 = 0, id3 = 0, id4 = 0;
    CHECK(mgr.open(1, cvaccel::Priority::NORMAL, id1) == cvaccel::Status::OK);
    CHECK(mgr.open(2, cvaccel::Priority::NORMAL, id2) == cvaccel::Status::OK);
    CHECK(mgr.open(3, cvaccel::Priority::NORMAL, id3) == cvaccel::Status::OK);

    cvaccel::Status st = mgr.open(4, cvaccel::Priority::NORMAL, id4);
    CHECK(st == cvaccel::Status::OK);                                  // assert: expected value first
    LONGS_EQUAL(4, id4);                                               // assert: expected value first
}

// L8 true: the found slot is populated with every field open() sets, and marked active.
TEST(SessionManager, Open_InactiveSlotFound_PopulatesSessionFields) {  // one test = one behaviour: <Function>_<Condition>_<Expected>
    cvaccel::SessionManager mgr;
    cvaccel::SessionId id = 0;
    cvaccel::Status st = mgr.open(55, cvaccel::Priority::HIGH, id);
    CHECK(st == cvaccel::Status::OK);                                  // assert: expected value first

    cvaccel::SessionInfo* s = mgr.find(id);
    CHECK(s != nullptr);                                               // assert: expected value first
    LONGS_EQUAL(55, s->clientFd);                                      // assert: expected value first
    CHECK(s->priority == cvaccel::Priority::HIGH);                     // assert: expected value first
    UNSIGNED_LONGS_EQUAL(0, s->openRequests);
    UNSIGNED_LONGS_EQUAL(0, s->bytesAllocated);
    CHECK_TRUE(s->active);                                             // assert: expected value first
}

// L8 false on every iteration: all kMaxSessions slots are active, so the loop runs to
// completion without ever matching and falls through to NO_MEMORY.
TEST(SessionManager, Open_AllSlotsActive_ReturnsNoMemory) {            // one test = one behaviour: <Function>_<Condition>_<Expected>
    cvaccel::SessionManager mgr;
    cvaccel::SessionId id = 0;
    for (unsigned i = 0; i < cvaccel::kMaxSessions; ++i) {
        CHECK(mgr.open(static_cast<cvaccel::ClientFd>(i), cvaccel::Priority::NORMAL, id) == cvaccel::Status::OK);
    }

    cvaccel::Status st = mgr.open(999, cvaccel::Priority::NORMAL, id);
    CHECK(st == cvaccel::Status::NO_MEMORY);                           // assert: expected value first
}

// L24 true: nothing was ever opened, so find() returns nullptr and close() reports NO_SESSION.
TEST(SessionManager, Close_SessionNotFound_ReturnsNoSession) {         // one test = one behaviour: <Function>_<Condition>_<Expected>
    cvaccel::SessionManager mgr;
    cvaccel::Status st = mgr.close(1);
    CHECK(st == cvaccel::Status::NO_SESSION);                          // assert: expected value first
}

// L24 false: the session was opened, so find() returns a pointer, close() resets the slot to a
// default SessionInfo{} (active=false) and returns OK.
```
