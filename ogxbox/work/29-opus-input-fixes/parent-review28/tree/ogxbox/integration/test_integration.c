/* SPDX-License-Identifier: GPL-3.0-or-later */
/*
 * test_integration.c -- drives the ACTUAL production path, not synthetic stand-ins:
 *
 *   real core/gip.c parser -> og_gip adapter (hardened snapshot) -> ogx_present
 *
 * It also exercises the NATIVE/original chain path with a real connected mask,
 * virtual insertion/removal edge detection, original+virtual coexistence,
 * ports 0..3, invalid/stale handles, unknown-device-type pass-through, caps
 * zero-fill, and the exact GIP-frame -> served XINPUT_STATE button bytes.
 *
 * Every GIP frame here is SYNTHETIC and labelled as such; the "USB attached"
 * signal is the ONE missing production input and is driven explicitly via
 * ctx.attached_mask (in production only the transport backend sets it). No
 * hardware claim is made.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stddef.h>

#include "../../core/compat.h"
#include "../gip/og_gip.h"
#include "../gip/og_host_platform.h"
#include "../halo2/xinput_model.h"
#include "ogx_present.h"

static int g_fail;

#define CHECK(cond, msg) do { \
	if (!(cond)) { printf("FAIL: %s\n", msg); g_fail++; } \
	else         { printf("ok:   %s\n", msg); } \
} while (0)

/* ---- injected clock ---------------------------------------------------------- */
static u64 g_now;
static u64 fake_now(void) { return g_now; }

/* ---- synthetic GIP frames (LABELLED synthetic; not USB captures) ------------- */
static int frame(u8 *out, u8 cmd, u8 options, u8 seq, const u8 *payload, u32 plen)
{
	int n = 0; u32 v = plen;
	out[n++] = cmd; out[n++] = options; out[n++] = seq;
	do { u8 byte = v & 0x7f; v >>= 7; if (v) byte |= 0x80; out[n++] = byte; } while (v);
	if (payload && plen) memcpy(out + n, payload, plen);
	return n + (int)plen;
}

static void ann_payload(u8 *a)
{
	memset(a, 0, 28);
	a[8] = 0x5e; a[9] = 0x04; a[10] = 0x12; a[11] = 0x0b;
}

static void identify_payload(u8 *id)
{
	int i;
	memset(id, 0, 64);
	id[26] = 16; id[27] = 0; id[32] = 1; id[33] = 26; id[34] = 0;
	for (i = 0; i < 26; i++) id[35 + i] = (u8)"Windows.Xbox.Input.Gamepad"[i];
}

static void input_payload(u8 *p, u16 buttons, u16 lt, u16 rt,
			  s16 lx, s16 ly, s16 rx, s16 ry)
{
	put_le16(p + 0, buttons); put_le16(p + 2, lt); put_le16(p + 4, rt);
	put_le16(p + 6, (u16)lx); put_le16(p + 8, (u16)ly);
	put_le16(p + 10, (u16)rx); put_le16(p + 12, (u16)ry);
}

/* power one port to ready: announce -> identify (no USB, so attached is faked by
 * the caller setting ctx->attached_mask, as the transport would) */
static void bring_port_ready(struct og_gip_port *p)
{
	u8 b[128], pld[64]; int n;
	og_gip_rx(p, NULL, 0); /* sanity no-op */
	ann_payload(pld);
	n = frame(b, 0x02, 0x20, 1, pld, 28); og_gip_rx(p, b, n);
	identify_payload(pld);
	n = frame(b, 0x04, 0x20, 2, pld, 64); og_gip_rx(p, b, n);
}

/* ---- native (real-driver) emulation: a distinct, connected OG-pad stand-in -- */
static uint32_t g_nat_mask, g_nat_prev;
#define NAT_HANDLE(p) ((uintptr_t)(0x80000000u + (p)))

