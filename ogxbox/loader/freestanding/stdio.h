/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Freestanding stdio.h shim (snprintf only; the core's only stdio use). */
#ifndef OGX_FREESTANDING_STDIO_H
#define OGX_FREESTANDING_STDIO_H
#include <stddef.h>
int snprintf(char *out, size_t cap, const char *fmt, ...);
#endif
