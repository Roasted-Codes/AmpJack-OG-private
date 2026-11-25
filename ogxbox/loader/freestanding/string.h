/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Freestanding string.h shim. clang i386-unknown-none-elf provides <stdint.h>
 * <stddef.h> <stdbool.h> <stdarg.h> as builtins, but not the libc headers; the
 * AmpJack core includes <string.h>. These prototypes let it compile against a
 * stub libc (stub_libc.c). */
#ifndef OGX_FREESTANDING_STRING_H
#define OGX_FREESTANDING_STRING_H
#include <stddef.h>
void *memcpy(void *d, const void *s, size_t n);
void *memmove(void *d, const void *s, size_t n);
void *memset(void *d, int c, size_t n);
int memcmp(const void *a, const void *b, size_t n);
size_t strlen(const char *s);
char *strcpy(char *d, const char *s);
char *strncpy(char *d, const char *s, size_t n);
int strcmp(const char *a, const char *b);
int strncmp(const char *a, const char *b, size_t n);
char *strchr(const char *s, int c);
#endif
