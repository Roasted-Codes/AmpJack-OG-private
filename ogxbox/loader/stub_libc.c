/* SPDX-License-Identifier: GPL-3.0-or-later */
/*
 * Minimal freestanding libc for the LOADER feasibility build. Implements only
 * what the AmpJack portable core references: memcpy, memset, memmove, memcmp,
 * strlen, snprintf (%s %c %d %u %x %X %p %%), and a stub malloc/calloc/free/
 * realloc over a fixed arena.
 *
 * The arena bump allocator is a SYNTHETIC FIXTURE for the size probe only: a real
 * driver allocates from the title's memory with MmAllocateContiguousMemoryEx, not
 * a fixed image-resident arena. It is labelled here so the probe module is never
 * mistaken for a working driver.
 */
#include <stddef.h>
#include <stdarg.h>
#include "freestanding/string.h"
#include "freestanding/stdlib.h"
#include "freestanding/stdio.h"

void *memcpy(void *d, const void *s, size_t n)
{
    char *dp = (char *)d;
    const char *sp = (const char *)s;
    while (n--) *dp++ = *sp++;
    return d;
}

void *memmove(void *d, const void *s, size_t n)
{
    char *dp = (char *)d;
    const char *sp = (const char *)s;
    if (dp < sp) { while (n--) *dp++ = *sp++; }
    else { dp += n; sp += n; while (n--) *--dp = *--sp; }
    return d;
}

void *memset(void *d, int c, size_t n)
{
    char *dp = (char *)d;
    while (n--) *dp++ = (char)c;
    return d;
}

int memcmp(const void *a, const void *b, size_t n)
{
    const char *ap = (const char *)a, *bp = (const char *)b;
    while (n--) { if (*ap != *bp) return *ap - *bp; ap++; bp++; }
    return 0;
}

size_t strlen(const char *s)
{
    size_t n = 0;
    while (s[n]) n++;
    return n;
}

static char *emit_u(unsigned v, int base, int upper, int width, char pad, char *p)
{
    char tmp[12];
    static const char low[] = "0123456789abcdef";
    static const char up[] = "0123456789ABCDEF";
    const char *dig = upper ? up : low;
    int i = 0;
    do { tmp[i++] = dig[v % (unsigned)base]; v /= (unsigned)base; } while (v);
    while (i < width) tmp[i++] = pad;
    while (i) *p++ = tmp[--i];
    return p;
}

int snprintf(char *out, size_t cap, const char *fmt, ...)
{
    va_list ap;
    char *p = out;
    char *end = out + (cap ? cap - 1 : 0);
    va_start(ap, fmt);
    for (; *fmt && p < end; fmt++) {
        if (*fmt != '%') { *p++ = *fmt; continue; }
        fmt++;
        char pad = ' '; int width = 0;
        if (*fmt == '0') { pad = '0'; fmt++; }
        while (*fmt >= '0' && *fmt <= '9') { width = width * 10 + (*fmt - '0'); fmt++; }
        switch (*fmt) {
        case 's': { const char *s = va_arg(ap, const char *); while (*s && p < end) *p++ = *s++; break; }
        case 'c': *p++ = (char)va_arg(ap, int); break;
        case 'd': case 'i': { int v = va_arg(ap, int); if (v < 0) { *p++ = '-'; v = -v; } p = emit_u((unsigned)v, 10, 0, width, pad, p); break; }
        case 'u': p = emit_u(va_arg(ap, unsigned), 10, 0, width, pad, p); break;
        case 'x': p = emit_u(va_arg(ap, unsigned), 16, 0, width, pad, p); break;
        case 'X': p = emit_u(va_arg(ap, unsigned), 16, 1, width, pad, p); break;
        case 'p': p = emit_u(va_arg(ap, unsigned), 16, 1, 8, '0', p); break;
        case '%': *p++ = '%'; break;
        default: *p++ = '%'; *p++ = *fmt; break;
        }
    }
    va_end(ap);
    if (cap) *p = '\0';
    return (int)(p - out);
}

/* Stub heap: a fixed arena in bss. Size-probe glue only, never a real allocator. */
#define STUB_HEAP_BYTES 4096
static unsigned char stub_heap[STUB_HEAP_BYTES];
static size_t stub_used;

void *malloc(size_t n)
{
    n = (n + 3u) & ~3u;
    if (stub_used + n > STUB_HEAP_BYTES) return NULL;
    void *p = &stub_heap[stub_used];
    stub_used += n;
    return p;
}

void *calloc(size_t n, size_t sz) { void *p = malloc(n * sz); if (p) memset(p, 0, n * sz); return p; }
void *realloc(void *p, size_t n) { (void)p; (void)n; return NULL; }
void free(void *p) { (void)p; }
void abort(void) { for (;;) __asm__ volatile("hlt"); }