static uint32_t OGX_STDCALL nat_devchanges(uintptr_t dt, uint32_t *ins, uint32_t *rem)
{
	(void)dt;
	*ins = g_nat_mask & ~g_nat_prev;
	*rem = g_nat_prev & ~g_nat_mask;
	g_nat_prev = g_nat_mask;
	return (*ins || *rem) ? 1 : 0;
}
static uintptr_t OGX_STDCALL nat_open(uintptr_t dt, uint32_t port, uint32_t slot, uintptr_t poll)
{
	(void)dt; (void)slot; (void)poll;
	if (port >= OGX_MAX_PORTS) return 0;
	return (g_nat_mask & (1u << port)) ? NAT_HANDLE(port) : 0;
}
static void OGX_STDCALL nat_close(uintptr_t h) { (void)h; }
static uint32_t OGX_STDCALL nat_caps(uintptr_t h, uintptr_t caps)
{
	ogx_capabilities_t *c = (ogx_capabilities_t *)caps;
	(void)h;
	if (!c) return OGX_ERR_INVALID_PARAM;
	ogx_fill_gamepad_caps(c);
	return OGX_ERR_SUCCESS;
}
static uint32_t OGX_STDCALL nat_getstate(uintptr_t h, uintptr_t state)
{
	ogx_state_t *s = (ogx_state_t *)state;
	uint32_t p = (uint32_t)(h - 0x80000000u);
	if (!s) return OGX_ERR_INVALID_PARAM;
	if (h < 0x80000000u || p >= OGX_MAX_PORTS || !(g_nat_mask & (1u << p)))
		return OGX_ERR_NOT_CONNECTED;
	memset(s, 0, sizeof(*s));
	s->dwPacketNumber = 100 + p;
	s->Gamepad.wButtons = (uint16_t)(XG_DPAD_UP << p);
	return OGX_ERR_SUCCESS;
}
static uint32_t OGX_STDCALL nat_setstate(uintptr_t h, uintptr_t fb)
{ (void)h; (void)fb; return OGX_ERR_SUCCESS; }

static void wire_ctx(struct ogx_host_ctx *ctx)
{
	memset(ctx, 0, sizeof(*ctx));
	ctx->xdevice_type_gamepad = 0x4127D8u;   /* the gamepad table ptr (stub) */
	ctx->orig_XGetDeviceChanges     = nat_devchanges;
	ctx->orig_XInputOpen            = nat_open;
	ctx->orig_XInputClose           = nat_close;
	ctx->orig_XInputGetCapabilities = nat_caps;
	ctx->orig_XInputGetState        = nat_getstate;
	ctx->orig_XInputSetState        = nat_setstate;
}

/* ====================================================================== */

static void test_caps_zero_fill(void)
{
	ogx_capabilities_t c;
	memset(&c, 0xCC, sizeof(c));
	ogx_fill_gamepad_caps(&c);
	CHECK(c.SubType == OGX_DEVSUBTYPE_GAMEPAD, "caps: SubType = gamepad (1)");
	CHECK(c.Reserved == 0, "caps: Reserved zeroed");
	CHECK(c.Vibration.wLeftMotorSpeed == 0 && c.Vibration.wRightMotorSpeed == 0,
	      "caps: rumble NOT claimed (0, no motors this milestone)");
	{
		uint8_t *raw = (uint8_t *)&c;
		int poison = 0;
		for (int i = 0; i < (int)sizeof(c); i++) if (raw[i] == 0xCC) poison++;
		CHECK(poison == 0, "caps: every byte written (no 0xCC poison left)");
	}
}

static void test_gip_to_served_state(void)
{
	struct og_gip_port port;
	struct ogx_host_ctx ctx;
	u8 b[128], pld[64];
	int n;
	uintptr_t h;
	ogx_state_t served;

	printf("scenario: real GIP frames -> served XINPUT_STATE bytes\n");
	wire_ctx(&ctx);
	og_gip_init(&port);
	ctx.ports[0] = &port;
	ctx.attached_mask |= 1u;          /* SIMULATED transport "physically attached" */

	bring_port_ready(&port);
	CHECK(port.ready, "parser: powered-ready after identify");
	CHECK(ogx_port_present(&ctx, 0), "present = attached && ready");

	/* open a virtual handle on port 0 */
	{
		uint32_t ins = 0, rem = 0;
		ogx_XGetDeviceChanges(&ctx, ctx.xdevice_type_gamepad, &ins, &rem);
		CHECK((ins & 1u) && !(rem & 1u), "insertion edge raised, no removal");
	}
	h = ogx_XInputOpen(&ctx, ctx.xdevice_type_gamepad, 0, 0, 0);
	CHECK(h != 0, "open: synthetic handle returned");
	{
		ogx_capabilities_t caps;
		memset(&caps, 0xEE, sizeof(caps));
		CHECK(ogx_XInputGetCapabilities(&ctx, h, (uintptr_t)&caps) == OGX_ERR_SUCCESS &&
		      caps.SubType == OGX_DEVSUBTYPE_GAMEPAD &&
		      caps.Vibration.wLeftMotorSpeed == 0,
		      "caps via handle: gamepad, rumble not claimed");
	}

	/* first input: A + LB + Start + LT=1023 sticks nonzero */
	input_payload(pld, GIP_GP_BTN_A | GIP_GP_BTN_BUMPER_L | GIP_GP_BTN_MENU,
	              1023, 0, -1234, 20000, -3, 100);
	n = frame(b, 0x20, 0x00, 3, pld, 14);
	og_gip_rx(&port, b, n);
	CHECK(port.snapshot_valid, "parser: snapshot valid after input");

	memset(&served, 0xCC, sizeof(served));
	CHECK(ogx_XInputGetState(&ctx, h, (uintptr_t)&served) == OGX_ERR_SUCCESS,
	      "state: success");
	CHECK(served.dwPacketNumber == 1, "state: monotonic packet = 1");
	CHECK(served.Gamepad.bAnalogButtons[XG_AB_A] == 0xFF, "state: A -> analog A = 0xFF");
	CHECK(served.Gamepad.bAnalogButtons[XG_AB_BLACK] == 0xFF, "state: LB -> Black = 0xFF");
	CHECK(served.Gamepad.wButtons == XG_START, "state: Start bit set in wButtons");
	CHECK(served.Gamepad.bAnalogButtons[XG_AB_LEFT_TRIG] == 0xFF,
	      "state: LT 1023 -> 0xFF");
	CHECK(served.Gamepad.sThumbLX == -1234 && served.Gamepad.sThumbLY == 20000,
	      "state: sticks copied");

	/* second frame -> packet 2 */
	input_payload(pld, 0, 0, 0, 0, 0, 0, 0);
	n = frame(b, 0x20, 0x00, 4, pld, 14);
	og_gip_rx(&port, b, n);
	CHECK(ogx_XInputGetState(&ctx, h, (uintptr_t)&served) == OGX_ERR_SUCCESS &&
	      served.dwPacketNumber == 2 && served.Gamepad.wButtons == 0 &&
	      served.Gamepad.bAnalogButtons[XG_AB_A] == 0,
	      "state: packet 2, released buttons zeroed");

	og_gip_deinit(&port);
}

