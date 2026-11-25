/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Freestanding stdlib.h shim (malloc/calloc/free/realloc; no libc). */
#ifndef OGX_FREESTANDING_STDLIB_H
#define OGX_FREESTANDING_STDLIB_H
#include <stddef.h>
void *malloc(size_t n);
void *calloc(size_t n, size_t sz);
void *realloc(void *p, size_t n);
void free(void *p);
void abort(void);
#endif
