/* SPDX-License-Identifier: GPL-3.0-or-later */
/*
 * ogx_transport.c -- the PROVEN GIP USB transport, retargeted to the Halo 2 u803
 * title. It is the thin platform wrapper over ogxbox/gipdriver/gipdrive.h: it
 * does NOT duplicate the USB stack or rewrite the GIP protocol. It only supplies
 * the injected title call surface (SubmitRequest / AddComplete / CancelRequest /
 * RemoveComplete, all VERIFIED/UNKNOWN VAs from ogx_module.h) and the
 * FindClassDriver class-match hook, then bridges the decoded gdr_snapshot into
 * the og_gip_port snapshot that ogx_present.c serves.
 *
 * DPC contract (unchanged from the proven probe): every completion callback only
 * pushes one bounded ring event and re-submits; no file I/O, no malloc, no
 * unbounded formatting and no parse happens in the DPC. All decoding, snapshot
 * publication and OUT queuing happen here in ogx_module_pump(), on the title
 * thread, which is the single owner. No waiting on the title thread, no timers
 * and no blocking in the XInput hook.
 */
#include "ogx_module.h"

/* ---- chain trampolines (trampoline.S) + the stub ctx binder (ogx_stub.c) ---- */
void   ogx_stub_bind_ctx(struct ogx_host_ctx *ctx);
/* The trampolines are tail-jump stubs that re-run the displaced bytes and jmp to
 * the original body; the original body does the final `ret N`. Declare them with
 * the title's stdcall signature so ogx_present.c calls them with the right arg
 * count (their asm body reads the args from the stack and never returns). */
uint32_t  OGX_STDCALL ogx_chain_getdevicechanges(uintptr_t, uint32_t *, uint32_t *);
uintptr_t OGX_STDCALL ogx_chain_inputopen(uintptr_t, uint32_t, uint32_t, uintptr_t);
void      OGX_STDCALL ogx_chain_inputclose(uintptr_t);
uint32_t  OGX_STDCALL ogx_chain_getcaps(uintptr_t, uintptr_t);
uint32_t  OGX_STDCALL ogx_chain_getstate(uintptr_t, uintptr_t);
uint32_t  OGX_STDCALL ogx_chain_setstate(uintptr_t, uintptr_t);

/* -- thiscall thunks: C cannot put `self` in ECX portably, so the injected VAs
 *    are cast to OGX_THISCALL function pointers (i386 __thiscall on the title,
 *    plain function pointers on the host-test build). ---- */
typedef long (OGX_THISCALL *ogx_thiscall_submit)(void *self, void *urb);
typedef void (OGX_THISCALL *ogx_thiscall_addcomplete)(void *self, long status);
typedef long (OGX_THISCALL *ogx_thiscall_cancel)(void *self, void *urb);
typedef void (OGX_THISCALL *ogx_thiscall_removecomplete)(void *self);

/* ---- module singleton (declared extern in ogx_module.h). The injector fills
 *      ogx_g_module.host BEFORE ogx_module_entry(): BSS is zero at load, and
 *      entry does NOT re-zero host. ---------------------------------------------- */
struct ogx_module ogx_g_module;

/* ---- transport seams: gdr_*_fn are plain function pointers in gipdrive.h;
 *      these wrappers do the thiscall through the injected VA. ------------------ */
static long ogx_usb_submit(void *device, void *urb)
{
	if (!ogx_g_module.host.submit_request)
		return -1;
	return ((ogx_thiscall_submit)(uintptr_t)ogx_g_module.host.submit_request)(device, urb);
}
static void ogx_usb_add_complete(void *device, long status)
{
	/* REQUIRED seam (0x416992): enumeration MUST signal AddComplete exactly once
	 * so the device leaves the pending-enum list. A zero injection is a refusal
	 * at install time, never a runtime no-op. */
	if (ogx_g_module.host.add_complete)
		((ogx_thiscall_addcomplete)(uintptr_t)ogx_g_module.host.add_complete)(device, status);
}
static long ogx_usb_cancel(void *device, void *urb)
{
	if (!ogx_g_module.host.cancel_request)
		return -1;
	return ((ogx_thiscall_cancel)(uintptr_t)ogx_g_module.host.cancel_request)(device, urb);
}
static void ogx_usb_remove_complete(void *device)
{
	/* REQUIRED seam (0x4165C6): native removal MUST close owned endpoints before
	 * this fires (gdr_close_next runs the default->IN->OUT close chain first). */
	if (ogx_g_module.host.remove_complete)
		((ogx_thiscall_removecomplete)(uintptr_t)ogx_g_module.host.remove_complete)(device);
}

/* ---- GIP class-driver description + callbacks ------------------------------ */

