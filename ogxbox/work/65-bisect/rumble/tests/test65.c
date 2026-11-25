/* SPDX-License-Identifier: GPL-3.0-or-later */
/*
 * test63.c -- W63 hosted tests against the PRODUCTION module sources
 * (ogx_transport.c, ogx_present.c, ogx_stub.c, ogx_log.c, xinput_model.c and
 * the patched gipdrive.h), built -m32 with real thiscall/stdcall. USB, the pad,
 * kernel file I/O and IRQL are SYNTHETIC doubles; nothing here proves real
 * pad wake, real rumble or real file I/O.
 *   usage: test63 a|b|c1|c2|c3|c4|c5
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "ogx_module.h"

#define TC __attribute__((thiscall))
#define SC __attribute__((stdcall))
static int fails;
#define CHECK(c) do { if (!(c)) { printf("FAIL %s:%d %s\n", __FILE__, __LINE__, #c); fails++; } } while (0)

/* chain trampolines (title-only asm) -> synthetic native driver */
static int native_setstate;
uint32_t  SC ogx_chain_getdevicechanges(uintptr_t d, uint32_t *i, uint32_t *r) { (void)d; *i = *r = 0; return 0; }
uintptr_t SC ogx_chain_inputopen(uintptr_t a, uint32_t b, uint32_t c, uintptr_t d) { (void)a; (void)b; (void)c; (void)d; return 0; }
void      SC ogx_chain_inputclose(uintptr_t h) { (void)h; }
uint32_t  SC ogx_chain_getcaps(uintptr_t h, uintptr_t c) { (void)h; (void)c; return 0x48F; }
uint32_t  SC ogx_chain_getstate(uintptr_t h, uintptr_t s) { (void)h; (void)s; return 0x48F; }
uint32_t  SC ogx_chain_setstate(uintptr_t h, uintptr_t f) { (void)h; (void)f; native_setstate++; return 0x48F; }
uint32_t  SC ogx_stub_xgetdevicechanges(uintptr_t dtype, uint32_t *ins, uint32_t *rem);
uintptr_t SC ogx_stub_xinputopen(uintptr_t dtype, uint32_t port, uint32_t slot, uintptr_t poll);
uint32_t  SC ogx_stub_xinputsetstate(uintptr_t handle, uintptr_t feedback);

/* ---- synthetic USB stack ---------------------------------------------------- */
static u8 frames[256][64]; static int flen[256], nframes;
static gdr_urb_transfer *pending_tx;
static u8 dev[64];
static long TC fake_submit(void *self, void *urb)
{
	(void)self;
	if (urb == &ogx_g_module.att.tx_urb) {
		gdr_urb_transfer *u = urb;
		memcpy(frames[nframes], (void *)(uintptr_t)u->TransferBuffer, u->TransferLength);
		flen[nframes++] = (int)u->TransferLength;
		pending_tx = u;
	}
	return 0;
}
static void TC fake_add(void *self, long st) { (void)self; (void)st; }
static void TC fake_rc(void *self) { (void)self; }
static void complete_tx(long status)
{
	gdr_urb_transfer *u = pending_tx;
	if (!u) { printf("FAIL no pending tx\n"); fails++; return; }
	pending_tx = 0;
	u->Hdr.Status = (u32)status;
	((void (SC *)(void *, void *))(uintptr_t)u->Hdr.CompleteProc)(u, (void *)(uintptr_t)u->Hdr.CompleteContext);
}
#define DTYPE 0x4127D8u
static void pump(void) { uint32_t i, r; ogx_stub_xgetdevicechanges(DTYPE, &i, &r); }
static void inject_rx(const u8 *d, u32 n)
{
	struct gdr_evt e; memset(&e, 0, sizeof e);
	e.kind = GDR_EVT_RX; e.len = n; memcpy(e.data, d, n);
	gdr_ring_push(&ogx_g_module.ring, &e);
}
static void setup(uint32_t flags)
{
	ogx_g_module.host.submit_request  = (uint32_t)(uintptr_t)fake_submit;
	ogx_g_module.host.add_complete    = (uint32_t)(uintptr_t)fake_add;
	ogx_g_module.host.remove_complete = (uint32_t)(uintptr_t)fake_rc;
	ogx_g_module.host.xdevice_type_gamepad = DTYPE;
	(void)flags;
	ogx_transport_init();
	((void (SC *)(void *))(uintptr_t)ogx_g_module.desc.Attach)(dev);
	/* S0..S5 are proven elsewhere (f6/lifecycle); jump to the live state */
	ogx_g_module.att.state = 6; ogx_g_module.att.in_handle = 0x11; ogx_g_module.att.out_handle = 0x22;
}
static int is_power(int i) { return flen[i] == 5 && frames[i][0] == 5 && frames[i][1] == 0x20 && frames[i][3] == 1 && frames[i][4] == 0; }
static int is_sinit(int i) { return frames[i][0] == 5 && frames[i][3] == 0x0f; }
static const u8 ANN28[32] = { 0x02, 0x20, 0x05, 0x1c, 1,2,3,4,5,6, 0x5e,0x04, 0x12,0x0b, 1,0, 1,0 };
static const u8 ANN4[8]   = { 0x02, 0x20, 0x06, 0x04, 0xaa, 0xbb, 0xcc, 0xdd };
static const u8 INPUT[18] = { 0x20, 0x00, 0x01, 0x0e, 0x10, 0x00 };

