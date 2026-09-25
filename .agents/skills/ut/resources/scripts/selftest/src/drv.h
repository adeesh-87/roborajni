#ifndef DRV_H
#define DRV_H
#include <stdint.h>
#include "fw_config.h"
#ifdef __cplusplus
extern "C" {
#endif
typedef struct {
    int  (*open)(void);
    int  (*write)(const uint8_t* b, uint32_t n);
    void (*close)(void);
} drv_ops_t;
typedef struct { void (*on_error)(int code); void (*on_done)(void); } drv_events_t;
FW_API int drv_write_all(const uint8_t* b, uint32_t n);
FW_API void drv_init(void);
#ifdef __cplusplus
}
#endif
#endif
