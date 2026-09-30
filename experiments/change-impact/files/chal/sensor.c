#include "hal.h"
int sensor_get(int reg) { return hal_read(reg) / 2; }
