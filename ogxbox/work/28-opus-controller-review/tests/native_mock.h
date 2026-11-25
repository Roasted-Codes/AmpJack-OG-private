/* SPDX-License-Identifier: GPL-3.0-or-later */
/* native_mock.h -- SYNTHETIC title-side doubles; see native_mock.c */
#ifndef NATIVE_MOCK_H
#define NATIVE_MOCK_H
#include "ogx_module.h"   /* production module ABI (unmodified) */

#define MOCK_MAXPEND  32
#define MOCK_MAXOUT   64
#define MOCK_MAXCLOSE 32

struct fake_dev {
	int id;
	int freed;              /* RemoveComplete ran: stack freed the address */
	int add_completes;
	long add_status;
	int remove_completes;
	int closes_at_rc;
	int pending_closes_at_rc;
};

struct mock_state {
	struct { void *urb; struct fake_dev *dev; } pend[MOCK_MAXPEND];
	int npend;
	void *in_urb; struct fake_dev *in_dev;
	int inline_all, inline_in, inline_in_budget, late_in, fail_next_close;
	int (*reenter_on_submit)(void *urb);
	int submits, completions, opens, in_submits, depth, max_depth;
	int freed_calls, violations;
	int out_frames, nout; uint8_t out_log[MOCK_MAXOUT][64]; uint32_t out_len[MOCK_MAXOUT]; int out_dev[MOCK_MAXOUT];
	int nclose; uint8_t close_fn[MOCK_MAXCLOSE]; uint32_t close_h[MOCK_MAXCLOSE]; int close_dev[MOCK_MAXCLOSE]; int close_rc_before[MOCK_MAXCLOSE];
	/* native XInput */
	uintptr_t dtype_gamepad;
	uint32_t native_ins, native_rem, mu_ins;
	int n_gdc, n_open, n_close, n_caps, n_getstate, n_setstate;
	uintptr_t last_dtype, close_handle, getstate_handle, open_poll;
	uint32_t open_port, open_slot;
};
extern struct mock_state M;

void mock_complete(void *urb, uint32_t status);
int  mock_step(void);
int  mock_run(void);
int  mock_in_frame(const uint8_t *data, uint32_t n);
uint32_t mock_va_submit(void);
uint32_t mock_va_add(void);
uint32_t mock_va_remove(void);
#endif
