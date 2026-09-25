#ifndef FW_CONFIG_H
#define FW_CONFIG_H
#define FW_USE_DMA 1
#define FW_API
#ifndef STATIC
#define STATIC static
#endif
void fw_assert_failed(const char* file, int line);
#define FW_ASSERT(x) do { if (!(x)) { fw_assert_failed(__FILE__, __LINE__); } } while (0)
#endif
