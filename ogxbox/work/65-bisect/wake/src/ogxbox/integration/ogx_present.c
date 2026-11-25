/* SPDX-License-Identifier: GPL-3.0-or-later */
/*
 * ogx_present.c -- see ogx_present.h. Portable, host-testable, i386-static-PIE
 * friendly: single-owner (no internal locking; the owning transport serializes
 * cross-thread access to attached_mask/og_gip -- volatile is visibility, not
 * synchronization), no heap (fixed arena), reads og_gip_port snapshots it does
 * not own, and chains every non-virtual call to the untouched title XID code.
 */
#include "ogx_present.h"

/* ------------------------------------------------------------------------- */
/* presence contract                                                          */
/* ------------------------------------------------------------------------- */

bool ogx_port_present(const struct ogx_host_ctx *ctx, uint32_t port)
{
	if (!ctx || port >= OGX_MAX_PORTS)
		return false;
	if (!(ctx->attached_mask & (1u << port)))
		return false;                     /* USB backend has not claimed it */
	if (!ctx->ports[port])
		return false;
	return ctx->ports[port]->ready;       /* powered-ready, NOT input-seen */
}

/* ------------------------------------------------------------------------- */
/* synthetic-handle classification                                            */
/* ------------------------------------------------------------------------- */

/* OGX_HK_NATIVE = not one of our handles -> chain to the real driver.
 * OGX_HK_STALE  = ours, but dead (unplugged/replugged) -> owned error path.
 * OGX_HK_LIVE   = ours and current -> serve. Only live/stale deref our arena. */
enum ogx_hk { OGX_HK_NATIVE, OGX_HK_STALE, OGX_HK_LIVE };

static enum ogx_hk vhandle_classify(const struct ogx_host_ctx *ctx,
				    uintptr_t handle, struct ogx_vhandle **out)
{
	uintptr_t base, end, off;
	struct ogx_vhandle *v;

	if (out)
		*out = NULL;
	if (!ctx || !handle)
		return OGX_HK_NATIVE;

	base = (uintptr_t)&ctx->vh[0];
	end  = (uintptr_t)&ctx->vh[OGX_HANDLE_ARENA];

	/* never dereference memory outside our own arena (the title's real handles
	 * can be anything; they are chained, never read) */
	if (handle < base || handle >= end)
		return OGX_HK_NATIVE;
	off = handle - base;
	if (off % sizeof(*v) != 0)
		return OGX_HK_NATIVE;

	v = (struct ogx_vhandle *)handle;
	if (v->magic != OGX_HANDLE_MAGIC || v->port >= OGX_MAX_PORTS)
		return OGX_HK_NATIVE;           /* forged / corrupt: not ours */

	if (out)
		*out = v;
	return v->live ? OGX_HK_LIVE : OGX_HK_STALE;
}

void ogx_present_port_lost(struct ogx_host_ctx *ctx, uint32_t port)
{
	if (!ctx || port >= OGX_MAX_PORTS)
		return;
	for (uint32_t i = 0; i < OGX_HANDLE_ARENA; i++) {
		struct ogx_vhandle *v = &ctx->vh[i];
		if (v->live && v->magic == OGX_HANDLE_MAGIC && v->port == port)
			v->live = 0;   /* never reissued (monotonic arena) -> dead forever */
	}
}

/* ------------------------------------------------------------------------- */
/* XGetDeviceChanges                                                          */
/* ------------------------------------------------------------------------- */