static void test_native_passthrough_and_coexist(void)
{
	struct og_gip_port port;
	struct ogx_host_ctx ctx;
	u8 pld[64];
	int n;
	u8 b[128];
	uintptr_t vh, nh;
	uint32_t ins = 0, rem = 0;
	ogx_state_t served;

	printf("scenario: native pad (port 1) + virtual pad (port 0) coexist\n");
	wire_ctx(&ctx);
	og_gip_init(&port);
	ctx.ports[0] = &port;
	g_nat_mask = (1u << 1);          /* a real pad lives on port 1 */

	/* native only, virtual not yet attached */
	ogx_XGetDeviceChanges(&ctx, ctx.xdevice_type_gamepad, &ins, &rem);
	CHECK((ins & 2u) && !(ins & 1u), "native insertion survives on port 1");

	/* native open/getstate must be CHAINED, not swallowed */
	nh = ogx_XInputOpen(&ctx, ctx.xdevice_type_gamepad, 1, 0, 0);
	CHECK(nh == NAT_HANDLE(1), "open port 1 -> native handle (chained)");
	CHECK(ogx_XInputGetState(&ctx, nh, (uintptr_t)&served) == OGX_ERR_SUCCESS &&
	      served.Gamepad.wButtons == (XG_DPAD_UP << 1),
	      "native getstate returns the real driver's state");

	/* now attach virtual on port 0 */
	ctx.attached_mask |= 1u;
	bring_port_ready(&port);
	ins = rem = 0;
	ogx_XGetDeviceChanges(&ctx, ctx.xdevice_type_gamepad, &ins, &rem);
	CHECK((ins & 1u) && (ctx.native_connected_mask & 2u),
	      "virtual insertion on port 0 while native port 1 stays connected");

	vh = ogx_XInputOpen(&ctx, ctx.xdevice_type_gamepad, 0, 0, 0);
	CHECK(vh != 0 && vh != nh, "virtual handle distinct from native handle");

	input_payload(pld, GIP_GP_BTN_A, 0, 0, 0, 0, 0, 0);
	n = frame(b, 0x20, 0x00, 3, pld, 14); og_gip_rx(&port, b, n);
	CHECK(ogx_XInputGetState(&ctx, vh, (uintptr_t)&served) == OGX_ERR_SUCCESS &&
	      served.Gamepad.bAnalogButtons[XG_AB_A] == 0xFF,
	      "virtual handle serves A=0xFF");
	CHECK(ogx_XInputGetState(&ctx, nh, (uintptr_t)&served) == OGX_ERR_SUCCESS &&
	      served.Gamepad.wButtons == (XG_DPAD_UP << 1),
	      "native handle still chains (not swallowed while virtual live)");

	og_gip_deinit(&port);
}

