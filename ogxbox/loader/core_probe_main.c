/* SPDX-License-Identifier: GPL-3.0-or-later */
/*
 * Core-size probe: links the real AmpJack portable GIP core (gip.c, dongle.c,
 * mt76.c, sha256.c, uECC.c) into the stage-2 container against the SYNTHETIC
 * stub platform, so the LOADER worker can state an honest, measured upper bound
 * for the driver's code/data/bss from the linker map — not a guess.
 *
 * The wired path (gip_client_new_transport, no_auth) is exercised only at link
 * level; at runtime the stub transport returns -XA_ENODEV, so this module never
 * talks to USB and is not a controller driver.
 */
#include "h2s2.h"
#include "../../core/gip.h"

static int stub_send(void *ctx, const u8 *data, int len)
{
    (void)ctx; (void)data; (void)len;
    return -XA_ENODEV;
}

static const struct gip_transport stub_transport = {
    .send = stub_send,
    .set_key = NULL,
    .no_auth = true,  /* wired: GIP security handshake is skipped */
    .wired = true,
};

int h2s2_main(struct h2s2_host *host)
{
    (void)host;
    struct gip_client *gc = gip_client_new_transport(&stub_transport, NULL, 0, NULL, NULL);
    if (gc)
        gip_poll(gc);
    return 0; /* inert: no usable transport */
}
