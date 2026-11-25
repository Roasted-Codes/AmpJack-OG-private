/* SPDX-License-Identifier: GPL-3.0-or-later */
/*
 * og_gip_test.c -- exercises the ACTUAL core/gip.c parser through the og_gip
 * adapter, end to end:
 *
 *   1. announce -> gip.c asks the pad to identify itself (outgoing queue);
 *   2. identify (class "Windows.Xbox.Input.Gamepad") -> gip.c powers the pad on,
 *      lights its LED, sends the rumble-stop, and reports ready;
 *   3. an input frame -> the og_gamepad snapshot (buttons/sticks/triggers), plus
 *      its exact 18-byte packed form;
 *   4. an acknowledged input frame -> gip.c queues an ACKNOWLEDGE, then decodes;
 *   5. the virtual-key (Guide) -> the guide flag, delivered through the input path;
 *   6. status "disconnected" -> gone: snapshot cleared;
 *   7. hot unplug / reset -> outgoing traffic refused, fresh client;
 *   8. unknown command and length-limit frames -> counted, not decoded;
 *   9. a fresh port with no announce -> the wired 1500 ms start fallback (xpad
 *      style): identify request, then blind power-on.
 *
 * Every frame here is SYNTHETIC and labelled as such; none of it is a USB capture
 * or a claim about real hardware.
 *
 *   make -C ogxbox/gip test && ./ogxbox/gip/test
 *   make -C ogxbox/gip asan  && ASAN_OPTIONS=detect_leaks=1 ./ogxbox/gip/asan
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "../../core/compat.h"
#include "og_gip.h"
#include "og_host_platform.h"

static int g_fail;
static int og_tx_drain_present(struct og_gip_port *p);

static void check(int ok, const char *what)
{
	printf("%s %s\n", ok ? "ok  " : "FAIL", what);
	if (!ok) {
		g_fail = 1;
		if (xa_debug)
			fflush(stderr);
	}
}

/* ---- injected clock ------------------------------------------------------------ */

static u64 g_now;

static u64 fake_now(void)
{
	return g_now;
}

/* ---- synthetic GIP frames (LABELLED synthetic; not USB captures) --------------- */

/* one non-chunked incoming frame, LEB128 varint length as core/gip.c's
 * decode_varint reads it */
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
	/* handle_identify reads offsets relative to base = data + 16, so the classes
	 * block here sits at data[32..60] with base offset 16: */
	id[26] = 16, id[27] = 0;     /* classes at base offset 16 -> data[32] */
	id[32] = 1;                  /* one class (base[16]) */
	id[33] = 26, id[34] = 0;     /* 26 bytes (base[17..18]) */
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

/* drain one packet, print what it is */
static int expect_tx(struct og_gip_port *p, u8 want_cmd, const char *what)
{
	u8 out[OG_GIP_TX_PKT] = { 0 };
	int n = og_gip_tx_drain(p, out, sizeof(out));
	int ok = n > 0 && out[0] == want_cmd;

	if (xa_debug) {
		printf("tx[%d]:", n);
		for (int i = 0; i < n; i++)
			printf(" %02x", out[i]);
		printf("\n");
	}
	check(ok, what);
	return n;
}

/* ---- scenarios ------------------------------------------------------------------ */