static void test_edge_once_and_stale_generation(void)
{
	struct og_gip_port port;
	struct ogx_host_ctx ctx;
	uint32_t ins = 0, rem = 0;
	uintptr_t h, h2;
	ogx_state_t served;

	printf("scenario: removal edge once + replug stale generation\n");
	wire_ctx(&ctx);
	og_gip_init(&port);
	ctx.ports[0] = &port;
	ctx.attached_mask |= 1u;
	bring_port_ready(&port);

	ogx_XGetDeviceChanges(&ctx, ctx.xdevice_type_gamepad, &ins, &rem);
	CHECK((ins & 1u) && ctx.insertion_edges == 1, "exactly one insertion edge");
	h = ogx_XInputOpen(&ctx, ctx.xdevice_type_gamepad, 0, 0, 0);

	/* detach: transport clears the attached bit (and would call og_gip_unplug) */
	ctx.attached_mask &= ~1u;
	ins = rem = 0;
	ogx_XGetDeviceChanges(&ctx, ctx.xdevice_type_gamepad, &ins, &rem);
	CHECK((rem & 1u) && ctx.removal_edges == 1, "exactly one removal edge");

	/* a second poll with no re-attach must NOT re-fire the removal edge */
	ins = rem = 0;
	ogx_XGetDeviceChanges(&ctx, ctx.xdevice_type_gamepad, &ins, &rem);
	CHECK(rem == 0 && ins == 0, "removal edge not re-fired on next tick");

	/* the now-stale handle reports NOT_CONNECTED, never a stale snapshot */
	CHECK(ogx_XInputGetState(&ctx, h, (uintptr_t)&served) == OGX_ERR_NOT_CONNECTED,
	      "stale handle after unplug -> ERROR_DEVICE_NOT_CONNECTED");

	/* re-plug: new generation -> new handle address; old handle stays dead */
	ctx.attached_mask |= 1u;
	bring_port_ready(&port);   /* og_gip reset was simulated; still ready path */
	ins = rem = 0;
	ogx_XGetDeviceChanges(&ctx, ctx.xdevice_type_gamepad, &ins, &rem);
	CHECK((ins & 1u) && ctx.insertion_edges == 2, "replug raises a 2nd insertion edge");
	h2 = ogx_XInputOpen(&ctx, ctx.xdevice_type_gamepad, 0, 0, 0);
	CHECK(h2 != 0 && h2 != h, "replug issues a NEW handle (different address)");
	CHECK(ogx_XInputGetState(&ctx, h, (uintptr_t)&served) == OGX_ERR_NOT_CONNECTED,
	      "old handle stays NOT_CONNECTED after replug");
	CHECK(ogx_XInputGetState(&ctx, h2, (uintptr_t)&served) == OGX_ERR_SUCCESS,
	      "new handle serves");

	og_gip_deinit(&port);
}

static void test_ports_1_4_and_invalid(void)
{
	struct og_gip_port p[4];
	struct ogx_host_ctx ctx;
	uintptr_t h[4];
	uint32_t ins = 0, rem = 0;
	ogx_state_t served;

	printf("scenario: ports 0..3 + invalid handles\n");
	wire_ctx(&ctx);
	for (int i = 0; i < 4; i++) {
		og_gip_init(&p[i]);
		ctx.ports[i] = &p[i];
		ctx.attached_mask |= (1u << i);
		bring_port_ready(&p[i]);
	}
	ogx_XGetDeviceChanges(&ctx, ctx.xdevice_type_gamepad, &ins, &rem);
	CHECK(ins == 0xF && rem == 0, "all four virtual ports insert");

	for (int i = 0; i < 4; i++) {
		h[i] = ogx_XInputOpen(&ctx, ctx.xdevice_type_gamepad, (uint32_t)i, 0, 0);
		CHECK(h[i] != 0, "port i: handle nonzero");
	}
	for (int i = 1; i < 4; i++)
		CHECK(h[i] != h[i-1], "handles pairwise distinct");

	/* invalid: a pointer outside the arena that is not a native handle */
	CHECK(ogx_XInputGetState(&ctx, (uintptr_t)0xDEADBEEF, (uintptr_t)&served)
	      == OGX_ERR_NOT_CONNECTED, "wild handle -> chained -> NOT_CONNECTED");
	CHECK(ogx_XInputGetState(&ctx, (uintptr_t)0, (uintptr_t)&served)
	      == OGX_ERR_NOT_CONNECTED, "null handle -> NOT_CONNECTED");
	/* null output on a LIVE handle -> documented INVALID_PARAM */
	CHECK(ogx_XInputGetState(&ctx, h[0], 0) == OGX_ERR_INVALID_PARAM,
	      "null output -> ERROR_INVALID_PARAM");
	CHECK(ogx_XInputGetCapabilities(&ctx, h[0], 0) == OGX_ERR_INVALID_PARAM,
	      "null caps -> ERROR_INVALID_PARAM");

	for (int i = 0; i < 4; i++)
		og_gip_deinit(&p[i]);
}

