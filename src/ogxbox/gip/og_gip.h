/* SPDX-License-Identifier: GPL-3.0-or-later */
/*
 * og_gip.h -- the wired Xbox One -> OG Xbox input adapter.
 *
 * Thin, reusable glue between AmpJack's core/gip.c GIP parser and an original
 * Xbox: one wired GIP controller per port, no security handshake (on a cable a
 * GIP pad reports input once powered on, as Linux's xpad has always driven it),
 * no audio, no headset (enable_audio/send_audio stay NULL, so GIP client 1 is
 * ignored by gip_rx). Input is re-published as a fixed 18-byte og_gamepad
 * snapshot; every packet the core decides to send (power on, LED, rumble,
 * identify requests, acknowledge) lands in a bounded ring for the USB backend
 * to drain. Time is injected: the adapter owns no clock of its own.
 *
 * ---- portability / thread-ownership contract ---------------------------------
 *
 * The adapter itself is PLATFORM-NEUTRAL: it depends only on the injected clock
 * (og_gip_clock_set) and on a host malloc/calloc/free for core/gip.c's chunk
 * buffers. It provides NO locking and makes NO lock-free claims.
 *
 *  * Single owner thread (the console/driver thread) must call og_gip_init,
 *    og_gip_rx, og_gip_poll, og_gip_unplug, og_gip_reset and og_gip_deinit, and
 *    install the clock. The gip_ops callbacks (ready / input / gone) fire
 *    SYNCHRONOUSLY from that same thread inside og_gip_rx / og_gip_poll, so a
 *    callback must not call back into the adapter (no re-entrancy).
 *  * The outgoing queue has one producer (the GIP core's transport .send, i.e.
 *    og_tx_send, invoked from within og_gip_rx / og_gip_poll) and one consumer
 *    (og_gip_tx_drain, normally the USB OUT backend). If those run on different
 *    threads, the owner must serialize them; the adapter does not. Nothing here
 *    is lock-free.
 *
 * ---- memory bound -------------------------------------------------------------
 *
 * The adapter's own state is static and small: the 18-byte snapshot, `guide`,
 * flags, counters and the 8 x 64-byte outgoing ring. core/gip.c's chunk buffers
 * are the ONLY dynamic memory; each is malloc/calloc/free'd by core and capped
 * at core's GIP_CHUNK_BUF_MAX_LENGTH (0xffff = 65535) bytes, with the size taken
 * from the untrusted chunk_offset of an incoming CHUNK_START frame (core rejects
 * offsets > 0xffff). The adapter does NOT impose a smaller cap -- reducing it
 * would duplicate core's framing logic -- so the console port's allocator must
 * be able to serve up to 65535 bytes per chunk buffer (input-only: the receive
 * buffer is the one that can reach it). This is NOT a static bound on parser
 * memory; it is a hard, core-enforced cap and the port must supply a bounded
 * allocator. If you need less, cap your allocator: core turns an allocation
 * failure into -XA_ENOMEM and logs it.
 *
 * ---- disconnect / outgoing-error semantics -------------------------------------
 *
 *  * og_tx_send (the transport .send): 0 = accepted; a negative XA code =
 *    refused. A full queue is backpressure: the NEW packet is dropped and
 *    counted in tx_dropped, the already-queued packets are left intact, and
 *    -XA_ENOSPC is returned so core sees the failure (e.g. it will NOT publish
 *    ready after dropping a power-on). len <= 0 / > OG_GIP_TX_PKT and a NULL
 *    data pointer are rejected (-XA_EINVAL / -XA_ENOSPC), never truncated.
 *    core/gip.c does NOT itself retry a refused send; the console port must
 *    drain the queue promptly (og_gip_tx_drain) for init/ack to reach the pad,
 *    and re-plug/reset is the only recovery once core's state machine has
 *    passed the start point.
 *  * og_gip_tx_drain: 0 = empty queue; a positive length when a packet is
 *    popped; -XA_ENOSPC when the packet does not fit in `max` (the packet stays
 *    queued, retry with a larger buffer); -XA_EINVAL on a NULL port/buffer or a
 *    negative `max`. Nothing is ever truncated.
 *  * Unplug / deinit / reset / gone (controller turned off) all clear the
 *    published snapshot, `guide` and any queued reports, so a consumer can never
 *    read a stale button state as live input.
 *
 * ---- ready vs snapshot_valid ----------------------------------------------------
 *
 * `ready` is POWERED-READY: core/gip.c's ops->ready (fired from start_gamepad
 * once power/LED/rumble are enqueued for a no_auth wired pad). It does NOT mean
 * user input has arrived -- between ready and the first report the snapshot is
 * still the zeroed boot state. A consumer wanting "real input seen" must read
 * `snapshot_valid` (set on the first input report, cleared on gone/unplug/
 * deinit/reset) instead of treating ready as an input snapshot.
 */
