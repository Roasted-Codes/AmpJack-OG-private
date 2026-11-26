/* SPDX-License-Identifier: GPL-3.0-or-later */
/*
 * ogx_stub.c -- the six HOOK entry points the E9 detours jump into. Each is a
 * stdcall function that (a) picks up the injected context once, (b) delegates to
 * the production ogx_X* discriminator (ogx_present.c), which either serves the
 * virtual path or CHAINS to the real driver through ctx->orig_* (a chain
 * trampoline from trampoline.S). No absolute self-symbol loads: the ctx lives in
 * a single hidden slot the compiler reaches PIC-relatively (static PIE).
 */
#include "ogx_present.h"

static struct ogx_host_ctx *volatile g_ctx;

/* pump runs on the SAME game thread as the XInput calls, serialized with the
 * presentation mutations; a re-entrancy guard makes it safe even if a native
 * chained path ever reached back into a hook (it does not today). */
void ogx_module_pump(void);

/* Title-thread generation resync (ogx_transport.c): a cheap compare of the
 * real attach generation, no ring decode. Called before every entry point
 * that can serve a virtual handle, so an unplug/replug seen by RemoveDevice
 * kills old handles and the old snapshot even if the game has not called
 * XGetDeviceChanges yet. It does not consume the removal edge (the next
 * XGetDeviceChanges still reports it). Idempotent; it only clears state, so a
 * chained native call re-entering a hook cannot corrupt it. */
void ogx_transport_sync(void);

static int g_pump_depth;

void ogx_stub_bind_ctx(struct ogx_host_ctx *ctx)
{
	g_ctx = ctx;
}

uint32_t OGX_STDCALL ogx_stub_xgetdevicechanges(uintptr_t dtype, uint32_t *ins, uint32_t *rem)
{
	/* the game calls XGetDeviceChanges every frame -> this is the transport
	 * service path. No eighth hook is added: the pump is serviced HERE, on the
	 * existing game-called API, before the discriminator reads presentation
	 * state. Non-blocking: only ring-decode + async OUT submit. */
	if (!g_pump_depth) {
		g_pump_depth = 1;
		ogx_module_pump();
		g_pump_depth = 0;
	} else {
		ogx_transport_sync();
	}
	return ogx_XGetDeviceChanges(g_ctx, dtype, ins, rem);
}

uintptr_t OGX_STDCALL ogx_stub_xinputopen(uintptr_t dtype, uint32_t port, uint32_t slot, uintptr_t poll)
{
	ogx_transport_sync();
	return ogx_XInputOpen(g_ctx, dtype, port, slot, poll);
}

void OGX_STDCALL ogx_stub_xinputclose(uintptr_t handle)
{
	ogx_transport_sync();
	ogx_XInputClose(g_ctx, handle);
}

uint32_t OGX_STDCALL ogx_stub_xinputgetcaps(uintptr_t handle, uintptr_t caps)
{
	ogx_transport_sync();
	return ogx_XInputGetCapabilities(g_ctx, handle, caps);
}

uint32_t OGX_STDCALL ogx_stub_xinputgetstate(uintptr_t handle, uintptr_t state)
{
	ogx_transport_sync();
	return ogx_XInputGetState(g_ctx, handle, state);
}

uint32_t OGX_STDCALL ogx_stub_xinputsetstate(uintptr_t handle, uintptr_t feedback)
{
	ogx_transport_sync();
	return ogx_XInputSetState(g_ctx, handle, feedback);
}
