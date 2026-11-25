/* SPDX-License-Identifier: GPL-3.0-or-later */
/*
 * native_mock.c -- SYNTHETIC native Xbox USB stack + native XInput, i386 only.
 *
 * Everything in this file is a TEST DOUBLE for the TITLE side of the ABI. It is
 * NOT a copy of the production module: the production module
 * (ogx_transport.c + ogx_present.c + ogx_stub.c + gipdrive.h) is compiled
 * unmodified and calls into these functions exactly the way it calls u803:
 *   - IUsbDevice::SubmitRequest/AddComplete/RemoveComplete as __thiscall
 *     (self in ECX) through the uint32_t VAs in ogx_g_module.host,
 *   - URB CompleteProc as __stdcall(urb, ctx),
 *   - ogx_chain_* (normally trampoline.S) as __stdcall native XInput.
 * Completions are delivered by the test (async) unless inline mode is set.
 */
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "native_mock.h"

struct mock_state M;

#define TC __attribute__((thiscall))
#define SC __attribute__((stdcall))
typedef void (SC *complete_fn)(void *urb, void *ctx);

/* the GIP config descriptor the measured pad exposes (iface0 FF/47/D0,
 * EP 0x82 IN int4 mps64, EP 0x02 OUT int4 mps64; work/20 CFG line 26). */
static const uint8_t k_cfg[32] = {
	0x09,0x02,0x20,0x00,0x01,0x01,0x00,0xa0,0xfa,
	0x09,0x04,0x00,0x00,0x02,0xff,0x47,0xd0,0x00,
	0x07,0x05,0x02,0x03,0x40,0x00,0x04,
	0x07,0x05,0x82,0x03,0x40,0x00,0x04,
};

static struct fake_dev *dev_of(void *self) { return (struct fake_dev *)self; }

void mock_complete(void *urb, uint32_t status)
{
	gdr_urb_header *h = (gdr_urb_header *)urb;
	h->Status = status;
	M.completions++;
	((complete_fn)(uintptr_t)h->CompleteProc)(urb, (void *)(uintptr_t)h->CompleteContext);
}

static void pend_push(void *urb, struct fake_dev *d)
{
	if (M.npend < MOCK_MAXPEND) { M.pend[M.npend].urb = urb; M.pend[M.npend].dev = d; M.npend++; }
	else M.violations++;
}

/* complete one deferred (non-interrupt) URB in FIFO order; returns 0 if none */
int mock_step(void)
{
	if (!M.npend) return 0;
	void *urb = M.pend[0].urb;
	memmove(&M.pend[0], &M.pend[1], (size_t)(M.npend - 1) * sizeof M.pend[0]);
	M.npend--;
	mock_complete(urb, 0);
	return 1;
}
int mock_run(void) { int n = 0; while (mock_step()) n++; return n; }

static long TC mock_submit(void *self, void *urb)
{
	struct fake_dev *d = dev_of(self);
	gdr_urb_header *h = (gdr_urb_header *)urb;
	M.submits++;
	M.depth++;
	if (M.depth > M.max_depth) M.max_depth = M.depth;
	if (!d || d->freed) { M.freed_calls++; M.violations++; M.depth--; return (long)0xC000000Du; }
	if (M.reenter_on_submit && M.reenter_on_submit(urb)) { /* synthetic re-entry */ }
	switch (h->Function) {
	case 0x82: { /* open default control pipe */
		gdr_urb_open *o = (gdr_urb_open *)urb;
		o->EndpointHandle = 0x1000u + d->id;
		break; }
	case 0x02: { /* open interrupt endpoint */
		gdr_urb_open *o = (gdr_urb_open *)urb;
		o->EndpointHandle = 0x2000u + (uint32_t)d->id * 0x100u + o->EndpointAddress;
		M.opens++;
		break; }
	case 0x40: { /* control transfer */
		gdr_urb_control *c = (gdr_urb_control *)urb;
		if (c->SetupPacket[1] == 0x06) {
			uint32_t n = c->TransferLength > sizeof k_cfg ? sizeof k_cfg : c->TransferLength;
			memcpy((void *)(uintptr_t)c->TransferBuffer, k_cfg, n);
			c->TransferLength = n;
		}
		break; }
	case 0x41: { /* interrupt transfer */
		gdr_urb_transfer *t = (gdr_urb_transfer *)urb;
		if (t->FlagB0 == 2) {          /* IN: stays pending until data */
			M.in_urb = urb; M.in_dev = d; M.in_submits++;
			if (M.inline_in && M.inline_in_budget > 0) {
				M.inline_in_budget--;
				t->TransferLength = 0;
				mock_complete(urb, 0);
			}
			M.depth--;
			return 0;
		}
		/* OUT */
		M.out_frames++;
		if (M.nout < MOCK_MAXOUT) { memcpy(M.out_log[M.nout], (void *)(uintptr_t)t->TransferBuffer, t->TransferLength > 64 ? 64 : t->TransferLength); M.out_len[M.nout] = t->TransferLength; M.out_dev[M.nout] = d->id; M.nout++; }
		break; }
	case 0xc3: case 0x43: { /* close endpoint */
		gdr_urb_close *c = (gdr_urb_close *)urb;
		if (M.nclose < MOCK_MAXCLOSE) { M.close_fn[M.nclose] = h->Function; M.close_h[M.nclose] = c->EndpointHandle; M.close_dev[M.nclose] = d->id; M.close_rc_before[M.nclose] = d->remove_completes; M.nclose++; }
		/* native model: closing the IN pipe retires its pending transfer with a
		 * cancel status BEFORE the close completes (unless late_in is set). */
		if (h->Function == 0x43 && M.in_urb && M.in_dev == d && !M.late_in) {
			gdr_urb_transfer *t = (gdr_urb_transfer *)M.in_urb;
			if (t->EndpointHandle == c->EndpointHandle) { void *u = M.in_urb; M.in_urb = 0; mock_complete(u, 0xC0000120u); }
		}
		break; }
	default:
		break;
	}
	if (M.inline_all) { M.depth--; mock_complete(urb, M.fail_next_close && (h->Function == 0x43 || h->Function == 0xc3) ? (M.fail_next_close = 0, 0xC0000001u) : 0); return 0; }
	pend_push(urb, d);
	M.depth--;
	return 0;
}

