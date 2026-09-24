#include "proto.h"
#include "uart.h"
#include "crc.h"

static proto_state_t s_state = P_IDLE;
static uint8_t s_buf[32];
static uint8_t s_len, s_pos;

STATIC int proto_frame_done(void)
{
    uint16_t c = crc16(s_buf, s_len);
    const uint8_t ack[2] = { (uint8_t)(c >> 8), (uint8_t)c };
    return uart_send(ack, 2u);
}

FW_API void proto_reset(void) { s_state = P_IDLE; s_len = 0; s_pos = 0; }

FW_API int proto_feed(uint8_t byte)
{
    switch (s_state) {
    case P_IDLE: if (byte == 0x7E) { s_state = P_LEN; } break;
    case P_LEN:
        FW_ASSERT(byte <= sizeof(s_buf));
        s_len = byte; s_pos = 0; s_state = (byte != 0u) ? P_DATA : P_CRC; break;
    case P_DATA: s_buf[s_pos++] = byte; if (s_pos == s_len) { s_state = P_CRC; } break;
    case P_CRC: proto_reset(); return proto_frame_done();
    default: proto_reset(); break;
    }
    return 0;
}
