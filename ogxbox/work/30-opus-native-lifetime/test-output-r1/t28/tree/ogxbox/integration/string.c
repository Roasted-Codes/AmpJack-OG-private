/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "freestanding/string.h"

void *memset(void *dst, int c, size_t n)
{
	unsigned char *d = dst;
	while (n--)
		*d++ = (unsigned char)c;
	return dst;
}

void *memcpy(void *dst, const void *src, size_t n)
{
	unsigned char *d = dst;
	const unsigned char *s = src;
	while (n--)
		*d++ = *s++;
	return dst;
}

int memcmp(const void *a, const void *b, size_t n)
{
	const unsigned char *x = a, *y = b;
	while (n--) {
		if (*x != *y)
			return (int)*x - (int)*y;
		x++; y++;
	}
	return 0;
}
