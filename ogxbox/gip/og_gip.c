/* SPDX-License-Identifier: GPL-3.0-or-later */
/*
 * og_gip.c -- wired Xbox One -> OG Xbox input adapter (see og_gip.h).
 *
 * Everything here stays host/platform-neutral: the only platform symbol the
 * adapter owns is xa_now_ms(), which forwards to the injected clock, so the real
 * console port can point it at the kernel time base without touching this file.
 *
 * Memory is bounded and static for the adapter itself (see og_gip.h): one struct
 * og_gip_port holds the 18-byte snapshot, the 8 x 64-byte outgoing ring and the
 * counters. core/gip.c's own malloc/calloc/free (the chunk buffers, up to its
 * GIP_CHUNK_BUF_MAX_LENGTH = 0xffff each) are the only dynamic memory and are
 * exactly what Linux's xpad path allocates too; the console port supplies a
 * bounded allocator for them (see README.md).
 */
#include <stdlib.h>
#include <string.h>

#include "og_gip.h"

/* ---- injected clock ---------------------------------------------------------- */

static u64 (*g_now_ms)(void);

void og_gip_clock_set(u64 (*now_ms)(void))
{
	g_now_ms = now_ms;
}

u64 og_gip_now_ms(void)
{
	return g_now_ms ? g_now_ms() : 0;
}

/* core/gip.c and mt76/dongle time themselves with this; the adapter owns it */
u64 xa_now_ms(void)
{
	return og_gip_now_ms();
}

/* ---- wired transport: outgoing init/ack/control queue ------------------------- */

/* the GIP command set core/gip.c decodes (enum gip_command, plus audio 0x08/0x60).
 * Anything else is counted as unknown but still handed to the parser, which is
 * authoritative (it ignores commands it doesn't know). */
static bool cmd_known(u8 c)
{
	switch (c) {
	case 0x01: case 0x02: case 0x03: case 0x04: case 0x05:
	case 0x06: case 0x07: case 0x08: case 0x09: case 0x0a:
	case 0x20: case 0x60:
		return true;
	}
	return false;
}

/* the GIP core's transport .send. 0 = accepted; negative XA = refused, so core
 * sees the failure (e.g. it will not publish ready after a dropped power-on).
 * A full queue is backpressure: drop-and-count the NEW packet, leave the
 * already-queued ones intact. core/gip.c does not retry a refused send itself. */
int og_tx_send(void *ctx, const u8 *data, int len)
{
	struct og_gip_port *p = ctx;
	u32 s;

	if (!p)
		return -XA_EINVAL;
	if (!p->plugged)
		return -XA_ENODEV;
	if (!data || len <= 0)
		return -XA_EINVAL;
	if (len > OG_GIP_TX_PKT)
		return -XA_ENOSPC;
	if (p->tx_head - p->tx_tail >= OG_GIP_TX_SLOTS) {
		p->tx_dropped++;
		return -XA_ENOSPC;
	}
	s = p->tx_head % OG_GIP_TX_SLOTS;
	memcpy(p->tx[s], data, (size_t)len);
	p->tx_len[s] = (u8)len;
	p->tx_head++;
	return 0;
}

/* ---- gip_ops: publish the fixed-size snapshot ---------------------------------- */

static void og_ready(struct gip_client *gc)
{
	struct og_gip_port *p = gc->user;

	/* powered-ready: the pad is on and input is expected. The snapshot is NOT yet
	 * valid -- see og_gip.h (ready vs snapshot_valid). */
	p->ready = true;
}

static void og_input(struct gip_client *gc, const struct gip_gamepad_state *s)
{
	struct og_gip_port *p = gc->user;

	og_gamepad_from_gip(&p->gamepad, s);
	p->guide = s->guide;
	p->snapshot_valid = true;
	p->seq++;
	p->input_reports++;
}

static void og_gone(struct gip_client *gc)
{
	struct og_gip_port *p = gc->user;

	/* turned off (status disconnected): gip.c forgot the session, we clear the
	 * snapshot. The cable is still there: gip.c will re-announce on the next one.
	 * seq/input_reports are kept monotonic so a consumer tracking "last seq"
	 * still notices the next change. */
	p->ready = false;
	p->guide = false;
	p->snapshot_valid = false;
	memset(&p->gamepad, 0, sizeof(p->gamepad));
}

static const struct gip_ops og_ops = {
	.ready = og_ready,
	.input = og_input,
	.gone = og_gone,
};

/* no_auth + wired: input flows once the pad is powered on; no key exchange.
 * enable_audio/send_audio NULL: the jack headset (GIP client 1) is out of scope. */
static const struct gip_transport og_transport = {
	.send = og_tx_send,
	.set_key = NULL,
	.no_auth = true,
	.wired = true,
};

/* ---- lifecycle ------------------------------------------------------------------ */

int og_gip_init(struct og_gip_port *p)
{
	if (!p)
		return -XA_EINVAL;
	memset(p, 0, sizeof(*p));
	p->gc = gip_client_new_transport(&og_transport, p, 0, &og_ops, p);
	if (!p->gc)
		return -XA_ENOMEM; /* p stays fully zeroed: not plugged, no client */
	p->plugged = true;
	return 0;
}

void og_gip_deinit(struct og_gip_port *p)
{
	if (!p)
		return;
	if (p->gc) {
		gip_client_free(p->gc);
		p->gc = NULL;
	}
	/* leave nothing a consumer could mistake for live state */
	p->plugged = false;
	p->ready = false;
	p->guide = false;
	p->snapshot_valid = false;
	memset(&p->gamepad, 0, sizeof(p->gamepad));
	p->tx_head = p->tx_tail = 0;
}

void og_gip_rx(struct og_gip_port *p, const u8 *data, int len)
{
	if (!p || !data || !p->gc || !p->plugged)
		return;
	/* explicit length limits at the adapter boundary: gip_rx's framing needs at
	 * least a 3-byte header, and a single interrupt IN never exceeds 128 here */
	if (len < 3 || len > OG_GIP_RX_MAX) {
		p->bad_packets++;
		return;
	}
	if (!cmd_known(data[0]))
		p->unknown_cmds++;
	gip_rx(p->gc, data, len);
}

void og_gip_poll(struct og_gip_port *p)
{
	if (p && p->gc && p->plugged)
		gip_poll(p->gc);
}

void og_gip_unplug(struct og_gip_port *p)
{
	if (!p)
		return;
	p->plugged = false;
	p->ready = false;
	p->guide = false;
	p->snapshot_valid = false;
	memset(&p->gamepad, 0, sizeof(p->gamepad));
	/* the device is gone: nothing pending can leave */
	p->tx_head = p->tx_tail = 0;
}

void og_gip_reset(struct og_gip_port *p)
{
	if (!p)
		return;
	og_gip_deinit(p); /* free the old client and clear all session state */
	og_gip_init(p);   /* fresh client; if it OOMs, the port stays unplugged */
}

int og_gip_tx_drain(struct og_gip_port *p, u8 *out, int max)
{
	u32 s;
	int n;

	if (!p || !out)
		return -XA_EINVAL;
	if (max < 0)
		return -XA_EINVAL;
	if (p->tx_head == p->tx_tail)
		return 0;          /* empty queue */
	s = p->tx_tail % OG_GIP_TX_SLOTS;
	n = p->tx_len[s];
	if (n > max)
		return -XA_ENOSPC; /* kept queued: this packet needs max >= n */
	memcpy(out, p->tx[s], (size_t)n);
	p->tx_tail++;
	return n;
}