static void test_announce_identify_input(void)
{
	struct og_gip_port port;
	u8 b[128], pld[64], wire[OG_GAMEPAD_WIRE];
	struct og_gamepad want;
	int n;
	static const u8 wire_want[OG_GAMEPAD_WIRE] = {
		0x11, 0x00,                    /* wButtons: START | DPAD_UP */
		0xff, 0xff, 0x00, 0x00,       /* A B X Y */
		0xff, 0xff, 0xff, 0x7f,       /* Black White LT RT (RT=127) */
		0x2e, 0xfb,                   /* lx -1234 */
		0x20, 0x4e,                   /* ly 20000 */
		0xfd, 0xff,                   /* rx -3 */
		0x64, 0x00,                   /* ry 100 */
	};

	printf("scenario: announce -> identify -> input\n");
	og_gip_init(&port);
	check(!port.ready && port.plugged && port.gc != NULL,
	      "init: wired client created, not ready");

	ann_payload(pld);
	n = frame(b, 0x02, 0x20, 1, pld, 28);          /* announce, internal, client 0 */
	og_gip_rx(&port, b, n);
	check(port.tx_head == 1, "announce: gip.c queued one reply");
	expect_tx(&port, 0x04, "  -> identify request (cmd 0x04)");
	check(!port.ready, "announce: still not ready");

	identify_payload(pld);
	n = frame(b, 0x04, 0x20, 2, pld, 64);          /* identify, internal, client 0 */
	og_gip_rx(&port, b, n);
	check(port.ready, "identify: gamepad class -> powered on, ready");
	check(port.tx_head - port.tx_tail == 3, "identify: power / LED / rumble queued");
	expect_tx(&port, 0x05, "  -> power on   (cmd 0x05)");
	expect_tx(&port, 0x0a, "  -> LED on     (cmd 0x0a)");
	expect_tx(&port, 0x09, "  -> rumble off (cmd 0x09)");

	/* A|B|LB|RB|DPAD_UP|MENU ; LT 1023, RT 511 */
	input_payload(pld,
		GIP_GP_BTN_A | GIP_GP_BTN_B | GIP_GP_BTN_BUMPER_L | GIP_GP_BTN_BUMPER_R |
		GIP_GP_BTN_DPAD_U | GIP_GP_BTN_MENU, 1023, 511, -1234, 20000, -3, 100);
	n = frame(b, 0x20, 0x00, 3, pld, 14);          /* input, not internal */
	og_gip_rx(&port, b, n);
	check(port.input_reports == 1 && port.seq == 1, "input: one report decoded");
	check(port.gamepad.buttons == (OG_GP_START | OG_GP_DPAD_UP),
	      "input: dpad/start/back/thumb bits mapped (A/B/LB/RB stay analog)");
	check(port.gamepad.analog[OG_AB_A] == 0xff && port.gamepad.analog[OG_AB_B] == 0xff &&
	      port.gamepad.analog[OG_AB_X] == 0x00 && port.gamepad.analog[OG_AB_Y] == 0x00,
	      "input: A/B analog full, X/Y released");
	check(port.gamepad.analog[OG_AB_BLACK] == 0xff && port.gamepad.analog[OG_AB_WHITE] == 0xff,
	      "input: LB/RB -> Black/White");
	check(port.gamepad.analog[OG_AB_LTRIG] == 0xff && port.gamepad.analog[OG_AB_RTRIG] == 0x7f,
	      "input: triggers 1023/511 -> 255/127");
	check(port.gamepad.stick_lx == -1234 && port.gamepad.stick_ly == 20000 &&
	      port.gamepad.stick_rx == -3 && port.gamepad.stick_ry == 100,
	      "input: sticks copied (sign preserved)");

	og_gamepad_pack(&port.gamepad, wire);
	check(!memcmp(wire, wire_want, OG_GAMEPAD_WIRE),
	      "input: 18-byte packed form byte-exact (le)");
	og_gamepad_unpack(wire, &want);
	check(!memcmp(&want, &port.gamepad, sizeof(want)),
	      "input: unpack(pack(x)) == x");

	/* acknowledged input: gip.c must queue an ACKNOWLEDGE, then still decode */
	input_payload(pld, GIP_GP_BTN_X, 0, 0, 0, 0, 0, 0);
	n = frame(b, 0x20, 0x10, 4, pld, 14);          /* input + ACK bit */
	og_gip_rx(&port, b, n);
	expect_tx(&port, 0x01, "input-ack: ACKNOWLEDGE queued (cmd 0x01)");
	check(port.input_reports == 2 &&
	      (port.gamepad.buttons == 0) && port.gamepad.analog[OG_AB_X] == 0xff,
	      "input-ack: the same frame still decoded");

	/* Guide (virtual key) */
	{
		u8 vk[2] = { 1, 0x5b };
		n = frame(b, 0x07, 0x20, 5, vk, 2);
		og_gip_rx(&port, b, n);
		check(port.guide, "guide: virtual-key press carried on the input path");
	}

	/* turned off */
	{
		u8 st[4] = { 0, 0, 0, 0 };
		n = frame(b, 0x03, 0x20, 6, st, 4);        /* status, not connected */
		og_gip_rx(&port, b, n);
	}
	check(!port.ready && !port.guide && port.gamepad.buttons == 0 &&
	      port.gamepad.analog[OG_AB_A] == 0 && port.gamepad.stick_lx == 0,
	      "status off: snapshot cleared, ready false");

	og_gip_deinit(&port);
}

