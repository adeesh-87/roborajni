#ifndef HAL_H
#define HAL_H
#include <stdint.h>
typedef struct { volatile uint32_t DR; volatile uint32_t SR; } UART_TypeDef;
#define UART0 ((UART_TypeDef*)0x40001000u)
#define UART_SR_TXE (1u << 7)
uint32_t hal_get_tick(void);
void hal_dma_start(const uint8_t* buf, uint32_t len);
#endif
