/* SPDX-License-Identifier: GPL-3.0-or-later */
/*
 * og_gip_hardening_test.c -- boundary / regression tests for the wired GIP
 * adapter. These are the RED tests the hardening worker added FIRST: they
 * encode the correct contract (reject-invalid-args, refuse-to-truncate,
 * backpressure-not-success, no-stale-lifecycle, saturate-don't-wrap) and are
 * run against the un-fixed adapter to record the real failures before the
 * minimal GREEN fixes land.
 *
 * Every frame here is SYNTHETIC and labelled as such; none of it is a USB
 * capture or a claim about real hardware.
 *
 *   make -C ogxbox/gip hardtest && ./ogxbox/gip/hardtest
 *   make -C ogxbox/gip hardtest_asan && ASAN_OPTIONS=detect_leaks=1 ./ogxbox/gip/hardtest_asan
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/wait.h>

#include "../../core/compat.h"
#include "og_gip.h"
#include "og_host_platform.h"

static int g_fail;

static void check(int ok, const char *what)
{
	printf("%s %s\n", ok ? "ok  " : "FAIL", what);
	if (!ok)
		g_fail = 1;
}

/* fork isolation: one hostile-API case per child, so a crash/abort is recorded
 * as a clean FAIL instead of killing the whole run. fn returns 0 = pass. */
static void check_isolated(const char *what, int (*fn)(void))
{
	pid_t pid = fork();
	int st;

	if (pid < 0) {
		check(0, what);
		return;
	}
	if (pid == 0)
		_exit(fn());
	if (waitpid(pid, &st, 0) < 0) {
		check(0, what);
		return;
	}
	check(WIFEXITED(st) && WEXITSTATUS(st) == 0, what);
}

/* ---- injected clock ------------------------------------------------------------ */

static u64 g_now;

static u64 fake_now(void)
{
	return g_now;
}

/* core/gip.c's enum gip_option values (not exported via gip.h) */
#define OPT_INTERNAL    0x20
#define OPT_CHUNK_START 0x40
#define OPT_CHUNK       0x80

/* ---- synthetic GIP frames ------------------------------------------------------ */

static int frame(u8 *out, u8 cmd, u8 options, u8 seq, const u8 *payload, u32 plen)
{
	int n = 0;
	u32 v = plen;

	out[n++] = cmd;
	out[n++] = options;
	out[n++] = seq;
	do {
		u8 byte = v & 0x7f;

		v >>= 7;
		if (v)
			byte |= 0x80;
		out[n++] = byte;
	} while (v);
	if (payload && plen)
		memcpy(out + n, payload, plen);
	return n + (int)plen;
}

/* the first chunk of a chunked packet: chunk_offset carries the total length
 * (as core/gip.c's send_pkt sets it), packet_length carries this chunk's size */
static int chunk_start_frame(u8 *out, u8 cmd, u8 seq, u32 total)
{
	int n = 0;
	u32 v;

	out[n++] = cmd;
	out[n++] = OPT_INTERNAL | OPT_CHUNK_START | OPT_CHUNK;
	out[n++] = seq;
	out[n++] = 0x02;            /* varint packet_length = 2 */
	v = total;
	do {
		u8 byte = v & 0x7f;

		v >>= 7;
		if (v)
			byte |= 0x80;
		out[n++] = byte;
	} while (v);
	out[n++] = 0xaa;            /* 2 payload bytes */
	out[n++] = 0xbb;
	return n;
}

static void ann_payload(u8 *a)
{
	memset(a, 0, 28);
	a[8] = 0x5e, a[9] = 0x04;   /* vid 0x045e */
	a[10] = 0x12, a[11] = 0x0b; /* pid 0x0b12 */
}

static void identify_payload(u8 *id)
{
	int i = 0;

	memset(id, 0, 64);
	id[26] = 16, id[27] = 0;   /* classes at base offset 16 -> data[32] */
	id[32] = 1;                /* one class */
	id[33] = 26, id[34] = 0;   /* 26 bytes */
	for (; i < 26; i++)
		id[35 + i] = (u8)"Windows.Xbox.Input.Gamepad"[i];
}

static void input_payload(u8 *p, u16 buttons, u16 lt, u16 rt,
			  s16 lx, s16 ly, s16 rx, s16 ry)
{
	put_le16(p + 0, buttons);
	put_le16(p + 2, lt);
	put_le16(p + 4, rt);
	put_le16(p + 6, (u16)lx);
	put_le16(p + 8, (u16)ly);
	put_le16(p + 10, (u16)rx);
	put_le16(p + 12, (u16)ry);
}

