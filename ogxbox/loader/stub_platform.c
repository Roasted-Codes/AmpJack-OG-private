/* SPDX-License-Identifier: GPL-3.0-or-later */
/*
 * SYNTHETIC platform stub for the LOADER feasibility build, matching the interface
 * in core/platform.h. Every transport entry returns an error / does nothing, so a
 * module linked with this is provably inert: it cannot touch USB, timers or RNG.
 * This is NOT a USB capture or a driver backend; it only proves the portable core
 * compiles and links into the stage-2 container at this size class.
 */
#include <stdarg.h>
#include "../../core/platform.h"

int xa_debug = 0;

int xa_usb_ctrl(struct xa_usb *usb, u8 request_type, u8 request, u16 value,
                u16 index, void *data, u16 len)
{
    (void)usb; (void)request_type; (void)request; (void)value;
    (void)index; (void)data; (void)len;
    return -XA_ENODEV;
}

int xa_usb_bulk_out(struct xa_usb *usb, u8 ep, const void *data, int len)
{
    (void)usb; (void)ep; (void)data; (void)len;
    return -XA_ENODEV;
}

int xa_random(void *buf, int len)
{
    (void)buf; (void)len;
    return -XA_ENODEV; /* no RNG: the GIP security handshake cannot complete */
}

void xa_sleep_ms(unsigned int ms) { (void)ms; }

u64 xa_now_ms(void) { return 0; }

void xa_log(const char *fmt, ...)
{
    (void)fmt; /* no DbgPrint in this stub */
}
