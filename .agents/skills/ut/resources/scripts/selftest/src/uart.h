#ifndef UART_H
#define UART_H
#include <stdint.h>
#include "fw_config.h"
#ifdef __cplusplus
extern "C" {
#endif
typedef void (*uart_cb_t)(int status);
FW_API int uart_send(const uint8_t* buf, uint32_t len);
FW_API int uart_flush(void);
FW_API void uart_set_callback(uart_cb_t cb);
#ifdef __cplusplus
}
#endif
#endif