uint32_t ogx_XGetDeviceChanges(struct ogx_host_ctx *ctx, uintptr_t dtype,
			       uint32_t *ins, uint32_t *rem)
{
	uint32_t native_ins = 0, native_rem = 0;
	uint32_t native_bool = 0;
	uint32_t virt_ins = 0, virt_rem = 0;

	if (!ctx || !ins || !rem)
		return 0u;

	/* 1. chain to the real driver first: never swallow native hot-plug events */
	if (ctx->orig_XGetDeviceChanges) {
		native_bool = ctx->orig_XGetDeviceChanges(dtype, &native_ins, &native_rem);
		*ins = native_ins;
		*rem = native_rem;
	} else {
		*ins = 0;
		*rem = 0;
	}

	/* 2. only the GAMEPAD device type is merged or tracked. Memory-unit/headset
	 *    types pass through untouched and MUST NOT contaminate the gamepad
	 *    native mask (their insertions/removals are not gamepad ports 0..3). */
	if (dtype != ctx->xdevice_type_gamepad)
		return native_bool;

	/* mirror the native mask for the gamepad type only */
	ctx->native_connected_mask =
	    (ctx->native_connected_mask & ~native_rem) | native_ins;

	/* 3. EFFECTIVE virtual presence = physical+ready AND NOT native-owned.
	 *    Track effective presence for edge detection so a native pad holding a
	 *    port also suppresses the virtual device ready underneath it, and its
	 *    removal lets that virtual device become visible. */
	for (uint32_t p = 0; p < OGX_MAX_PORTS; p++) {
		bool native_gone = (native_rem >> p) & 1u;
		bool here        = (ctx->native_connected_mask >> p) & 1u;
		bool now         = ogx_port_present(ctx, p) && !here;

		if (native_gone) {
			/* handover: a native pad just vacated this port. Hold the
			 * virtual rising edge ONE tick so the game closes the native
			 * handle (rem, already emitted above) before it opens the
			 * virtual one (ins), avoiding a rem+ins of the same port
			 * slot in a single call. prev_present stays 0 so the NEXT
			 * tick raises the insertion. */
			continue;
		}

		if (now && !ctx->prev_present[p])
			virt_ins |= (1u << p);
		if (!now && ctx->prev_present[p])
			virt_rem |= (1u << p);
		ctx->prev_present[p] = now ? 1u : 0u;
	}

	if (virt_ins) ctx->insertion_edges++;
	if (virt_rem) ctx->removal_edges++;

	/* invalidate any live handle of a port that just went away: the detached
	 * handle now returns ERROR_DEVICE_NOT_CONNECTED, never a stale snapshot.
	 * Also fires when a native pad re-takes a port (virt_rem). */
	if (virt_rem) {
		for (uint32_t i = 0; i < OGX_HANDLE_ARENA; i++) {
			struct ogx_vhandle *v = &ctx->vh[i];
			if (v->live && v->magic == OGX_HANDLE_MAGIC &&
			    (virt_rem & (1u << v->port)))
				v->live = 0;
		}
	}

	*ins |= virt_ins;
	*rem |= virt_rem;
	return (native_bool || virt_ins || virt_rem) ? 1u : 0u;
}

/* ------------------------------------------------------------------------- */
/* XInputOpen                                                                 */
/* ------------------------------------------------------------------------- */

static struct ogx_vhandle *handle_alloc(struct ogx_host_ctx *ctx, uint32_t port)
{
	/* MONOTONIC: never recycle an issued address. A stale pre-unplug handle is
	 * a raw uintptr; if it aliased a later live object it would resurrect
	 * (vhandle_classify reads the NEW object's magic/live, not the stored gen).
	 * Never reissuing a slot keeps a stale handle dead forever. The trade-off
	 * is a FINITE handle budget: after OGX_HANDLE_ARENA issues the arena is
	 * exhausted and ogx_XInputOpen fails closed (NULL = no-device) until the
	 * title reboots. That limit is documented, not a transparent infinite
	 * hotplug. */
	if (ctx->next_handle >= OGX_HANDLE_ARENA)
		return NULL;   /* arena exhausted -> honest no-device */

	struct ogx_vhandle *v = &ctx->vh[ctx->next_handle++];
	v->magic = OGX_HANDLE_MAGIC;
	v->gen   = ++ctx->gen[port];
	v->port  = port;
	v->live  = 1;
	return v;
}

uintptr_t ogx_XInputOpen(struct ogx_host_ctx *ctx, uintptr_t dtype,
			 uint32_t port, uint32_t slot, uintptr_t poll)
{
	(void)slot; (void)poll;

	if (!ctx)
		return 0;

	/* not the gamepad type, or an out-of-range port, or the port is natively
	 * occupied -> the real driver decides (never steal/replace a real pad). */
	if (dtype != ctx->xdevice_type_gamepad ||
	    port >= OGX_MAX_PORTS ||
	    (ctx->native_connected_mask & (1u << port)) ||
	    !ogx_port_present(ctx, port)) {
		if (ctx->orig_XInputOpen)
			return ctx->orig_XInputOpen(dtype, port, slot, poll);
		return 0;
	}

	struct ogx_vhandle *v = handle_alloc(ctx, port);
	if (!v)
		return 0;
	return (uintptr_t)v;
}

/* ------------------------------------------------------------------------- */
/* XInputClose                                                                */
/* ------------------------------------------------------------------------- */

void ogx_XInputClose(struct ogx_host_ctx *ctx, uintptr_t handle)
{
	struct ogx_vhandle *v;
	enum ogx_hk k;

	if (!ctx)
		return;

	k = vhandle_classify(ctx, handle, &v);
	if (k == OGX_HK_LIVE) {
		v->live = 0;              /* nothing owned to free; just release */
		return;
	}
	if (k == OGX_HK_STALE)
		return;                   /* already dead; do NOT touch native code */

	/* native handle -> the real driver frees it */
	if (ctx->orig_XInputClose)
		ctx->orig_XInputClose(handle);
}

/* ------------------------------------------------------------------------- */
/* XInputGetCapabilities                                                      */
/* ------------------------------------------------------------------------- */

