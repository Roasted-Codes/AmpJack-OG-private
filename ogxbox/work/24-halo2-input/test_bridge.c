/* SPDX-License-Identifier: GPL-3.0-or-later */
/*
 * test_bridge.c -- production-linked bridge test (HOST build, NOT a guest boot).
 *
 * Links the ACTUAL production files (ogx_transport.c + ogx_stub.c +
 * ogx_present.c + xinput_model.c) and drives the real gdr attach state machine
 * through a fake native USB transport (the only thing mocked, and labelled as
 * such). It exercises the game-facing export stubs (ogx_stub_xgetdevicechanges /
 * xinputopen / xinputgetstate), not a re-implementation:
 *
 *   1. missing-bindings rejection  (ogx_install_hooks refuses before any write)
 *   2. attach -> S0..S5 -> AddComplete(0) -> transport live
 *   3. interrupt-IN -> pump -> GetDeviceChanges/Open/GetState serve real input
 *   4. detach -> close chain -> RemoveComplete; stale handle NOT_CONNECTED
 *   5. reconnect -> new generation; a held button cannot survive
 *   6. native stock port passthrough via injected orig_* chain
 *
 * The fake submit/add/remove stand in ONLY for the native IUsbDevice thiscall
 * transport (which cannot run on a host). Everything else is production code.
 */
#include <stdio.h>
#include <string.h>
#include <stdint.h>
#include <stddef.h>

#include "ogx_module.h"   /* -> ogx_present.h + gipdrive.h + xinput_model.h + og_gip.h */

/* the six game-facing stubs (ogx_stub.c) */
extern uint32_t  OGX_STDCALL ogx_stub_xgetdevicechanges(uintptr_t, uint32_t *, uint32_t *);
extern uintptr_t OGX_STDCALL ogx_stub_xinputopen(uintptr_t, uint32_t, uint32_t, uintptr_t);
extern uint32_t  OGX_STDCALL ogx_stub_xinputgetstate(uintptr_t, uintptr_t);

extern void ogx_transport_init(void);
extern int  ogx_install_hooks(void);
extern void ogx_module_pump(void);
extern uint32_t ogx_module_status(void);

static int g_fail;
#define CHECK(cond, msg) do { \
	if (!(cond)) { printf("FAIL: %s\n", msg); g_fail++; } \
	else         { printf("ok:   %s\n", msg); } \
} while (0)

/* ===================== fake native USB transport (LABELLED MOCK) ============ */

static const uintptr_t DEV = 0x00005000;   /* fake IUsbDevice* under test */

/* a minimal 0xFF-interface config descriptor (WIRED 045e:0b12 shape) */
static const uint8_t cfg_desc[32] = {
	0x09, 0x02, 0x20, 0x00, 0x01, 0x01, 0x00, 0x80, 0x32,  /* config (wTotal=32) */
	0x09, 0x04, 0x00, 0x00, 0x02, 0xFF, 0x47, 0xD0, 0x00,  /* iface0, 2 ep, 0xFF */
	0x07, 0x05, 0x81, 0x03, 0x40, 0x00, 0x04,              /* EP IN  0x81 intr 64 */
	0x07, 0x05, 0x01, 0x03, 0x40, 0x00, 0x04,              /* EP OUT 0x01 intr 64 */
};

static void *g_pending[16];            /* open/ctrl/close URBs, completed by hcd_step */
static int   g_npend;
static u32   g_next_handle = 0x100;    /* fake HCD pipe handles */

static unsigned g_add_complete_calls;
static long     g_add_complete_status;
static unsigned g_remove_complete_calls;

/* the fake SubmitRequest: accept the URB; open/ctrl/close are drained by
 * hcd_step(), the persistent interrupt IN/OUT (fn 0x41) is the test's to
 * complete (via &att->in_urb / &att->tx_urb). */
static long fake_submit(void *device, void *urb)
{
	(void)device;
	gdr_urb_header *h = (gdr_urb_header *)urb;
	if (h->Function == 0x41)           /* interrupt IN/OUT: not auto-completed */
		return 0;
	if (g_npend < 16)
		g_pending[g_npend++] = urb;
	return 0;
}