static void test_unplug_reset_limits(void)
{
	struct og_gip_port port;
	u8 b[OG_GIP_RX_MAX + 16];
	int n;

	printf("scenario: unplug / reset / unknown / length limits\n");
	og_gip_init(&port);
	check(port.plugged, "init: plugged");

	/* unknown command: counted, then ignored by the parser */
	n = frame(b, 0x77, 0x20, 1, NULL, 0);
	og_gip_rx(&port, b, n);
	check(port.unknown_cmds == 1, "unknown command counted");

	/* length limits at the boundary */
	og_gip_rx(&port, b, 2);                     /* too short (< 3) */
	og_gip_rx(&port, b, OG_GIP_RX_MAX + 1);    /* too long */
	check(port.bad_packets == 2, "length limits: 2 bad packets counted");

	/* hot unplug: outgoing refused */
	og_gip_unplug(&port);
	check(!port.plugged && !port.ready, "unplug: cleared");
	check(og_tx_drain_present(&port) == 0, "unplug: nothing queued was kept");
	/* rx after unplug is a no-op */
	og_gip_rx(&port, b, 4);
	check(port.input_reports == 0, "unplug: rx is a no-op");

	/* reset: fresh client, plugged again */
	og_gip_reset(&port);
	check(port.plugged && port.gc != NULL && !port.ready &&
	      port.unknown_cmds == 0 && port.bad_packets == 0,
	      "reset: fresh client, counters cleared");

	og_gip_deinit(&port);
}

static void test_wired_fallback(void)
{
	struct og_gip_port port;

	printf("scenario: no-announce wired fallback (xpad style)\n");
	/* a real console clock is nonzero: core/gip.c's fallback uses `gc->started &&`
	 * as a guard, so at injected time 0 it never arms. Start at a nonzero base. */
	g_now = 1000;
	og_gip_init(&port);

	/* before the 1500 ms deadline nothing happens */
	og_gip_poll(&port);
	check(port.tx_head == 0 && !port.ready, "fallback: nothing before the deadline");

	/* pass the deadline: gip.c asks who it is */
	g_now = 2600;
	og_gip_poll(&port);
	expect_tx(&port, 0x04, "  -> identify request after 1500 ms");

	/* another 1500 ms with no answer: blind start as a gamepad (no_auth: ready) */
	g_now = 4200;
	og_gip_poll(&port);
	check(port.ready, "fallback: started blind, ready without an announce");
	check(port.tx_head - port.tx_tail == 3, "fallback: power / LED / rumble queued");
	expect_tx(&port, 0x05, "  -> power on   (cmd 0x05)");

	og_gip_deinit(&port);
}

/* forward decl used in test_unplug_reset_limits */
static int og_tx_drain_present(struct og_gip_port *p)
{
	u8 out[4];
	return og_gip_tx_drain(p, out, sizeof(out));
}

int main(int argc, char **argv)
{
	const char *dbg = argc > 1 ? argv[1] : getenv("XA_DEBUG");

	xa_debug = dbg ? atoi(dbg) : 0;
	og_gip_clock_set(fake_now);
	printf("og_gamepad is %u bytes, og_gip_port is %u bytes (18 + GC ptr + 8x64 TX + counters)\n",
	       (unsigned)sizeof(struct og_gamepad), (unsigned)sizeof(struct og_gip_port));

	test_announce_identify_input();
	test_unplug_reset_limits();
	test_wired_fallback();

	printf(g_fail ? "FAIL\n" : "all ok\n");
	return g_fail;
}
