#include "cvaccel/session_manager.hpp"

#include "CppUTest/TestHarness.h"

TEST_GROUP(SessionManager) {};

// L6: fresh manager, slot 0 is already inactive, so the loop body matches on i=0 -- 0 iterations
// skipped before the match.
TEST(SessionManager, Open_NoActiveSessions_ReturnsOkWithFirstId) {
    cvaccel::SessionManager mgr;
    cvaccel::SessionId id = 0;
    cvaccel::Status st = mgr.open(1, cvaccel::Priority::NORMAL, id);
    CHECK(st == cvaccel::Status::OK);
    LONGS_EQUAL(1, id);
}

// L6: slot 0 is already active (opened once), so the loop skips i=0 and matches at i=1 --
// 1 iteration skipped before the match.
TEST(SessionManager, Open_OneActiveSession_ReturnsOkWithSecondId) {
    cvaccel::SessionManager mgr;
    cvaccel::SessionId id1 = 0, id2 = 0;
    CHECK(mgr.open(1, cvaccel::Priority::NORMAL, id1) == cvaccel::Status::OK);

    cvaccel::Status st = mgr.open(2, cvaccel::Priority::NORMAL, id2);
    CHECK(st == cvaccel::Status::OK);
    LONGS_EQUAL(2, id2);
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
    CHECK(st == cvaccel::Status::OK);
    LONGS_EQUAL(4, id4);
}

// L8 true: the found slot is populated with every field open() sets, and marked active.
TEST(SessionManager, Open_InactiveSlotFound_PopulatesSessionFields) {
    cvaccel::SessionManager mgr;
    cvaccel::SessionId id = 0;
    cvaccel::Status st = mgr.open(55, cvaccel::Priority::HIGH, id);
    CHECK(st == cvaccel::Status::OK);

    cvaccel::SessionInfo* s = mgr.find(id);
    CHECK(s != nullptr);
    LONGS_EQUAL(55, s->clientFd);
    CHECK(s->priority == cvaccel::Priority::HIGH);
    UNSIGNED_LONGS_EQUAL(0, s->openRequests);
    UNSIGNED_LONGS_EQUAL(0, s->bytesAllocated);
    CHECK_TRUE(s->active);
}

// L8 false on every iteration: all kMaxSessions slots are active, so the loop runs to
// completion without ever matching and falls through to NO_MEMORY.
TEST(SessionManager, Open_AllSlotsActive_ReturnsNoMemory) {
    cvaccel::SessionManager mgr;
    cvaccel::SessionId id = 0;
    for (unsigned i = 0; i < cvaccel::kMaxSessions; ++i) {
        CHECK(mgr.open(static_cast<cvaccel::ClientFd>(i), cvaccel::Priority::NORMAL, id) == cvaccel::Status::OK);
    }

    cvaccel::Status st = mgr.open(999, cvaccel::Priority::NORMAL, id);
    CHECK(st == cvaccel::Status::NO_MEMORY);
}

// L24 true: nothing was ever opened, so find() returns nullptr and close() reports NO_SESSION.
TEST(SessionManager, Close_SessionNotFound_ReturnsNoSession) {
    cvaccel::SessionManager mgr;
    cvaccel::Status st = mgr.close(1);
    CHECK(st == cvaccel::Status::NO_SESSION);
}

// L24 false: the session was opened, so find() returns a pointer, close() resets the slot to a
// default SessionInfo{} (active=false) and returns OK.
TEST(SessionManager, Close_SessionFound_ReturnsOkAndClearsSlot) {
    cvaccel::SessionManager mgr;
    cvaccel::SessionId id = 0;
    CHECK(mgr.open(3, cvaccel::Priority::NORMAL, id) == cvaccel::Status::OK);

    cvaccel::Status st = mgr.close(id);
    CHECK(st == cvaccel::Status::OK);
    POINTERS_EQUAL(nullptr, mgr.find(id));
}

// L30 true: each sub-condition of (id == 0 || id > kMaxSessions) flips the outcome alone --
// id == 0 alone, and id > kMaxSessions alone -- both return nullptr without touching sessions_.
TEST(SessionManager, Find_IdOutOfRange_ReturnsNullptr) {
    cvaccel::SessionManager mgr;
    POINTERS_EQUAL(nullptr, mgr.find(0));
    POINTERS_EQUAL(nullptr, mgr.find(cvaccel::kMaxSessions + 1));
}

// L30 false: id == kMaxSessions is in range (neither sub-condition holds), so find() proceeds
// past the range guard to inspect sessions_[kMaxSessions - 1].
TEST(SessionManager, Find_IdEqualsKMaxSessions_PassesRangeCheck) {
    cvaccel::SessionManager mgr;
    POINTERS_EQUAL(nullptr, mgr.find(cvaccel::kMaxSessions));
}

// L32 true (!s.active sub-condition): id=1 is in range, but slot 0 was never opened, so it is
// still default-constructed (active=false), and find() returns nullptr.
// Note: the other sub-condition (s.id != id) cannot be driven independently through the public
// API -- open()/close() always keep s.id in sync with the slot index (id-1), so a slot can only
// be active with s.id == id, never active with a mismatched id.
TEST(SessionManager, Find_SlotNotActive_ReturnsNullptr) {
    cvaccel::SessionManager mgr;
    POINTERS_EQUAL(nullptr, mgr.find(1));
}

// L32 false: the slot is active and its stored id matches, so find() returns a pointer to it.
TEST(SessionManager, Find_SlotActiveWithMatchingId_ReturnsPointer) {
    cvaccel::SessionManager mgr;
    cvaccel::SessionId id = 0;
    CHECK(mgr.open(7, cvaccel::Priority::NORMAL, id) == cvaccel::Status::OK);

    cvaccel::SessionInfo* s = mgr.find(id);
    CHECK(s != nullptr);
    UNSIGNED_LONGS_EQUAL(id, s->id);
    LONGS_EQUAL(7, s->clientFd);
}

// Straight-line: owns() is true only when find() returns non-null and the stored clientFd
// matches; a wrong fd or an unopened id must each make it false.
TEST(SessionManager, Owns_TypicalInputs_MatchesFindAndClientFd) {
    cvaccel::SessionManager mgr;
    cvaccel::SessionId id = 0;
    CHECK(mgr.open(42, cvaccel::Priority::HIGH, id) == cvaccel::Status::OK);

    CHECK_TRUE(mgr.owns(id, 42));
    CHECK_FALSE(mgr.owns(id, 99));         // s != nullptr but s->clientFd (42) != clientFd (99)
    CHECK_FALSE(mgr.owns(id + 1, 42));     // find(id + 1) is nullptr (never opened)
}

// L50 true: the opened slot has s.active == true, so it is counted.
TEST(SessionManager, ActiveCount_OneOpenSession_ReturnsOne) {
    cvaccel::SessionManager mgr;
    cvaccel::SessionId id = 0;
    CHECK(mgr.open(1, cvaccel::Priority::NORMAL, id) == cvaccel::Status::OK);

    UNSIGNED_LONGS_EQUAL(1, mgr.activeCount());
}

// L50 false: no sessions were ever opened, so every slot has s.active == false and the count
// stays 0.
TEST(SessionManager, ActiveCount_NoActiveSessions_ReturnsZero) {
    cvaccel::SessionManager mgr;
    UNSIGNED_LONGS_EQUAL(0, mgr.activeCount());
}