static void fake_add_complete(void *device, long status)
{
	(void)device;
	g_add_complete_calls++;
	g_add_complete_status = status;
}

static void fake_remove_complete(void *device)
{
	(void)device;
	g_remove_complete_calls++;
}

/* complete ONE queued open/ctrl/close URB with HCD semantics (synchronous,
 * like a fast-emulated OHCI) */
static int hcd_step(void)
{
	gdr_urb_header *h;
	if (!g_npend) return 0;
	h = (gdr_urb_header *)g_pending[0];
	memmove(&g_pending[0], &g_pending[1], (size_t)(g_npend - 1) * sizeof(void *));
	g_npend--;
	switch (h->Function) {
	case 0x82:
	case 0x02: {                 /* OPEN_ENDPOINT -> hand back a pipe handle */
		gdr_urb_open *o = (gdr_urb_open *)h;
		o->EndpointHandle = ++g_next_handle;
		o->Hdr.Status = 0;
		break; }
	case 0x40: {                 /* control: GET_DESCRIPTOR(config) fills the buffer */
		gdr_urb_control *c = (gdr_urb_control *)h;
		if (c->SetupPacket[1] == 0x06) {   /* bRequest GET_DESCRIPTOR */
			u32 len = c->TransferLength;
			u8 *dst = (u8 *)(uintptr_t)c->TransferBuffer;
			if (dst && len)
				memcpy(dst, cfg_desc, len < sizeof(cfg_desc) ? len : sizeof(cfg_desc));
		}
		c->Hdr.Status = 0;       /* SET_CONFIGURATION (0x09) is a no-op success */
		break; }
	case 0xC3:
	case 0x43:                   /* close default / endpoint */
		h->Status = 0;
		break;
	default:
		h->Status = 0;
	}
	{
		gdr_complete_fn cb = (gdr_complete_fn)(uintptr_t)h->CompleteProc;
		cb((void *)h, (void *)(uintptr_t)h->CompleteContext);
	}
	return 1;
}

static void drain(void) { int guard = 64; while (guard-- && g_npend) hcd_step(); }

/* build a GIP input frame: command, options, seq, varint(len), payload[14] */
static int build_input(u8 *out, u16 buttons)
{
	int n = 0;
	out[n++] = 0x20; out[n++] = 0x00; out[n++] = 0x03; out[n++] = 0x0e;
	out[n++] = (u8)(buttons & 0xFF); out[n++] = (u8)(buttons >> 8);  /* wButtons */
	for (int i = 0; i < 12; i++) out[n++] = 0;                        /* lt rt + 4 sticks */
	return n;
}

/* complete the persistent interrupt-IN URB with `flen` bytes of `frame` */
static void inject_rx(const u8 *frame, int flen)
{
	struct gdr_attach_ctx *att = &ogx_g_module.att;
	gdr_urb_transfer *u = &att->in_urb;
	memcpy(att->rx_buf, frame, (size_t)flen);
	u->TransferLength = (u32)flen;
	u->Hdr.Status = 0;
	{
		gdr_complete_fn cb = (gdr_complete_fn)(uintptr_t)u->Hdr.CompleteProc;
		cb((void *)u, (void *)(uintptr_t)u->Hdr.CompleteContext);
	}
}

/* ---- native passthrough fakes (stand in for the title XID driver) ---- */
static uint32_t g_nat_mask;
static uintptr_t NAT_HANDLE = 0x80008000u;
static uint32_t OGX_STDCALL nat_devchanges(uintptr_t dt, uint32_t *ins, uint32_t *rem)
{
	(void)dt; *ins = g_nat_mask; *rem = 0; return g_nat_mask ? 1 : 0;
}
static uintptr_t OGX_STDCALL nat_open(uintptr_t dt, uint32_t p, uint32_t s, uintptr_t pl)
{ (void)dt; (void)s; (void)pl; return (g_nat_mask & (1u << p)) ? NAT_HANDLE : 0; }