uint32_t ogx_XInputGetCapabilities(struct ogx_host_ctx *ctx, uintptr_t handle,
				   uintptr_t caps)
{
	struct ogx_vhandle *v;
	enum ogx_hk k;

	if (!ctx)
		return OGX_ERR_INVALID_PARAM;

	k = vhandle_classify(ctx, handle, &v);
	if (k == OGX_HK_LIVE) {
		if (!caps)
			return OGX_ERR_INVALID_PARAM;
		if (!ogx_port_present(ctx, v->port))
			return OGX_ERR_NOT_CONNECTED;   /* detached: fail, don't fake */
		ogx_fill_gamepad_caps((ogx_capabilities_t *)caps);
		return OGX_ERR_SUCCESS;
	}
	if (k == OGX_HK_STALE)
		return OGX_ERR_NOT_CONNECTED;

	if (ctx->orig_XInputGetCapabilities)
		return ctx->orig_XInputGetCapabilities(handle, caps);
	return OGX_ERR_NOT_CONNECTED;
}

/* ------------------------------------------------------------------------- */
/* XInputGetState                                                             */
/* ------------------------------------------------------------------------- */

uint32_t ogx_XInputGetState(struct ogx_host_ctx *ctx, uintptr_t handle,
			    uintptr_t state)
{
	struct ogx_vhandle *v;
	enum ogx_hk k;

	if (!ctx)
		return OGX_ERR_INVALID_PARAM;

	k = vhandle_classify(ctx, handle, &v);
	if (k == OGX_HK_LIVE) {
		ogx_state_t *out = (ogx_state_t *)state;
		uint32_t port = v->port;
		struct og_gip_port *gp;

		if (!out)
			return OGX_ERR_INVALID_PARAM;      /* documented null-output result */

		if (!ogx_port_present(ctx, port) || !ctx->ports[port])
			return OGX_ERR_NOT_CONNECTED;

		gp = ctx->ports[port];
		memset(out, 0, sizeof(*out));

		if (gp->snapshot_valid) {
			/* monotonic game-facing packet number: bump on a NEW adapter
			 * seq, or when the handle generation/epoch changed. A replug
			 * resets the adapter seq (first input seq == 1 again), so seq
			 * alone can alias the previous session's value and mask a real
			 * state change under an unchanged packet number. */
			uint32_t g = ctx->gen[port];
			if (gp->seq != ctx->last_served_seq[port] ||
			    g != ctx->last_served_gen[port]) {
				ctx->served_packet[port]++;
				ctx->last_served_seq[port] = gp->seq;
				ctx->last_served_gen[port] = g;
			}
			out->dwPacketNumber = ctx->served_packet[port];
			/* the 18-byte og_gamepad IS the XINPUT_GAMEPAD layout */
			memcpy(&out->Gamepad, &gp->gamepad, OGX_XINPUT_GAMEPAD_SIZE);
		} else {
			/* present (ready) but no input frame yet: honest zeroed boot
			 * state, not a fabricated press */
			out->dwPacketNumber = ctx->served_packet[port];
		}
		return OGX_ERR_SUCCESS;
	}
	if (k == OGX_HK_STALE)
		return OGX_ERR_NOT_CONNECTED;           /* unplug/replug: stale handle */

	if (ctx->orig_XInputGetState)
		return ctx->orig_XInputGetState(handle, state);
	return OGX_ERR_NOT_CONNECTED;
}

/* ------------------------------------------------------------------------- */
/* XInputSetState (rumble)                                                    */
/* ------------------------------------------------------------------------- */

uint32_t ogx_XInputSetState(struct ogx_host_ctx *ctx, uintptr_t handle,
			    uintptr_t feedback)
{
	struct ogx_vhandle *v;
	enum ogx_hk k;

	if (!ctx)
		return OGX_ERR_INVALID_PARAM;

	k = vhandle_classify(ctx, handle, &v);
	if (k == OGX_HK_LIVE) {
		ogx_input_feedback_t *fb = (ogx_input_feedback_t *)feedback;

		/* PXINPUT_FEEDBACK (IN OUT), NOT a bare 4-byte XINPUT_VIBRATION:
		 * the Rumble value sits at offset 66 behind the header. Validate
		 * the parameter first, then the device presence. */
		if (!fb)
			return OGX_ERR_INVALID_PARAM;
		if (!ogx_port_present(ctx, v->port))
			return OGX_ERR_NOT_CONNECTED;

		/* Input-only milestone: there are NO motors, so rumble cannot
		 * actuate and we will not pretend otherwise. We never read the
		 * header bytes as motor speeds and never emit a GIP rumble
		 * command. Returning ERROR_NOT_SUPPORTED and writing it into
		 * Header.dwStatus (the XID output-completion gate) tells the title
		 * honestly that the rumble did NOT happen; hEvent is left
		 * untouched because no completion occurs. */
		fb->Header.dwStatus = OGX_ERR_NOT_SUPPORTED;
		return OGX_ERR_NOT_SUPPORTED;
	}
	if (k == OGX_HK_STALE)
		return OGX_ERR_NOT_CONNECTED;

	if (ctx->orig_XInputSetState)
		return ctx->orig_XInputSetState(handle, feedback);
	return OGX_ERR_NOT_CONNECTED;
}