/* ---- hostile-API children (run isolated) ---------------------------------------- */

static int child_drain_negative_max(void)
{
	struct og_gip_port port;
	u8 b[128], pld[28], out[16];
	int n;

	og_gip_init(&port);
	ann_payload(pld);
	n = frame(b, 0x02, 0x20, 1, pld, 28);
	og_gip_rx(&port, b, n);
	n = og_gip_tx_drain(&port, out, -1);
	og_gip_deinit(&port);
	return n == -XA_EINVAL ? 0 : 1;
}

static int child_drain_null_out(void)
{
	struct og_gip_port port;
	u8 b[128], pld[28];
	int n;

	og_gip_init(&port);
	ann_payload(pld);
	n = frame(b, 0x02, 0x20, 1, pld, 28);
	og_gip_rx(&port, b, n);
	n = og_gip_tx_drain(&port, NULL, 64);
	og_gip_deinit(&port);
	return n == -XA_EINVAL ? 0 : 1;
}

static int child_drain_null_port(void)
{
	u8 *dummy = (u8 *)"x";
	int n = og_gip_tx_drain(NULL, dummy, 4);

	(void)dummy;
	return n == -XA_EINVAL ? 0 : 1;
}

static int child_rx_null_data(void)
{
	struct og_gip_port port;

	og_gip_init(&port);
	og_gip_rx(&port, NULL, 4);
	og_gip_deinit(&port);
	return 0;
}

static int child_deinit_null(void)
{
	og_gip_deinit(NULL);
	return 0;
}

/* ---- scenarios ------------------------------------------------------------------ */

static void test_trigger_saturation(void)
{
	/* required values plus two extras that clearly wrap the old u8 narrowing */
	static const u16 in[8]   = { 0, 1, 511, 1023, 1024, 65535, 1028, 4095 };
	static const u8  want[8] = { 0, 0, 127, 255, 255, 255, 255, 255 };

	printf("scenario: trigger saturation before 0..255 scale\n");
	for (int i = 0; i < 8; i++) {
		struct gip_gamepad_state s;
		struct og_gamepad g;
		char what[64];

		memset(&s, 0, sizeof(s));
		s.trigger_left = in[i];
		s.trigger_right = in[i];
		og_gamepad_from_gip(&g, &s);
		snprintf(what, sizeof(what), "trigger %u -> L %u / R %u",
			 in[i], want[i], want[i]);
		check(g.analog[OG_AB_LTRIG] == want[i] &&
		      g.analog[OG_AB_RTRIG] == want[i], what);
	}
}

static void test_individual_bumpers(void)
{
	struct gip_gamepad_state s;
	struct og_gamepad g;

	printf("scenario: individual LB / RB mapping (swapped-mapping detection)\n");

	memset(&s, 0, sizeof(s));
	s.buttons = GIP_GP_BTN_BUMPER_L;
	og_gamepad_from_gip(&g, &s);
	check(g.analog[OG_AB_BLACK] == OG_BTN_PRESSED, "LB only -> Black pressed");
	check(g.analog[OG_AB_WHITE] == OG_BTN_RELEASED, "LB only -> White released");

	memset(&s, 0, sizeof(s));
	s.buttons = GIP_GP_BTN_BUMPER_R;
	og_gamepad_from_gip(&g, &s);
	check(g.analog[OG_AB_WHITE] == OG_BTN_PRESSED, "RB only -> White pressed");
	check(g.analog[OG_AB_BLACK] == OG_BTN_RELEASED, "RB only -> Black released");
}

