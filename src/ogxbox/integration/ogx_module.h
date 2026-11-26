/* SPDX-License-Identifier: GPL-3.0-or-later */
/*
 * ogx_module.h -- title-resident AmpJack-OG module ABI.
 *
 * The vertical slice: the PROVEN GIP USB transport (ogxbox/gipdriver/gipdrive.h,
 * header-only, address-independent) feeds the existing hardened virtual-XInput
 * presentation (ogx_present.{h,c}) through exactly ONE injected set of title
 * function pointers. No D3D, no XLaunchNewImage, no global XInput/guide code, and
 * NO 0x30000-method addresses from the standalone probe are carried into the
 * title: every title call goes through a VERIFIED u803 VA injected here.
 *
 * Load model: the trainer injector relocates this static-PIE image
 * (R_386_RELATIVE only), fills `struct ogx_mod_host` with the VERIFIED u803 VAs,
 * calls ogx_module_entry() ONCE at title entry (BEFORE XInitDevices enumerates,
 * so install is single-threaded), then calls ogx_module_pump() every title tick
 * from a borrowed loop hook. Install is NOT claimed to be a thread-safe 5-byte
 * atomic patch; its safety comes from running before enumeration on one thread.
 */
#ifndef OGX_MODULE_H
#define OGX_MODULE_H

#include <stdint.h>
#include "ogx_present.h"
#include "../gipdriver/src/gipdrive.h"

/* __thiscall only exists on i386 (the title ABI). On the host-test build the
 * SAME ogx_transport.c compiles with plain function pointers so the production
 * bridge can be driven by an instrumented fake submit/add/remove. */
#ifdef __i386__
#define OGX_THISCALL __attribute__((thiscall))
#define OGX_FASTCALL __attribute__((fastcall))
#else
#define OGX_THISCALL
#define OGX_FASTCALL
#endif

/* ---- the fixed virtual slot the modern GIP pad is published on -------------- */
/*
 * FIXED SLOT = port index 1 ("front port 2"). The player keeps a stock pad on
 * port 1 (index 0); the modern pad is assumed on port 2 (index 1). This is a
 * DOCUMENTED FIXED SLOT, NOT a native-derived physical port: the real
 * port-number -> front-port wiring for a non-hub GIP device is UNKNOWN on this
 * box (binding REPORT §6), so no derivation is faked. ogx_present's
 * native_connected_mask guard still suppresses the virtual device on any port a
 * NATIVE gamepad already owns, so a stock pad can never be "stolen" — the fixed
 * slot is only ever visible when port 1 is not natively occupied.
 */
#define OGX_TRANSPORT_PORT 1u

/* ---- the title function pointers the injector MUST fill --------------------- */
/*
 * VERIFIED bindings (worker26 static proof + verify.py; re-asserted by
 * pin_u803.py against the frozen XBE — do NOT re-research these addresses):
 *   submit_request      = IUsbDevice::SubmitRequest  @ 0x004155BF (__thiscall)
 *   findclassdriver     = USBD_FindClassDriver        @ 0x0041517D (__stdcall,1)
 *   add_complete        = IUsbDevice::AddComplete     @ 0x00416992 (__thiscall, void, ret 4)
 *   remove_complete     = IUsbDevice::RemoveComplete  @ 0x004165C6 (__thiscall, void, ret)
 *   class_table_begin/end = 0x004127B4 / 0x004127CC   (writable XPP)
 *   xdevice_type_gamepad  = 0x004127D8 (the POINTER the title passes as the dtype
 *                           argument; pointer identity, NOT the DWORD stored there)
 * OPTIONAL (fail-closed 0, not called by the close-based transport):
 *   cancel_request      = IUsbDevice::CancelRequest  @ 0 (close_urb chain retires
 *                          in-flight transfers; CancelRequest is not needed)
 *
 * add_complete and remove_complete are REQUIRED, not "safe no-ops": native
 * enumeration must signal AddComplete (once, exact status) so the device leaves
 * the pending-enum list, and native removal must close the class-driver-owned
 * default/IN/OUT endpoints before RemoveComplete (the stack frees only the
 * device address, VERIFIED @0x305ef). entry/install REFUSE to write any byte
 * unless submit_request, add_complete, remove_complete, class_table_begin,
 * class_table_end and a NONZERO xdevice_type_gamepad are all present.
 */
