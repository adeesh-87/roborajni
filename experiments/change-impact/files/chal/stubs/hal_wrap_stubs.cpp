// shared --wrap + CppUMock stub for the C function hal_read (project headers before CppUTest headers)
#include "hal.h"
#include "CppUTestExt/MockSupport.h"
extern "C" int __real_hal_read(int reg);
extern "C" int __wrap_hal_read(int reg) {
    mock("hal_read").actualCall("hal_read").withIntParameter("reg", reg);
    if (mock("hal_read").hasReturnValue()) return mock("hal_read").intReturnValue();
    return __real_hal_read(reg);
}
