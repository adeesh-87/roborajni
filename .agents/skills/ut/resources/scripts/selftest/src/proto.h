#ifndef PROTO_H
#define PROTO_H
#include <stdint.h>
#include "fw_config.h"
#ifdef __cplusplus
extern "C" {
#endif
typedef enum { P_IDLE, P_LEN, P_DATA, P_CRC } proto_state_t;
FW_API int proto_feed(uint8_t byte);
FW_API void proto_reset(void);
#ifdef __cplusplus
}
#endif
#endif