struct ogx_mod_host {
	uint32_t submit_request;      /* 0x4155BF  __thiscall(self=ecx, urb) -> long */
	uint32_t findclassdriver;     /* 0x41517D  __stdcall(classId) -> desc*        */
	uint32_t add_complete;        /* 0x416992  __thiscall(self, status) void     */
	uint32_t cancel_request;      /* 0 (opt)   __thiscall(self, urb) -> long     */
	uint32_t remove_complete;     /* 0x4165C6  __thiscall(self) void             */
	uint32_t class_table_begin;   /* 0x4127B4                                  */
	uint32_t class_table_end;     /* 0x4127CC                                  */

	/* The GAMEPAD device-type POINTER IDENTITY (0x004127D8). Halo passes this
	 * exact address as the `dtype` argument to XGetDeviceChanges/XInputOpen; the
	 * runtime compares address equality only and NEVER dereferences it. A zero
	 * value does NOT mean "unknown pointer" (worker26 proves the identity by two
	 * static references: title init @0x1273DC builds PreallocTypes[0]=0x4127D8,
	 * descTypeInfo @0x412814 lists it first). install REFUSES on 0. */
	uint32_t xdevice_type_gamepad;

	/* injected clock (ms). UNUSED by production: gdr_gip_poll is a no-op and
	 * every state transition is completion-driven, so there is NO timing
	 * dependency. Native GetTickCount is u32 __stdcall, NOT a u64 cast; kept
	 * correctly typed in case a future keepalive ever needs it. 0 is accepted. */
	uint32_t (OGX_STDCALL *now_ms)(void);

	/* F6 critical span (work/32). These are the ADDRESSES OF THE TITLE'S OWN
	 * KERNEL IMPORT SLOTS, not function addresses: the module calls through
	 * *slot exactly like the title does (XInputGetState 0x413C50
	 * `call [0x41B700]` ... 0x413CB0 `mov cl,al; call [0x41B6FC]`).
	 * Pinned from the frozen u803 XBE + XDK 5849 xboxkrnl.lib (work/32
	 * tools/pin_irql.py):
	 *   irql_raise_slot = 0x0041B700  ord 129 _KeRaiseIrqlToDpcLevel@0
	 *                     (stdcall, no args, returns the old KIRQL in AL)
	 *   irql_lower_slot = 0x0041B6FC  ord 161 @KfLowerIrql@4
	 *                     (fastcall, NewIrql in CL)
	 * REQUIRED: ogx_install_hooks refuses on 0, and the freestanding title
	 * build never submits OUT without the span. */
	uint32_t irql_raise_slot;
	uint32_t irql_lower_slot;
};
#define OGX_HAS_IRQL_SPAN 1

/* ---- one title-resident module instance (all static, no heap) --------------- */
struct ogx_module {
	struct ogx_mod_host     host;                      /* injected pointers      */
	struct ogx_host_ctx     present;                   /* ogx_present services   */
	struct og_gip_port      gport[OGX_MAX_PORTS];      /* snapshots the module  */
	struct gdr_gip          gip;                       /* GIP decoder + tx queue */
	struct gdr_ring         ring;                      /* DPC -> main-loop ring  */
	struct gdr_attach_ctx   att;                       /* S0..S5 + lifecycle     */
	struct gdr_class_desc   desc;                      /* 24-byte GIP description */
	volatile uint32_t       attached;                  /* transport live guard    */
	uint32_t                installed_hooks;           /* bitmask of E9s applied  */
	uint32_t                install_failed;            /* fail-closed latch       */
};

extern struct ogx_module ogx_g_module;

/* entry + pump + hook entry points -------------------------------- */
void ogx_transport_init(void);                          /* wire ctx/seams/desc   */
int  ogx_install_hooks(void);                           /* 6 XInput + FC E9 write */
int  ogx_module_entry(void *unused);                    /* .text.entry           */
void ogx_module_pump(void);                             /* per-title-tick        */
void ogx_transport_sync(void);                          /* title-thread generation
                                                         * resync (no ring decode) */
uintptr_t OGX_STDCALL ogx_findclassdriver(uint32_t classId); /* E9 hook target */
uint32_t ogx_module_status(void);                       /* install/transport bitmask */

#endif /* OGX_MODULE_H */