static void wire_host(void)
{
	ogx_g_module.host.submit_request    = (u32)(uintptr_t)fake_submit;
	ogx_g_module.host.add_complete      = (u32)(uintptr_t)fake_add_complete;
	ogx_g_module.host.remove_complete   = (u32)(uintptr_t)fake_remove_complete;
	ogx_g_module.host.cancel_request    = 0;                          /* optional */
	ogx_g_module.host.class_table_begin = 0x004127B4u;
	ogx_g_module.host.class_table_end   = 0x004127CCu;
	ogx_g_module.host.xdevice_type_gamepad = 0x004127D8u;            /* pointer identity */
	ogx_g_module.host.now_ms            = 0;                          /* unused */
	ogx_transport_init();
	/* native chain fakes (host build leaves orig_* NULL; see ogx_transport_init) */
	ogx_g_module.present.orig_XGetDeviceChanges = nat_devchanges;
	ogx_g_module.present.orig_XInputOpen        = nat_open;
}

static void trigger_attach(void)
{
	typedef void (*attach_fn)(void *);
	((attach_fn)(uintptr_t)ogx_g_module.desc.Attach)((void *)DEV);
	drain();   /* S0..S5 complete; ends live with the persistent IN armed */
}

static void trigger_remove(void)
{
	typedef void (*remove_fn)(void *);
	((remove_fn)(uintptr_t)ogx_g_module.desc.RemoveDevice)((void *)DEV);
	drain();   /* default->IN->OUT close chain -> RemoveComplete */
}

