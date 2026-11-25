/* SPDX-License-Identifier: GPL-3.0-or-later */
/*
 * DISABLED diagnostic container. Proves only the loader/container path: the module
 * validates the host table and returns 0. It hooks nothing, does no USB I/O, writes
 * nothing to game memory and starts no thread. This is NOT a controller driver and
 * must not be mistaken for one; it exists to demonstrate buildability of the
 * stage-2 payload format for a later real GIP/USB module.
 */
#include "h2s2.h"

int h2s2_main(struct h2s2_host *host)
{
    /* host->magic / module_base were already checked by crt0 before reaching here. */
    (void)host;
    return 0; /* 0 = loaded and inert */
}
