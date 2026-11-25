/* SPDX-License-Identifier: GPL-3.0-or-later */
#include <stdarg.h>
#include <stdio.h>
#include <string.h>
#include <time.h>

#include "og_host_platform.h"

/* ---- platform.h symbols not owned by og_gip.c ---------------------------------- */

int xa_debug;

/* the wireless adapter's USB hooks: unused by the wired adapter, kept linkable */
int xa_usb_ctrl(struct xa_usb *usb, u8 request_type, u8 request, u16 value, u16 index,
		void *data, u16 len)
{
	(void)usb; (void)request_type; (void)request; (void)value; (void)index;
	(void)data; (void)len;
	return -XA_EIO;
}

int xa_usb_bulk_out(struct xa_usb *usb, u8 ep, const void *data, int len)
{
	(void)usb; (void)ep; (void)data; (void)len;
	return -XA_EIO;
}

void xa_sleep_ms(unsigned int ms)
{
	(void)ms;
}

/* ---- deterministic RNG (xorshift32), for the wired no-auth path it is unused --
 * the security handshake is the only consumer and is skipped. Seeded for tests. */
static u32 g_rand = 0x12345678u;

void og_host_rng_seed(u32 seed)
{
	g_rand = seed ? seed : 1u;
}

int xa_random(void *buf, int len)
{
	u8 *b = buf;

	for (int i = 0; i < len; i++) {
		g_rand ^= g_rand << 13;
		g_rand ^= g_rand >> 17;
		g_rand ^= g_rand << 5;
		b[i] = (u8)g_rand;
	}
	return 0;
}

void xa_log(const char *fmt, ...)
{
	va_list ap;

	va_start(ap, fmt);
	vfprintf(stderr, fmt, ap);
	va_end(ap);
}

u64 og_host_clock_ms(void)
{
	struct timespec ts;

	clock_gettime(CLOCK_MONOTONIC, &ts);
	return (u64)ts.tv_sec * 1000 + (u64)ts.tv_nsec / 1000000;
}