int main(void)
{
	printf("== test 1: missing-bindings rejection ==\n");
	{
		ogx_g_module.install_failed = 0;
		ogx_g_module.installed_hooks = 0;
		ogx_g_module.host.submit_request = 0;   /* required surface missing */
		CHECK(ogx_install_hooks() < 0, "install refuses when submit_request absent");
		CHECK(ogx_g_module.installed_hooks == 0, "no hook bit set on refusal");
		CHECK(ogx_g_module.install_failed == 1, "install_failed latch set");
	}
	{
		ogx_g_module.install_failed = 0;
		ogx_g_module.host.submit_request   = (u32)(uintptr_t)fake_submit;
		ogx_g_module.host.add_complete     = 0;   /* add_complete required, missing */
		ogx_g_module.host.remove_complete  = (u32)(uintptr_t)fake_remove_complete;
		ogx_g_module.host.class_table_begin = 0x4127B4u;
		ogx_g_module.host.class_table_end   = 0x4127CCu;
		ogx_g_module.host.xdevice_type_gamepad = 0;   /* dtype pointer required */
		CHECK(ogx_install_hooks() < 0, "install refuses when add_complete/dtype absent");
	}

	printf("== test 2-3: attach -> live -> input served via game-facing stubs ==\n");
	g_next_handle = 0x100;
	g_add_complete_calls = 0; g_remove_complete_calls = 0;
	wire_host();
	trigger_attach();
	CHECK(ogx_g_module.att.lifecycle == GDR_LIFE_LIVE, "attach reached LIVE state");
	CHECK(g_add_complete_calls == 1 && g_add_complete_status == 0,
	      "AddComplete signalled exactly once (status 0)");
	CHECK(ogx_g_module.att.in_handle != 0, "interrupt IN endpoint opened");
	CHECK(gdr_transport_live(1, ogx_g_module.att.in_handle), "transport live guard true");

	/* qualify wired + feed input + pump via the exported stub */
	ogx_module_pump();   /* run once: qualify wired -> ready, power-on OUT queued */
	{
		u8 frm[64]; int n = build_input(frm, 0x0010 /* A */);
		inject_rx(frm, n);
	}
	{
		uint32_t ins = 0, rem = 0;
		ogx_stub_xgetdevicechanges(0x004127D8u, &ins, &rem);  /* services the pump */
		CHECK((ins & (1u << OGX_TRANSPORT_PORT)) != 0, "virtual insertion on fixed slot");
	}
	{
		uintptr_t h = ogx_stub_xinputopen(0x004127D8u, OGX_TRANSPORT_PORT, 0, 0);
		CHECK(h != 0, "XInputOpen returns a synthetic handle");
		ogx_state_t st; memset(&st, 0xCC, sizeof(st));
		CHECK(ogx_stub_xinputgetstate(h, (uintptr_t)&st) == OGX_ERR_SUCCESS,
		      "GetState success on virtual handle");
		CHECK(st.Gamepad.bAnalogButtons[XG_AB_A] == 0xFF,
		      "A button served (0xFF) through the full bridge");
	}

	printf("== test 4: detach -> close chain -> RemoveComplete -> stale handle ==\n");
	{
		uintptr_t h = ogx_stub_xinputopen(0x004127D8u, OGX_TRANSPORT_PORT, 0, 0);
		trigger_remove();
		CHECK(g_remove_complete_calls == 1, "RemoveComplete acked after close chain");
		CHECK(ogx_g_module.att.lifecycle == GDR_LIFE_IDLE, "lifecycle back to IDLE");
		ogx_state_t st; memset(&st, 0xCC, sizeof(st));
		CHECK(ogx_stub_xinputgetstate(h, (uintptr_t)&st) == OGX_ERR_NOT_CONNECTED,
		      "stale handle -> ERROR_DEVICE_NOT_CONNECTED");
	}

	printf("== test 5: reconnect -> new generation; held button cannot survive ==\n");
	{
		uintptr_t h1 = 0, h2;
		ogx_state_t st;
		/* gen1: A held */
		ogx_module_pump();   /* consume DETACH -> neutralize gip */
		trigger_attach();
		ogx_module_pump();   /* qualify wired */
		{
			u8 frm[64]; int n = build_input(frm, 0x0010 /* A */);
			inject_rx(frm, n);
		}
		{
			uint32_t ins = 0, rem = 0;
			ogx_stub_xgetdevicechanges(0x004127D8u, &ins, &rem);
		}
		h1 = ogx_stub_xinputopen(0x004127D8u, OGX_TRANSPORT_PORT, 0, 0);
		memset(&st, 0xCC, sizeof(st));
		CHECK(ogx_stub_xinputgetstate(h1, (uintptr_t)&st) == OGX_ERR_SUCCESS &&
		      st.Gamepad.bAnalogButtons[XG_AB_A] == 0xFF, "gen1: A held");

		/* detach gen1 */
		trigger_remove();
		ogx_module_pump();   /* consume DETACH -> neutralize (A cleared) */

		/* gen2 reconnect: neutral input only */
		trigger_attach();
		ogx_module_pump();   /* qualify wired */
		{
			u8 frm[64]; int n = build_input(frm, 0x0000 /* no buttons */);
			inject_rx(frm, n);
		}
		{
			uint32_t ins = 0, rem = 0;
			ogx_stub_xgetdevicechanges(0x004127D8u, &ins, &rem);   /* services pump */
		}
		h2 = ogx_stub_xinputopen(0x004127D8u, OGX_TRANSPORT_PORT, 0, 0);
		CHECK(h2 != 0 && h2 != h1, "reconnect issues a NEW handle");
		memset(&st, 0xCC, sizeof(st));
		CHECK(ogx_stub_xinputgetstate(h2, (uintptr_t)&st) == OGX_ERR_SUCCESS &&
		      st.Gamepad.bAnalogButtons[XG_AB_A] == 0x00,
		      "gen2: held gen1 A does NOT survive reconnect");
		memset(&st, 0xCC, sizeof(st));
		CHECK(ogx_stub_xinputgetstate(h1, (uintptr_t)&st) == OGX_ERR_NOT_CONNECTED,
		      "gen1 handle stays dead after replug");
	}

	printf("== test 6: native stock port passthrough (orig_* chain) ==\n");
	{
		g_nat_mask = (1u << 0);   /* a real pad owns port 0 */
		ogx_g_module.present.native_connected_mask = (1u << 0);
		uintptr_t nh = ogx_XInputOpen(&ogx_g_module.present, 0x004127D8u, 0, 0, 0);
		CHECK(nh == NAT_HANDLE, "native-owned port 0 -> chained to fake native driver");
	}

	printf("\n%s: %d failure(s)\n", g_fail == 0 ? "PASS" : "FAIL", g_fail);
	return g_fail == 0 ? 0 : 1;
}