static void OGX_STDCALL ogx_gip_register(void *iUsbInit) { (void)iUsbInit; }
static void OGX_STDCALL ogx_gip_attach(void *device);
static void OGX_STDCALL ogx_gip_remove(void *device);

/* ---- FindClassDriver E9 hook target ---------------------------------------- */
/*
 * u803 FindClassDriver @0x41517D VERIFIED (pin_u803.py, frozen bytes
 * 56 B8 B4 27 41 00 BE CC 27 41 00 3B C6 8B C8 73 ...):
 *     for (p = begin; p < end; p += 4) { if (!(d=*p)) continue;
 *         if (Lo(classId)==d->MatchByte0 && Hi(classId)==d->MatchByte1) return d; }
 *     return 0;
 * Reimplement that exact loop (pure C, IRQL-safe, no nested call) so every stock
 * class returns the identical descriptor; only 0xFF81 (GIP, measured on the real
 * device) returns ours. begin/end are INJECTED so a mismatched build fails closed.
 */
uintptr_t OGX_STDCALL ogx_findclassdriver(uint32_t classId)
{
	uint32_t begin = ogx_g_module.host.class_table_begin;
	uint32_t end   = ogx_g_module.host.class_table_end;
	uint32_t addr;

	if ((classId & 0xffffu) == (uint32_t)GDR_PNP_GIP)
		return (uintptr_t)&ogx_g_module.desc;

	for (addr = begin; addr + 4 <= end; addr += 4) {
		uintptr_t d = *(volatile uint32_t *)addr;
		if (!d)
			continue;
		if ((uint8_t)classId == *(volatile uint8_t *)d &&
		    (uint8_t)(classId >> 8) == *((volatile uint8_t *)d + 1))
			return d;
	}
	return 0;
}

/* attach-ran flag (separate from the derived "transport live" state) */
static volatile uint32_t ogx_attach_ran;

static void OGX_STDCALL ogx_gip_attach(void *device)
{
	ogx_attach_ran = 1;
	ogx_g_module.att.in_complete = gdr_in_complete;  /* shared completion (gipdrive.h) */
	ogx_g_module.att.cb_log = 0;                     /* no per-completion CB events    */
	if (gdr_attach_begin(&ogx_g_module.att, device, ogx_usb_submit, &ogx_g_module.ring)) {
		/* refused: previous generation still quiescing -> fail closed, abort THIS
		 * enumeration instead of clobbering a live context. */
		ogx_g_module.att.add_complete(device, (long)(int)0xC0000001L);
	}
}
static void OGX_STDCALL ogx_gip_remove(void *device)
{
	gdr_remove_device(&ogx_g_module.att, device);
}

/* ---- snapshot -> presentation bridge ----------------------------------------
 * gdr_snapshot and og_gamepad share the SAME 18-byte wire layout (asserted).    */
static void ogx_bridge_publish(void)
{
	struct ogx_host_ctx *p = &ogx_g_module.present;
	struct og_gip_port *gp = &ogx_g_module.gport[OGX_TRANSPORT_PORT];
	uint32_t mask = 1u << OGX_TRANSPORT_PORT;
	int live = gdr_transport_live((int)ogx_attach_ran, ogx_g_module.att.in_handle);

	if (live) {
		/* powered-readable = gdr_gip.ready (set once minimal power-on accepted).
		 * Same "powered-ready, NOT input-seen" contract og_gip.h documents. */
		gp->ready = ogx_g_module.gip.ready ? true : false;
		if (ogx_g_module.gip.snapshot_valid) {
			gp->snapshot_valid = true;
			memcpy(&gp->gamepad, &ogx_g_module.gip.snap, sizeof(gp->gamepad));
			gp->seq = ogx_g_module.gip.input_reports;
		}
		p->attached_mask |= mask;
	} else {
		if (p->attached_mask & mask) {
			gp->ready = false;
			gp->snapshot_valid = false;
			memset(&gp->gamepad, 0, sizeof(gp->gamepad));
		}
		p->attached_mask &= ~mask;
	}
}