#pragma once

#include "../../core/gip.h"
#include "og_gamepad.h"

/* one USB interrupt IN is up to 64 bytes on every GIP pad xwired/user driver
 * sees; OG_GIP_RX_MAX is the adapter's per-call BUFFER limit (headroom for a
 * coalesced second 64-byte transfer or one large chunk), NOT the physical
 * endpoint max, and NOT a bound on core/gip.c's chunk reassembly (that is
 * GIP_CHUNK_BUF_MAX_LENGTH in core/gip.c). Do not shrink it without evidence a
 * valid parser transaction needs less: chunk reassembly already covers payloads
 * a single 64-byte interrupt IN cannot carry. */
#define OG_GIP_RX_MAX 128
/* the outgoing queue: init/ack/control packets fit comfortably in 64 bytes */
#define OG_GIP_TX_PKT 64
#define OG_GIP_TX_SLOTS 8

struct og_gip_port {
	struct gip_client *gc;      /* owned by core/gip.c; freed by us */
	struct og_gamepad gamepad;  /* fixed 18-byte snapshot (og_gamepad.h) */
	bool guide;                 /* the Xbox/Guide press; not in XINPUT_GAMEPAD */
	bool ready;                 /* powered-ready (ops->ready fired), NOT input-seen */
	bool snapshot_valid;        /* a real input frame has populated `gamepad` */
	bool plugged;               /* USB present; cleared by og_gip_unplug */
	u32 seq;                    /* +1 per input report, for consumers (monotonic) */
	u32 input_reports;
	u32 unknown_cmds;           /* command byte outside the GIP set (still parsed) */
	u32 bad_packets;            /* len < 3 or > OG_GIP_RX_MAX at the boundary */

	/* bounded outgoing queue: init/ack/control packets -> the USB backend */
	u8  tx[OG_GIP_TX_SLOTS][OG_GIP_TX_PKT];
	u8  tx_len[OG_GIP_TX_SLOTS];
	u32 tx_head, tx_tail, tx_dropped;
};

/* timestamp injection: the adapter's clock is whatever the port installs */
void og_gip_clock_set(u64 (*now_ms)(void));
u64  og_gip_now_ms(void);

/* create/free the wired client; returns 0 or a negative XA code. On failure the
 * port is left fully zeroed (not plugged). deinit is idempotent and safe on NULL. */
int  og_gip_init(struct og_gip_port *p);
void og_gip_deinit(struct og_gip_port *p);

/* the GIP core's transport .send (see the contract above); also directly usable
 * by tests to exercise backpressure and ring wrapping */
int  og_tx_send(void *ctx, const u8 *data, int len);

/* one USB interrupt IN buffer (already collected by the platform); NULL data or
 * port is a safe no-op; out-of-range len is counted in bad_packets and dropped */
void og_gip_rx(struct og_gip_port *p, const u8 *data, int len);
/* call every few ms: wired start-fallback and rumble pacing (gip_poll) */
void og_gip_poll(struct og_gip_port *p);

/* hot unplug: clear the snapshot and refuse outgoing traffic */
void og_gip_unplug(struct og_gip_port *p);
/* unplug + free + fresh client (a new plug or a host-side reset) */
void og_gip_reset(struct og_gip_port *p);

/* pop the oldest queued packet; returns its length (> 0) on success, 0 = empty,
 * -XA_ENOSPC when it does not fit in `max` (packet left queued), -XA_EINVAL on a
 * NULL port/out or a negative `max`. Never truncates. */
int  og_gip_tx_drain(struct og_gip_port *p, u8 *out, int max);