static void test_tx_drain_bounds(void)
{
	struct og_gip_port port;
	u8 b[128], pld[28], out[OG_GIP_TX_PKT];
	int n;

	printf("scenario: tx_drain bounds (too small / negative / null)\n");

	og_gip_init(&port);
	ann_payload(pld);
	n = frame(b, 0x02, 0x20, 1, pld, 28);
	og_gip_rx(&port, b, n);
	check(port.tx_head - port.tx_tail == 1, "one identify packet queued");

	memset(out, 0, sizeof(out));
	n = og_gip_tx_drain(&port, out, 2);
	check(n == -XA_ENOSPC, "drain(2) on a 4-byte packet -> -XA_ENOSPC");
	check(port.tx_head - port.tx_tail == 1, "too-small drain leaves the packet queued");

	n = og_gip_tx_drain(&port, out, sizeof(out));
	check(n == 4 && out[0] == 0x04, "retry at proper size drains the full packet");
	check(port.tx_head == port.tx_tail, "queue empty after the retry");
	n = og_gip_tx_drain(&port, out, sizeof(out));
	check(n == 0, "drain on an empty queue -> 0");

	og_gip_deinit(&port);

	check_isolated("drain(..., -1) -> -XA_EINVAL (no huge memcpy)", child_drain_negative_max);
	check_isolated("drain(..., NULL, 64) -> -XA_EINVAL", child_drain_null_out);
	check_isolated("drain(NULL, ...) -> -XA_EINVAL", child_drain_null_port);
}

static void test_backpressure(void)
{
	struct og_gip_port port;
	u8 b[128], pld[64], out[OG_GIP_TX_PKT];
	int n, all_ok;

	printf("scenario: TX backpressure propagates (dropped init -> not ready)\n");
	og_gip_init(&port);

	/* eight announces fill the 8-slot queue with identify requests */
	ann_payload(pld);
	for (int i = 0; i < OG_GIP_TX_SLOTS; i++) {
		n = frame(b, 0x02, 0x20, (u8)(i + 1), pld, 28);
		og_gip_rx(&port, b, n);
	}
	check(port.tx_head - port.tx_tail == OG_GIP_TX_SLOTS,
	      "8 announces fill the queue to capacity");

	/* identify as gamepad: start_gamepad's power-on cannot be enqueued */
	identify_payload(pld);
	n = frame(b, 0x04, 0x20, 9, pld, 64);
	og_gip_rx(&port, b, n);
	check(!port.ready, "power-on dropped -> NOT ready (no invented input)");
	check(port.tx_dropped >= 1, "overflow counted in tx_dropped");
	check(port.tx_head - port.tx_tail == OG_GIP_TX_SLOTS,
	      "overflow did not overwrite the queued packets");

	all_ok = 1;
	for (int i = 0; i < OG_GIP_TX_SLOTS; i++) {
		n = og_gip_tx_drain(&port, out, sizeof(out));
		all_ok &= (n == 4 && out[0] == 0x04);
	}
	check(all_ok, "all 8 queued identify requests intact after overflow");
	check(port.tx_head == port.tx_tail, "queue drains back to empty");

	og_gip_deinit(&port);
}

static void test_lifecycle(void)
{
	struct og_gip_port port;
	u8 b[128], pld[64];
	int n;

	printf("scenario: lifecycle leaves no stale ready/buttons/queued state\n");

	og_gip_init(&port);
	ann_payload(pld); n = frame(b, 0x02, 0x20, 1, pld, 28); og_gip_rx(&port, b, n);
	identify_payload(pld); n = frame(b, 0x04, 0x20, 2, pld, 64); og_gip_rx(&port, b, n);
	while (og_gip_tx_drain(&port, pld, sizeof(pld)) > 0)
		;                       /* clear the init packets */

	input_payload(pld, GIP_GP_BTN_A, 1023, 1023, -1, -2, -3, -4);
	n = frame(b, 0x20, 0x00, 3, pld, 14); og_gip_rx(&port, b, n);
	input_payload(pld, GIP_GP_BTN_B, 0, 0, 0, 0, 0, 0);
	n = frame(b, 0x20, 0x10, 4, pld, 14); og_gip_rx(&port, b, n); /* + one queued ack */
	{
		u8 vk[2] = { 1, 0x5b };
		n = frame(b, 0x07, 0x20, 5, vk, 2); og_gip_rx(&port, b, n);
	}
	check(port.ready && port.guide && port.input_reports >= 2,
	      "state built: ready + guide + input reports");
	check(port.tx_head > port.tx_tail, "state built: an ack packet is queued");

	/* deinit must clear ready, the snapshot, guide and the queued reports */
	og_gip_deinit(&port);
	check(!port.ready && !port.guide && port.gamepad.buttons == 0 &&
	      port.gamepad.analog[OG_AB_A] == 0 && port.gamepad.stick_lx == 0 &&
	      port.tx_head == port.tx_tail,
	      "deinit: no stale ready/buttons/queued reports");
	og_gip_deinit(&port);   /* idempotent */
	check(!port.ready && port.tx_head == port.tx_tail, "deinit: idempotent");

	/* reset must start a fresh session: counters and snapshot all cleared */
	og_gip_init(&port);
	ann_payload(pld); n = frame(b, 0x02, 0x20, 1, pld, 28); og_gip_rx(&port, b, n);
	identify_payload(pld); n = frame(b, 0x04, 0x20, 2, pld, 64); og_gip_rx(&port, b, n);
	while (og_gip_tx_drain(&port, pld, sizeof(pld)) > 0)
		;
	input_payload(pld, GIP_GP_BTN_X, 0, 0, 0, 0, 0, 0);
	n = frame(b, 0x20, 0x00, 3, pld, 14); og_gip_rx(&port, b, n);
	check(port.input_reports >= 1 && port.seq >= 1, "pre-built session counters nonzero");
	og_gip_reset(&port);
	check(port.plugged && port.gc != NULL, "reset: fresh plugged client");
	check(port.input_reports == 0 && port.seq == 0 && port.tx_dropped == 0 &&
	      port.unknown_cmds == 0 && port.bad_packets == 0,
	      "reset: session counters cleared");
	og_gip_deinit(&port);

	check_isolated("deinit(NULL) is a safe no-op", child_deinit_null);
}

