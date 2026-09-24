#include "drv.h"
#include "uart.h"

static int  uart_open(void) { return 0; }
static int  uart_write(const uint8_t* b, uint32_t n) { return uart_send(b, n); }
static void uart_close(void) { }
static void drv_on_error(int code) { (void)code; }
static void drv_on_done(void) { }

static const drv_ops_t s_uart_ops = { .open = uart_open, .write = uart_write, .close = uart_close };
static drv_events_t s_events = { drv_on_error, drv_on_done };
static const drv_ops_t* s_ops;

static void drv_uart_cb(int status) { if (status < 0) { s_events.on_error(status); } }

FW_API void drv_init(void)
{
    s_ops = &s_uart_ops;
    uart_set_callback(drv_uart_cb);
}

FW_API int drv_write_all(const uint8_t* b, uint32_t n)
{
    if (s_ops->open() != 0) { return -1; }
    int r = s_ops->write(b, n);
    s_ops->close();
    if (r >= 0) { s_events.on_done(); }
    return r;
}
