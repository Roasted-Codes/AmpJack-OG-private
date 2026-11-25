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

static void test_a(void)
{
	struct gdr_gip g; u8 out[64]; int n;
	setup(0); boot_live();
	inject_rx(INPUT, sizeof INPUT); pump();
	CHECK(ogx_g_module.gip.snapshot_valid && ogx_g_module.gip.input_reports == 1);
	CHECK(ogx_g_module.gip.announces == 0 && ogx_g_module.gip.rehandshakes == 0);
	inject_rx(ANN28, sizeof ANN28); pump();
	CHECK(nframes == 3 && is_power(2));
	CHECK(ogx_g_module.gip.announces == 1 && ogx_g_module.gip.rehandshakes == 1);
	CHECK(ogx_g_module.gip.s_init_pending == 1 && ogx_g_module.gip.ready == 1);
	CHECK(ogx_g_module.gip.snapshot_valid == 1);            /* snapshot kept */
	pump(); CHECK(nframes == 3);                            /* no S-init before TXDONE */
	complete_tx(0); pump(); CHECK(nframes == 4 && is_sinit(3));
	complete_tx(0); pump(); CHECK(nframes == 4);
	inject_rx(ANN4, sizeof ANN4); pump();                   /* len != 28 also re-handshakes */
	CHECK(nframes == 5 && is_power(4) && ogx_g_module.gip.announces == 2 && ogx_g_module.gip.rehandshakes == 2);
	complete_tx((long)(int)0xC0000001u); pump();            /* failed power-on: no S-init */
	CHECK(nframes == 5 && ogx_g_module.gip.s_init_pending == 1);
	CHECK(frames[2][2] != frames[0][2] && frames[4][2] != frames[2][2]);   /* new sequence */
	/* before qualification: old announce -> identify behaviour, no re-handshake */
	gdr_gip_init(&g, 0);
	gdr_gip_rx(&g, ANN28, sizeof ANN28);
	n = gdr_tx_drain(&g, out, 64);
	CHECK(n == 4 && out[0] == GIP_CMD_IDENTIFY && g.rehandshakes == 0 && g.announces == 1);
	gdr_gip_rx(&g, ANN4, sizeof ANN4);
	CHECK(gdr_tx_drain(&g, out, 64) == 0 && g.announces == 2 && g.rehandshakes == 0);
}

int main(void) { test_a(); printf("%s a frames=%d\n", fails ? "FAIL" : "PASS", nframes); return fails ? 1 : 0; }
