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
	}
	return ogx_XGetDeviceChanges(g_ctx, dtype, ins, rem);
}

uintptr_t OGX_STDCALL ogx_stub_xinputopen(uintptr_t dtype, uint32_t port, uint32_t slot, uintptr_t poll)
{
	return ogx_XInputOpen(g_ctx, dtype, port, slot, poll);
}

void OGX_STDCALL ogx_stub_xinputclose(uintptr_t handle)
{
	ogx_XInputClose(g_ctx, handle);
}

uint32_t OGX_STDCALL ogx_stub_xinputgetcaps(uintptr_t handle, uintptr_t caps)
{
	return ogx_XInputGetCapabilities(g_ctx, handle, caps);
}

uint32_t OGX_STDCALL ogx_stub_xinputgetstate(uintptr_t handle, uintptr_t state)
{
	return ogx_XInputGetState(g_ctx, handle, state);
}

uint32_t OGX_STDCALL ogx_stub_xinputsetstate(uintptr_t handle, uintptr_t feedback)
{
	return ogx_XInputSetState(g_ctx, handle, feedback);
}