static void test_unknown_type_passthrough(void)
{
	struct og_gip_port port;
	struct ogx_host_ctx ctx;
	uint32_t ins = 0, rem = 0;

	printf("scenario: non-gamepad device type passes through untouched\n");
	wire_ctx(&ctx);
	og_gip_init(&port);
	ctx.ports[0] = &port;
	ctx.attached_mask |= 1u;
	bring_port_ready(&port);
	g_nat_mask = (1u << 1);

	/* a headset/memory-unit style type pointer (NOT the gamepad table) */
	ogx_XGetDeviceChanges(&ctx, 0x00412990u /* not the gamepad ptr */, &ins, &rem);
	CHECK((ins & 1u) == 0, "no virtual injection for non-gamepad type");
	/* native still flows through for the same (made-up) type */
	CHECK(ins == 0 || (ins & 2u) == 0, "no synthesized non-gamepad events");

	og_gip_deinit(&port);
}

/* ---- parent review regression scenarios ---------------------------------- */

/* #1: polling a memory-unit/headset (non-gamepad) dtype must NOT contaminate the
 * GAMEPAD native mask. The mask is only meaningful for gamepad ports 0..3. */
static void test_non_gamepad_dtype_mask_isolation(void)
{
	struct ogx_host_ctx ctx;
	uint32_t ins = 0, rem = 0;

	printf("scenario: non-gamepad dtype does not contaminate gamepad native mask\n");
	wire_ctx(&ctx);

	g_nat_prev = 0;
	g_nat_mask = (1u << 0);   /* a headset/memory-unit style "insert" */

	ogx_XGetDeviceChanges(&ctx, 0x00412990u /* not the gamepad ptr */, &ins, &rem);
	CHECK((ins & 1u) != 0u, "non-gamepad insert still forwarded to caller");
	CHECK(ctx.native_connected_mask == 0u,
	      "gamepad native mask UNCHANGED by non-gamepad dtype poll");

	/* a real gamepad poll must still track -> the gate is dtype-scoped */
	g_nat_prev = 0;
	g_nat_mask = (1u << 1);
	ogx_XGetDeviceChanges(&ctx, ctx.xdevice_type_gamepad, &ins, &rem);
	CHECK(ctx.native_connected_mask == (1u << 1),
	      "gamepad dtype still updates the native mask");
}

/* #2a: native owns a port while the modern pad is ready underneath. The virtual
 * device must stay suppressed, and when the native pad unplugs, the virtual
 * insertion is deferred one poll so the game closes the native handle (rem)
 * before opening the virtual one (ins) -- one clean handover, no rem+ins of the
 * same port slot in a single call. */
static void test_native_unplug_promotes_virtual(void)
{
	struct og_gip_port port;
	struct ogx_host_ctx ctx;
	uint32_t ins = 0, rem = 0;
	uintptr_t vh;

	printf("scenario: native occupies port, then unplug promotes virtual (deferred)\n");
	wire_ctx(&ctx);
	og_gip_init(&port);
	ctx.ports[0] = &port;
	ctx.attached_mask |= 1u;
	bring_port_ready(&port);

	/* a real pad arrives and owns port 0 */
	g_nat_prev = 0;
	g_nat_mask = (1u << 0);
	ogx_XGetDeviceChanges(&ctx, ctx.xdevice_type_gamepad, &ins, &rem);
	CHECK((ins & 1u) != 0u, "native insertion on port 0");
	CHECK((ctx.native_connected_mask & 1u) != 0u, "native owns port 0");

	/* virtual is ready underneath but stays suppressed while native owns */
	ins = rem = 0;
	g_nat_mask = g_nat_prev;   /* no native change this tick */
	ogx_XGetDeviceChanges(&ctx, ctx.xdevice_type_gamepad, &ins, &rem);
	CHECK((ins & 1u) == 0u, "virtual insertion SUPPRESSED while native owns port");

	/* native unplugs: virtual promotion is deferred one poll */
	g_nat_mask = 0;
	ins = rem = 0;
	ogx_XGetDeviceChanges(&ctx, ctx.xdevice_type_gamepad, &ins, &rem);
	CHECK((rem & 1u) != 0u, "native removal edge on port 0");
	CHECK((ins & 1u) == 0u, "virtual insertion DEFERRED (no ins same tick as rem)");

	/* next poll: virtual is now visible */
	ins = rem = 0;
	g_nat_mask = g_nat_prev;   /* no native change */
	ogx_XGetDeviceChanges(&ctx, ctx.xdevice_type_gamepad, &ins, &rem);
	CHECK((ins & 1u) != 0u && (rem & 1u) == 0u,
	      "virtual insertion raised on the following poll");

	vh = ogx_XInputOpen(&ctx, ctx.xdevice_type_gamepad, 0, 0, 0);
	CHECK(vh != 0, "virtual handle opens after promotion");

	og_gip_deinit(&port);
}