static void test_tx_send_direct(void)
{
	struct og_gip_port port;
	u8 pkt[OG_GIP_TX_PKT];
	int n;

	printf("scenario: tx_send backpressure / wrapping / recovery\n");
	og_gip_init(&port);

	/* fill all 8 slots with distinct command tags so overwrite is detectable */
	for (int i = 0; i < OG_GIP_TX_SLOTS; i++) {
		memset(pkt, 0x40 + i, sizeof(pkt));
		pkt[0] = (u8)(0x10 + i);
		n = og_tx_send(&port, pkt, sizeof(pkt));
		check(n == 0, "send accepted within capacity");
	}
	check(port.tx_dropped == 0, "no drops while there is room");

	/* the 9th is backpressure: refused, not a silent success */
	memset(pkt, 0xEE, sizeof(pkt));
	pkt[0] = 0xEE;
	n = og_tx_send(&port, pkt, sizeof(pkt));
	check(n == -XA_ENOSPC, "full queue -> -XA_ENOSPC (not silent success)");
	check(port.tx_dropped == 1, "overflow counted once");
	check(port.tx_head == (u32)OG_GIP_TX_SLOTS && port.tx_tail == 0,
	      "overflow advanced nothing (existing packets intact)");

	/* drain 3, re-enqueue 3: the slot index wraps and reused slots stay intact */
	for (int i = 0; i < 3; i++) {
		memset(pkt, 0, sizeof(pkt));
		n = og_gip_tx_drain(&port, pkt, sizeof(pkt));
		check(n == (int)sizeof(pkt) && pkt[0] == (u8)(0x10 + i),
		      "wrapped drain returns the right packet");
	}
	{
		int ok = 1;

		for (int i = 0; i < 3; i++) {
			memset(pkt, 0xA0 + i, sizeof(pkt));
			pkt[0] = (u8)(0x20 + i);
			n = og_tx_send(&port, pkt, sizeof(pkt));
			ok &= (n == 0);
		}
		check(ok, "re-enqueue after a partial drain succeeds (ring wrapped)");
	}
	check(port.tx_head - port.tx_tail == OG_GIP_TX_SLOTS, "refilled to capacity");

	{
		int ok = 1;

		for (int i = 0; i < OG_GIP_TX_SLOTS; i++) {
			u8 want = (i < 5) ? (u8)(0x10 + 3 + i) : (u8)(0x20 + (i - 5));

			memset(pkt, 0, sizeof(pkt));
			n = og_gip_tx_drain(&port, pkt, sizeof(pkt));
			ok &= (n == (int)sizeof(pkt) && pkt[0] == want);
		}
		check(ok, "full drain after wrap returns every packet in order, uncorrupted");
	}
	check(port.tx_head == port.tx_tail, "queue empty after the full drain");

	/* recovery: after draining it accepts again */
	memset(pkt, 0x00, sizeof(pkt));
	n = og_tx_send(&port, pkt, 4);
	check(n == 0, "queue recovers after draining");
	check(port.tx_head - port.tx_tail == 1, "exactly one packet after recovery send");

	/* argument validation */
	n = og_tx_send(&port, NULL, 4);
	check(n == -XA_EINVAL, "send(NULL, 4) -> -XA_EINVAL");
	n = og_tx_send(&port, pkt, 0);
	check(n == -XA_EINVAL, "send(..., 0) -> -XA_EINVAL");
	n = og_tx_send(&port, pkt, -1);
	check(n == -XA_EINVAL, "send(..., -1) -> -XA_EINVAL");
	n = og_tx_send(&port, pkt, OG_GIP_TX_PKT + 1);
	check(n == -XA_ENOSPC, "send(..., > OG_GIP_TX_PKT) -> -XA_ENOSPC");

	og_gip_deinit(&port);
}

