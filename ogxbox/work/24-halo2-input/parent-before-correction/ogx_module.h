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
 * Load model: the parent trainer/injector relocates this static-PIE image
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

/* ---- the fixed virtual slot the modern GIP pad is published on -------------- */
/*
 * FIXED SLOT = port index 1 ("front port 2"). The owner keeps a stock pad on
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
 * VERIFIED (canonical research + pin_u803.py byte read of the frozen XBE):
 *   submit_request      = IUsbDevice::SubmitRequest @ 0x004155BF (__thiscall)
 *   findclassdriver     = USBD_FindClassDriver   @ 0x0041517D (__stdcall,1)
 *   class_table_begin/end = 0x004127B4 / 0x004127CC  (writable XPP)
 * NOT VERIFIED (fail-closed NULL => attach still streams input, but the module
 *   will NOT signal AddComplete / run the native remove-close chain):
 *   add_complete        = IUsbDevice::AddComplete    @ UNKNOWN (__thiscall,void)
 *   cancel_request      = IUsbDevice::CancelRequest  @ UNKNOWN (__thiscall,long)
 *   remove_complete     = IUsbDevice::RemoveComplete @ UNKNOWN (__thiscall,void)
 *
 * The module refuses to arm (ogx_module_entry returns non-zero, installs nothing)
 * unless submit_request, findclassdriver, class_table_begin and class_table_end
 * are non-zero AND the xdevice_type_gamepad value is set. A missing
 * add_complete/cancel/remove is a SAFE degradation (input still flows; the
 * unplug close-chain and enumeration-completion signalling are skipped), never a
 * crash, and is reported in ogx_module_status() so the parent can see it.
 */
struct ogx_mod_host {
	uint32_t submit_request;      /* 0x4155BF  __thiscall(self=ecx, urb) -> long */
	uint32_t findclassdriver;     /* 0x41517D  __stdcall(classId) -> desc*        */
	uint32_t add_complete;        /* UNKNOWN   __thiscall(self, status)          */
	uint32_t cancel_request;      /* UNKNOWN   __thiscall(self, urb) -> long     */
	uint32_t remove_complete;     /* UNKNOWN   __thiscall(self)                  */
	uint32_t class_table_begin;   /* 0x4127B4                                  */
	uint32_t class_table_end;     /* 0x4127CC                                  */

	/* the value Halo passes for XDEVICE_TYPE_GAMEPAD when it calls
	 * XGetDeviceChanges/XInputOpen. NOT auto-derived: the XPP word at
	 * 0x4127D8 reads 0x00000000 in the frozen image (runtime-populated), so the
	 * exact gamepad device-type value is INFERENCE-only and must be measured by
	 * the parent's first live check before the virtual device is trusted. With
	 * 0 the dtype check in ogx_XGetDeviceChanges never matches, so the virtual
	 * device is silently not published (fail-closed) rather than guessed. */
	uint32_t xdevice_type_gamepad;

	/* injected clock (ms). NULL => 0 (the GIP state machine is completion-driven
	 * and does not need wall time; this is only for future rumble pacing). */
	uint64_t (*now_ms)(void);
};

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
uintptr_t OGX_STDCALL ogx_findclassdriver(uint32_t classId); /* E9 hook target */
uint32_t ogx_module_status(void);                       /* install/transport bitmask */

#endif /* OGX_MODULE_H */