/* #2b: native replug while a virtual handle is live must invalidate the virtual
 * handle (it must not silently keep serving and steal the port); a fresh open
 * chains to the native driver. */
static void test_native_replug_invalidates_virtual(void)
{
	struct og_gip_port port;
	struct ogx_host_ctx ctx;
	uint32_t ins = 0, rem = 0;
	uintptr_t vh;
	ogx_state_t served;

	printf("scenario: native replug invalidates the virtual handle (no stealing)\n");
	wire_ctx(&ctx);
	og_gip_init(&port);
	ctx.ports[0] = &port;
	ctx.attached_mask |= 1u;
	bring_port_ready(&port);

	g_nat_prev = g_nat_mask = 0;
	ogx_XGetDeviceChanges(&ctx, ctx.xdevice_type_gamepad, &ins, &rem);
	CHECK((ins & 1u) != 0u, "virtual insertion (no native)");
	vh = ogx_XInputOpen(&ctx, ctx.xdevice_type_gamepad, 0, 0, 0);
	CHECK(vh != 0, "virtual handle live");

	g_nat_mask = (1u << 0);   /* a real pad plugs into port 0 */
	ins = rem = 0;
	ogx_XGetDeviceChanges(&ctx, ctx.xdevice_type_gamepad, &ins, &rem);
	CHECK((ins & 1u) != 0u, "native insertion reported");
	CHECK((rem & 1u) != 0u, "virtual removal reported on native takeover");
	CHECK((ctx.native_connected_mask & 1u) != 0u, "native owns port again");

	CHECK(ogx_XInputGetState(&ctx, vh, (uintptr_t)&served) == OGX_ERR_NOT_CONNECTED,
	      "old virtual handle NOT_CONNECTED after native replug");
	CHECK(ogx_XInputOpen(&ctx, ctx.xdevice_type_gamepad, 0, 0, 0) == NAT_HANDLE(0),
	      "open port 0 -> native handle (virtual is not stealing)");

	og_gip_deinit(&port);
}

/* #3: the handle arena must never recycle an issued object address (a stale
 * uintptr must not alias a later live object), and must fail closed at the
 * finite 16-handle budget. */
static void test_handle_arena_no_resurrection_and_exhaustion(void)
{
	struct og_gip_port port;
	struct ogx_host_ctx ctx;
	uintptr_t first, h = 0;
	ogx_state_t served;
	uint32_t ins = 0, rem = 0;

	printf("scenario: handle arena never resurrects a stale handle, fails closed\n");
	wire_ctx(&ctx);
	og_gip_init(&port);
	ctx.ports[0] = &port;
	ctx.attached_mask |= 1u;
	bring_port_ready(&port);

	ogx_XGetDeviceChanges(&ctx, ctx.xdevice_type_gamepad, &ins, &rem);
	first = ogx_XInputOpen(&ctx, ctx.xdevice_type_gamepad, 0, 0, 0);
	CHECK(first != 0, "open #1");
	ogx_XInputClose(&ctx, first);   /* its address is now a stale token */

	/* allocate (and free) the rest of the arena: a recycling cursor would wrap
	 * back onto `first`; a fail-closed allocator simply stops at capacity */
	for (uint32_t i = 1; i < OGX_HANDLE_ARENA; i++) {
		h = ogx_XInputOpen(&ctx, ctx.xdevice_type_gamepad, 0, 0, 0);
		if (h && h != first)
			ogx_XInputClose(&ctx, h);
	}

	/* arena exhausted: the 17th open must fail closed, not silently reuse */
	h = ogx_XInputOpen(&ctx, ctx.xdevice_type_gamepad, 0, 0, 0);
	CHECK(h == 0, "open after 16 issues fail-closed (finite handle budget)");

	/* the very first handle must never resurrect even under exhaustion */
	CHECK(ogx_XInputGetState(&ctx, first, (uintptr_t)&served) == OGX_ERR_NOT_CONNECTED,
	      "stale first handle never resurrects");

	og_gip_deinit(&port);
}

/* #4: XInputSetState ABI. The feedback is PXINPUT_FEEDBACK (IN OUT header +
 * Rumble), NOT a bare 4-byte vibration pointer. */
