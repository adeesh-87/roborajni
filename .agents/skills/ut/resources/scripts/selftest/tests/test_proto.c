#include "mini_test.h"
#include "proto.h"
TEST(Proto, Feed_StartByte_ReturnsZero) { proto_reset(); CHECK(proto_feed(0x7E) == 0); }
TEST(Proto, Reset_IsIdempotent) { proto_reset(); proto_reset(); }
