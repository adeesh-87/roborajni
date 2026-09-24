#include "hal.h"
#include "fw_config.h"
static uint32_t g_tick;
uint32_t hal_get_tick(void) { return g_tick++; }
void hal_dma_start(const uint8_t* b, uint32_t n) { (void)b; (void)n; }
void fw_assert_failed(const char* f, int l) { (void)f; (void)l; }