static void test_setstate_feedback_abi(void)
{
	struct og_gip_port port;
	struct ogx_host_ctx ctx;
	uintptr_t h;
	uint32_t ins = 0, rem = 0;
	ogx_input_feedback_t fb;

	printf("scenario: XInputSetState PXINPUT_FEEDBACK ABI (header, not vibration)\n");
	wire_ctx(&ctx);
	og_gip_init(&port);
	ctx.ports[0] = &port;
	ctx.attached_mask |= 1u;
	bring_port_ready(&port);

	ogx_XGetDeviceChanges(&ctx, ctx.xdevice_type_gamepad, &ins, &rem);
	h = ogx_XInputOpen(&ctx, ctx.xdevice_type_gamepad, 0, 0, 0);
	CHECK(h != 0, "handle open");

	CHECK(ogx_XInputSetState(&ctx, h, 0) == OGX_ERR_INVALID_PARAM,
	      "SetState NULL feedback -> ERROR_INVALID_PARAM");

	/* VERIFIED ABI sizes/offsets (OXDK xbox.h, packed) */
	CHECK(sizeof(ogx_input_feedback_header_t) == 66, "feedback header 66 B");
	CHECK(sizeof(ogx_input_feedback_t)         == 70, "feedback 70 B");
	CHECK(offsetof(ogx_input_feedback_header_t, dwStatus) == 0, "dwStatus @ 0");
	CHECK(offsetof(ogx_input_feedback_header_t, hEvent)   == 4, "hEvent   @ 4");
	CHECK(offsetof(ogx_input_feedback_t, Rumble)          == 66, "Rumble   @ 66");

	/* poison the whole feedback; the honest input-only path must touch only
	 * Header.dwStatus, and NEVER read the first 4 bytes as motor speeds */
	memset(&fb, 0xCC, sizeof(fb));
	fb.Header.hEvent = 0xDEADBEEFu;
	{
		uint32_t r = ogx_XInputSetState(&ctx, h, (uintptr_t)&fb);
		CHECK(r == OGX_ERR_NOT_SUPPORTED,
		      "input-only milestone -> ERROR_NOT_SUPPORTED");
		CHECK(fb.Header.dwStatus == OGX_ERR_NOT_SUPPORTED,
		      "Header.dwStatus updated to the honest completion status");
		CHECK(fb.Header.hEvent == 0xDEADBEEFu, "hEvent left untouched (no signal)");
		CHECK(fb.Rumble.wLeftMotorSpeed == 0xCCCC && fb.Rumble.wRightMotorSpeed == 0xCCCC,
		      "Rumble bytes untouched and never misread as motor values");
	}

	/* detached live handle -> NOT_CONNECTED (device presence, not stale handle) */
	ctx.attached_mask &= ~1u;
	og_gip_unplug(&port);
	CHECK(ogx_XInputSetState(&ctx, h, (uintptr_t)&fb) == OGX_ERR_NOT_CONNECTED,
	      "SetState detached -> ERROR_DEVICE_NOT_CONNECTED");

	og_gip_deinit(&port);
}

/* #5: detach must fail caps/getstate/setstate immediately, not wait for the
 * next XGetDeviceChanges poll. */
static void test_detach_fails_before_next_poll(void)
{
	struct og_gip_port port;
	struct ogx_host_ctx ctx;
	uintptr_t h;
	uint32_t ins = 0, rem = 0;
	ogx_input_feedback_t fb;

	printf("scenario: detach fails caps/getstate/setstate before the next poll\n");
	wire_ctx(&ctx);
	og_gip_init(&port);
	ctx.ports[0] = &port;
	ctx.attached_mask |= 1u;
	bring_port_ready(&port);

	ogx_XGetDeviceChanges(&ctx, ctx.xdevice_type_gamepad, &ins, &rem);
	h = ogx_XInputOpen(&ctx, ctx.xdevice_type_gamepad, 0, 0, 0);
	CHECK(h != 0, "handle open");

	/* transport clears attached (+ would og_gip_unplug) but the title has NOT
	 * polled GetDeviceChanges yet */
	ctx.attached_mask &= ~1u;
	og_gip_unplug(&port);

	{
		ogx_capabilities_t caps;
		ogx_state_t st;
		CHECK(ogx_XInputGetCapabilities(&ctx, h, (uintptr_t)&caps) == OGX_ERR_NOT_CONNECTED,
		      "caps on detached (pre-poll) -> NOT_CONNECTED");
		CHECK(ogx_XInputGetState(&ctx, h, (uintptr_t)&st) == OGX_ERR_NOT_CONNECTED,
		      "getstate on detached (pre-poll) -> NOT_CONNECTED");
		CHECK(ogx_XInputSetState(&ctx, h, (uintptr_t)&fb) == OGX_ERR_NOT_CONNECTED,
		      "setstate on detached (pre-poll) -> NOT_CONNECTED");
	}

	og_gip_deinit(&port);
}