static void test_snapshot_valid(void)
{
	struct og_gip_port port;
	u8 b[128], pld[64];
	int n;

	printf("scenario: powered-ready vs snapshot-valid\n");
	og_gip_init(&port);
	check(!port.ready && !port.snapshot_valid, "init: neither ready nor valid");

	ann_payload(pld); n = frame(b, 0x02, 0x20, 1, pld, 28); og_gip_rx(&port, b, n);
	identify_payload(pld); n = frame(b, 0x04, 0x20, 2, pld, 64); og_gip_rx(&port, b, n);
	check(port.ready && !port.snapshot_valid,
	      "after identify: powered-ready, snapshot NOT yet valid");
	check(port.gamepad.buttons == 0 && port.gamepad.analog[OG_AB_A] == 0,
	      "snapshot is the zeroed boot state until the first input");

	input_payload(pld, GIP_GP_BTN_A, 0, 0, 0, 0, 0, 0);
	n = frame(b, 0x20, 0x00, 3, pld, 14); og_gip_rx(&port, b, n);
	check(port.snapshot_valid && port.gamepad.analog[OG_AB_A] == OG_BTN_PRESSED,
	      "first input: snapshot now valid and populated");

	{
		u8 st[4] = { 0, 0, 0, 0 };

		n = frame(b, 0x03, 0x20, 4, st, 4); og_gip_rx(&port, b, n);
	}
	check(!port.ready && !port.snapshot_valid && port.gamepad.analog[OG_AB_A] == 0,
	      "gone: ready + snapshot_valid cleared, snapshot zeroed");

	og_gip_deinit(&port);
}

static void test_malformed_frames(void)
{
	printf("scenario: malformed framing / varints (sanitizer evidence, synthetic)\n");

	check_isolated("rx(NULL, 4) is a safe no-op", child_rx_null_data);

	{
		struct og_gip_port port;
		u8 h[8];
		int n = 0;

		og_gip_init(&port);
		h[n++] = 0x20; h[n++] = 0x00; h[n++] = 1; h[n++] = 0x3c; /* len 60 */
		og_gip_rx(&port, h, n);
		check(port.bad_packets == 0, "truncated framing: handled in parser, not overread");
		og_gip_deinit(&port);
	}
	{
		struct og_gip_port port;
		u8 v[8] = { 0x20, 0x00, 1, 0xff, 0xff, 0xff, 0xff, 0x00 };

		og_gip_init(&port);
		og_gip_rx(&port, v, sizeof(v));
		check(port.bad_packets == 0, "varint continuation overflow: bounded, no OOB");
		og_gip_deinit(&port);
	}
	{
		struct og_gip_port port;
		u8 b[16];
		int n;

		og_gip_init(&port);
		n = chunk_start_frame(b, 0x04, 1, 0xffff);   /* cap: allocates */
		og_gip_rx(&port, b, n);
		n = chunk_start_frame(b, 0x04, 2, 0x10000);  /* above cap: rejected */
		og_gip_rx(&port, b, n);
		check(1, "chunk allocation honours the 0xffff cap (leak detector confirms free)");
		og_gip_deinit(&port);
	}
}

int main(int argc, char **argv)
{
	const char *dbg = argc > 1 ? argv[1] : getenv("XA_DEBUG");

	xa_debug = dbg ? atoi(dbg) : 0;
	og_gip_clock_set(fake_now);
	g_now = 1000;

	test_trigger_saturation();
	test_individual_bumpers();
	test_tx_drain_bounds();
	test_backpressure();
	test_tx_send_direct();
	test_snapshot_valid();
	test_lifecycle();
	test_malformed_frames();

	printf(g_fail ? "FAIL\n" : "all ok\n");
	return g_fail;
}