static void boot_live(void)   /* qualify -> POWER -> S-init, queue idle */
{
	pump(); CHECK(nframes == 1 && is_power(0));
	complete_tx(0); pump(); CHECK(nframes == 2 && is_sinit(1));
	complete_tx(0); pump(); CHECK(nframes == 2 && !pending_tx);
}

static void w63_setstate(uintptr_t h, uint16_t l, uint16_t r, uint32_t *rc, uint32_t *st)
{
	ogx_input_feedback_t fb; memset(&fb, 0xee, sizeof fb);
	fb.Header.hEvent = 0x5555; fb.Rumble.wLeftMotorSpeed = l; fb.Rumble.wRightMotorSpeed = r;
	*rc = ogx_stub_xinputsetstate(h, (uintptr_t)&fb); *st = fb.Header.dwStatus;
}
static int is_rumble(int i, u8 l, u8 r)
{
	static const u8 t[13] = { 0x09, 0x00, 0, 0x09, 0x00, 0x0F, 0x00, 0x00, 0, 0, 0xFF, 0x00, 0xFF };
	u8 e[13]; memcpy(e, t, 13); e[2] = frames[i][2]; e[8] = l; e[9] = r;
	return flen[i] == 13 && !memcmp(frames[i], e, 13) && frames[i][2] != 0;
}
static uintptr_t vopen(void)
{
	uintptr_t h = ogx_stub_xinputopen(DTYPE, OGX_TRANSPORT_PORT, 0, 0);
	return h;
}
static void test_b(void)
{
	uint32_t rc, st, w; uintptr_t h; ogx_capabilities_t caps;
	setup(0); boot_live();
	h = vopen(); CHECK(h != 0);
	w63_setstate(h, 0x8000, 0xFFFF, &rc, &st);
	CHECK(rc == 997 && st == 0 && ogx_g_module.present.rumble_calls == 1 && ogx_g_module.present.rumble_hevent == 0x5555);
	pump(); CHECK(nframes == 3 && is_rumble(2, 0x40, 0x7F));
	/* busy: N calls -> exactly one frame carrying the LAST value */
	w63_setstate(h, 0x1000, 0x2000, &rc, &st); pump();
	w63_setstate(h, 0x3000, 0x4000, &rc, &st); pump();
	w63_setstate(h, 0xFE00, 0x0200, &rc, &st); pump();
	CHECK(nframes == 3);
	complete_tx(0); CHECK(nframes == 3);
	pump(); CHECK(nframes == 4 && is_rumble(3, 0x7F, 0x01));
	complete_tx(0); pump(); CHECK(nframes == 4);            /* unchanged -> nothing */
	w63_setstate(h, 0, 0, &rc, &st); pump(); CHECK(nframes == 5 && is_rumble(4, 0, 0));
	complete_tx(0);
	w63_setstate(h, 0x8000, 0x8000, &rc, &st); pump(); CHECK(nframes == 6 && is_rumble(5, 0x40, 0x40));
	complete_tx(0); pump(); CHECK(nframes == 6);
	/* generation change: requalify, then the nonzero desired value is re-sent */
	ogx_g_module.att.generation++;
	pump(); CHECK(nframes == 7 && is_power(6));
	complete_tx(0); pump(); CHECK(nframes == 8 && is_sinit(7));
	complete_tx(0); pump(); CHECK(nframes == 9 && is_rumble(8, 0x40, 0x40));
	complete_tx(0); pump(); CHECK(nframes == 9);
	/* stale and native handles unchanged */
	w = ogx_g_module.present.rumble_want[OGX_TRANSPORT_PORT];
	w63_setstate(h, 0x1111, 0x2222, &rc, &st);
	CHECK(rc == 0x48F && ogx_g_module.present.rumble_want[OGX_TRANSPORT_PORT] == w);
	w63_setstate(0x1234, 0x1111, 0x2222, &rc, &st);
	CHECK(rc == 0x48F && native_setstate == 1 && ogx_g_module.present.rumble_want[OGX_TRANSPORT_PORT] == w);
	CHECK(ogx_g_module.present.rumble_calls == 6);
	ogx_fill_gamepad_caps(&caps);
	CHECK(caps.Vibration.wLeftMotorSpeed == 0 && caps.Vibration.wRightMotorSpeed == 0);
}

int main(void) { test_b(); printf("%s b frames=%d\n", fails ? "FAIL" : "PASS", nframes); return fails ? 1 : 0; }