static void TC mock_add_complete(void *self, long status)
{
	struct fake_dev *d = dev_of(self);
	if (!d || d->freed) { M.freed_calls++; M.violations++; return; }
	d->add_completes++; d->add_status = status;
}

static void TC mock_remove_complete(void *self)
{
	struct fake_dev *d = dev_of(self);
	if (!d || d->freed) { M.freed_calls++; M.violations++; return; }
	d->remove_completes++;
	d->closes_at_rc = 0;
	for (int i = 0; i < M.nclose; i++) if (M.close_dev[i] == d->id) d->closes_at_rc++;
	d->pending_closes_at_rc = M.npend;
	d->freed = 1;                          /* stack frees the device address */
}

uint32_t mock_va_submit(void)  { return (uint32_t)(uintptr_t)mock_submit; }
uint32_t mock_va_add(void)     { return (uint32_t)(uintptr_t)mock_add_complete; }
uint32_t mock_va_remove(void)  { return (uint32_t)(uintptr_t)mock_remove_complete; }

/* deliver one interrupt-IN frame on the currently armed IN URB */
int mock_in_frame(const uint8_t *data, uint32_t n)
{
	gdr_urb_transfer *t = (gdr_urb_transfer *)M.in_urb;
	if (!t) return 0;
	M.in_urb = 0;
	memcpy((void *)(uintptr_t)t->TransferBuffer, data, n);
	t->TransferLength = n;
	mock_complete(t, 0);
	return 1;
}

/* ---- SYNTHETIC native XInput (stands in for trampoline.S chain stubs) ---- */
uint32_t SC ogx_chain_getdevicechanges(uintptr_t dtype, uint32_t *ins, uint32_t *rem)
{
	M.n_gdc++; M.last_dtype = dtype;
	if (dtype != M.dtype_gamepad) { *ins = M.mu_ins; *rem = 0; M.mu_ins = 0; return *ins != 0; }
	*ins = M.native_ins; *rem = M.native_rem;
	M.native_ins = M.native_rem = 0;
	return (*ins | *rem) ? 1u : 0u;
}
uintptr_t SC ogx_chain_inputopen(uintptr_t dtype, uint32_t port, uint32_t slot, uintptr_t poll)
{
	M.n_open++; M.open_port = port; M.open_slot = slot; M.open_poll = poll; (void)dtype;
	return 0x7A000000u | (port << 8) | 0x11u;   /* opaque native handle, never ours */
}
void SC ogx_chain_inputclose(uintptr_t h) { M.n_close++; M.close_handle = h; }
uint32_t SC ogx_chain_getcaps(uintptr_t h, uintptr_t caps) { M.n_caps++; (void)h; (void)caps; return 0; }
uint32_t SC ogx_chain_getstate(uintptr_t h, uintptr_t st)
{
	M.n_getstate++; M.getstate_handle = h;
	memset((void *)st, 0x5A, 22);               /* native pattern */
	return 0;
}
uint32_t SC ogx_chain_setstate(uintptr_t h, uintptr_t fb) { M.n_setstate++; (void)h; (void)fb; return 0; }
