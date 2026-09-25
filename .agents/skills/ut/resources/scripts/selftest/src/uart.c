#include "uart.h"
#include "hal.h"

static uart_cb_t s_cb;

STATIC int uart_wait_ready(uint32_t timeout_ms)
{
    uint32_t start = hal_get_tick();
    while ((UART0->SR & UART_SR_TXE) == 0u) {
        if ((hal_get_tick() - start) > timeout_ms) {
            return -1;
        }
    }
    return 0;
}

FW_API int uart_send(const uint8_t* buf, uint32_t len)
{
    FW_ASSERT(buf != 0);
    for (uint32_t i = 0; i < len; i++) {
        if (uart_wait_ready(10u) != 0) {
            if (s_cb) { s_cb(-1); }
            return -1;
        }
        UART0->DR = buf[i];
    }
    return (int)len;
}

#if FW_USE_DMA
FW_API int uart_flush(void)
{
    static const uint8_t pad[1] = {0};
    hal_dma_start(pad, 1u);
    return uart_wait_ready(100u);
}
#else
FW_API int uart_flush(void)
{
    return uart_send((const uint8_t*)"", 0u);
}
#endif

FW_API void uart_set_callback(uart_cb_t cb) { s_cb = cb; }