void ogx_transport_init(void)
{
	struct ogx_host_ctx *p = &ogx_g_module.present;
	uint32_t i;

	/* the six XInput stubs reach THIS presentation ctx */
	ogx_stub_bind_ctx(p);

#ifdef __i386__
	/* chain trampolines: native handles pass through these back to the title.
	 * Declared stdcall (above) so the call site's argument count matches the
	 * original function's `ret N`; the trampoline body tail-jumps and never
	 * returns itself. i386/title-only: on the host-test build the trampolines
	 * are undefined and orig_* stay NULL (the test injects its own fakes). */
	p->orig_XGetDeviceChanges     = ogx_chain_getdevicechanges;
	p->orig_XInputOpen            = ogx_chain_inputopen;
	p->orig_XInputClose           = ogx_chain_inputclose;
	p->orig_XInputGetCapabilities = ogx_chain_getcaps;
	p->orig_XInputGetState        = ogx_chain_getstate;
	p->orig_XInputSetState        = ogx_chain_setstate;
#endif

	/* the GAMEPAD device-type POINTER IDENTITY (host.xdevice_type_gamepad is
	 * the title's 0x4127D8 address, injected; the runtime compares pointer
	 * equality only and never dereferences it). */
	p->xdevice_type_gamepad = ogx_g_module.host.xdevice_type_gamepad;
	for (i = 0; i < OGX_MAX_PORTS; i++)
		p->ports[i] = &ogx_g_module.gport[i];

	gdr_gip_init(&ogx_g_module.gip, 0);
	gdr_ring_reset(&ogx_g_module.ring);

	/* 24-byte VERIFIED class description */
	ogx_g_module.desc.MatchByte0 = 0x81;   /* low byte of measured PNP_CLASS_ID 0xFF81 */
	ogx_g_module.desc.MatchByte1 = 0xFF;   /* high byte                              */
	ogx_g_module.desc.pad[0] = 0xFF; ogx_g_module.desc.pad[1] = 0xFF;
	ogx_g_module.desc.Register       = (uint32_t)(uintptr_t)&ogx_gip_register;
	ogx_g_module.desc.Attach         = (uint32_t)(uintptr_t)&ogx_gip_attach;
	ogx_g_module.desc.RemoveDevice   = (uint32_t)(uintptr_t)&ogx_gip_remove;
	ogx_g_module.desc.TypeInfo       = 0;   /* 0xFF device: AddComplete never reads it */
	ogx_g_module.desc.DispatchTable  = 0;

	/* lifecycle seams persist across re-attach (attach resets per-generation) */
	ogx_g_module.att.add_complete    = ogx_usb_add_complete;
	ogx_g_module.att.cancel_request  = ogx_usb_cancel;
	ogx_g_module.att.remove_complete = ogx_usb_remove_complete;
}

/* ---- per-title-tick pump (single owner thread) ---------------------------- */
void ogx_module_pump(void)
{
	struct gdr_evt ev;
	u32 now;

	while (gdr_ring_pop(&ogx_g_module.ring, &ev)) {
		if (ev.kind == GDR_EVT_RX) {
			gdr_gip_rx(&ogx_g_module.gip, ev.data, (int)ev.len);
		} else if (ev.kind == GDR_EVT_TXDONE && ev.b == GIP_CMD_POWER &&
		           (long)(int)ev.a >= 0) {
			gdr_gip_on_power_done(&ogx_g_module.gip);
		} else if (ev.kind == GDR_EVT_DETACH) {
			gdr_gip_neutralize(&ogx_g_module.gip);   /* reset snapshot/id/tx/seq */
		}
	}

	/* now_ms is UNUSED by gdr_gip_poll (a no-op) -- all timing is
	 * completion-driven. It is read here only to keep the (correctly typed u32
	 * stdcall) injected clock plumbed for a future keepalive; no timing
	 * dependency exists today. */
	now = ogx_g_module.host.now_ms ? ogx_g_module.host.now_ms() : 0u;

	if (gdr_transport_live((int)ogx_attach_ran, ogx_g_module.att.in_handle)) {
		if (ogx_g_module.att.state >= 6u && ogx_g_module.gip.gamepad == 0)
			gdr_gip_qualify_wired(&ogx_g_module.gip);  /* minimal power-on, S-init on done */
		gdr_gip_poll(&ogx_g_module.gip, now);

		u8 out_pkt[64]; int out_n;
		while ((out_n = gdr_tx_drain(&ogx_g_module.gip, out_pkt, 64)) > 0)
			gdr_tx_enqueue(&ogx_g_module.att, out_pkt, out_n);
		gdr_tx_submit_next(&ogx_g_module.att);
	}

	ogx_bridge_publish();
}

/* ---- status for the parent's readback (bits) ------------------------------ */
uint32_t ogx_module_status(void)
{
	uint32_t s = ogx_g_module.installed_hooks;              /* bits 0..7 (0..6 XInput, 7 FindClass) */
	if (ogx_g_module.installed_hooks & (1u << 8)) s |= (1u << 8);
	if (gdr_transport_live((int)ogx_attach_ran, ogx_g_module.att.in_handle)) s |= (1u << 9);
	if (ogx_g_module.gip.snapshot_valid)     s |= (1u << 10);
	if (ogx_g_module.install_failed)         s |= (1u << 11);
	if (ogx_g_module.host.cancel_request == 0) s |= (1u << 12);  /* cancel optional/unresolved */
	return s;
}

_Static_assert(sizeof(struct gdr_snapshot) == 18, "gdr_snapshot 18B");
_Static_assert(sizeof(struct og_gamepad) == 18, "og_gamepad 18B");
