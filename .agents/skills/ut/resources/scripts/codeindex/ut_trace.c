/* ut_trace.c - function entry/exit recorder for `index.sh trace` (GCC/Clang -finstrument-functions).
 * Linked into the TEST binary only. Writes to $UT_TRACE_FILE:
 *   M <line of /proc/self/maps for an executable mapping>   (to turn addresses into file offsets)
 *   E <fn address> <call site address> <thread id>   function entered
 *   X <fn address> <thread id>                        function left
 * Nothing is written when UT_TRACE_FILE is not set. Linux/glibc (reads /proc/self/maps). */
#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/syscall.h>

#define NOINST __attribute__((no_instrument_function))

static FILE *ut_f;

NOINST static void ut_trace_open(void) __attribute__((constructor(101)));
NOINST static void ut_trace_open(void)
{
    const char *p = getenv("UT_TRACE_FILE");
    char line[1024];
    FILE *m;
    if (!p || !*p) return;
    ut_f = fopen(p, "w");
    if (!ut_f) return;
    setvbuf(ut_f, NULL, _IOFBF, 1 << 20);
    m = fopen("/proc/self/maps", "r");
    while (m && fgets(line, sizeof line, m)) {
        if (strstr(line, " r-xp ") || strstr(line, " r--p 00000000 ")) fprintf(ut_f, "M %s", line);
    }
    if (m) fclose(m);
}

NOINST static void ut_trace_close(void) __attribute__((destructor(101)));
NOINST static void ut_trace_close(void)
{
    if (ut_f) { fflush(ut_f); fclose(ut_f); ut_f = NULL; }
}

NOINST void __cyg_profile_func_enter(void *fn, void *site)
{
    if (ut_f) fprintf(ut_f, "E %p %p %ld\n", fn, site, (long)syscall(SYS_gettid));
}

NOINST void __cyg_profile_func_exit(void *fn, void *site)
{
    (void)site;
    if (ut_f) fprintf(ut_f, "X %p %ld\n", fn, (long)syscall(SYS_gettid));
}