/* #6: monotonic packet counter. A replug resets the adapter seq (first input is
 * seq == 1 again); a new handle/epoch must still advance the packet number when
 * the state changed, so the game never sees a different button under an
 * unchanged packet number. */
static void test_replug_same_seq_different_button(void)
{
	struct og_gip_port port;
	struct ogx_host_ctx ctx;
	uint32_t ins = 0, rem = 0;
	uintptr_t h;
	ogx_state_t served;
	u8 pld[64], b[128];
	int n;

	printf("scenario: replug resets seq; packet number still advances on change\n");
	wire_ctx(&ctx);
	og_gip_init(&port);
	ctx.ports[0] = &port;
	ctx.attached_mask |= 1u;
	bring_port_ready(&port);

	ogx_XGetDeviceChanges(&ctx, ctx.xdevice_type_gamepad, &ins, &rem);
	h = ogx_XInputOpen(&ctx, ctx.xdevice_type_gamepad, 0, 0, 0);

	/* session 1: one input frame, adapter seq -> 1 */
	input_payload(pld, GIP_GP_BTN_A, 0, 0, 0, 0, 0, 0);
	n = frame(b, 0x20, 0x00, 1, pld, 14);
	og_gip_rx(&port, b, n);
	memset(&served, 0xCC, sizeof(served));
	CHECK(ogx_XInputGetState(&ctx, h, (uintptr_t)&served) == OGX_ERR_SUCCESS &&
	      served.dwPacketNumber == 1 &&
	      served.Gamepad.bAnalogButtons[XG_AB_A] == 0xFF,
	      "session 1: packet 1, A pressed");

	/* unplug + replug: adapter seq resets, next input is again seq == 1 */
	ctx.attached_mask &= ~1u;
	og_gip_unplug(&port);
	ins = rem = 0;
	ogx_XGetDeviceChanges(&ctx, ctx.xdevice_type_gamepad, &ins, &rem);
	CHECK((rem & 1u) != 0u, "replug: removal edge");
	ogx_XInputClose(&ctx, h);

	ctx.attached_mask |= 1u;
	og_gip_reset(&port);
	bring_port_ready(&port);
	ins = rem = 0;
	ogx_XGetDeviceChanges(&ctx, ctx.xdevice_type_gamepad, &ins, &rem);
	CHECK((ins & 1u) != 0u, "replug: insertion edge");

	h = ogx_XInputOpen(&ctx, ctx.xdevice_type_gamepad, 0, 0, 0);
	CHECK(h != 0, "replug: new handle (new epoch)");

	/* first new input: seq == 1 again but a DIFFERENT button */
	input_payload(pld, GIP_GP_BTN_B, 0, 0, 0, 0, 0, 0);
	n = frame(b, 0x20, 0x00, 1, pld, 14);
	og_gip_rx(&port, b, n);
	memset(&served, 0xCC, sizeof(served));
	CHECK(ogx_XInputGetState(&ctx, h, (uintptr_t)&served) == OGX_ERR_SUCCESS,
	      "replug: getstate success");
	CHECK(served.dwPacketNumber == 2,
	      "replug: packet number ADVANCED despite identical adapter seq");
	CHECK(served.Gamepad.bAnalogButtons[XG_AB_B] == 0xFF &&
	      served.Gamepad.bAnalogButtons[XG_AB_A] == 0,
	      "replug: new button shown, old button cleared");

	og_gip_deinit(&port);
}

int main(void)
{
	g_now = 1000;                       /* nonzero base so the wired fallback arms */
	og_gip_clock_set(fake_now);
	og_host_rng_seed(0x12345678u);

	test_caps_zero_fill();
	test_gip_to_served_state();
	test_native_passthrough_and_coexist();
	test_edge_once_and_stale_generation();
	test_ports_1_4_and_invalid();
	test_unknown_type_passthrough();

	test_non_gamepad_dtype_mask_isolation();
	test_native_unplug_promotes_virtual();
	test_native_replug_invalidates_virtual();
	test_handle_arena_no_resurrection_and_exhaustion();
	test_setstate_feedback_abi();
	test_detach_fails_before_next_poll();
	test_replug_same_seq_different_button();

	printf("\n%s: %d failure(s)\n", g_fail == 0 ? "PASS" : "FAIL", g_fail);
	return g_fail == 0 ? 0 : 1;
}
