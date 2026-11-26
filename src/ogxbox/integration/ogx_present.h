/* SPDX-License-Identifier: GPL-3.0-or-later */
/*
 * ogx_present.h -- honest Halo 2 virtual XInput presentation over the hardened
 * GIP adapter (ogxbox/gip/og_gip.h).
 *
 * Data flow (each step is real, none is fabricated):
 *   core/gip.c  --GIP frames-->  struct og_gip_port (hardened snapshot, og_gip.h)
 *   ogx_present --og_gamepad-->  served XINPUT_STATE / CAPABILITIES
 *
 * DESIGN CONTRACT (the "present" decision, made here explicitly):
 *   - `attached_mask` bit i is set ONLY by the USB transport backend when it has
 *     physically enumerated+claimed port i and interrupts are flowing. This
 *     module never sets it. There is no transport backend yet, so the default is
 *     0 -> every port is "no device". A failed USB binding = no-device, never
 *     playable. This file does not pretend USB works.
 *   - `ready`   = og_gip_port.ready  (POWERED-READY: core fired ops->ready).
 *   - `present` = attached(i) && ready(i). The EFFECTIVE published presence is
 *     `present && not native-owned`: a real pad holding a port suppresses the
 *     virtual device ready underneath it. A native->virtual handover defers the
 *     virtual insertion one poll so the game closes the native handle before
 *     opening the virtual one (no rem+ins of one port slot in a single call);
 *     a virtual->native takeover emits a virtual removal and invalidates the
 *     virtual handle. Only an effective rising edge raises an insertion.
 *   - Synthetic handles come from a MONOTONIC, never-recycling arena: a stale
 *     handle address is never reissued, so it stays dead; the arena is finite
 *     (OGX_HANDLE_ARENA) and ogx_XInputOpen fails closed once it is exhausted
 *     (documented limit, not transparent infinite hotplug).
 *   - XInputGetState serves the 18-byte og_gamepad snapshot when
 *     present(i) && snapshot_valid(i); if present but no input yet it returns
 *     success with a zeroed gamepad (the honest boot state, not a fake press).
 *   - XInputSetState takes PXINPUT_FEEDBACK (IN OUT header + Rumble, NOT a bare
 *     4-byte vibration) and, with no motors this milestone, returns
 *     ERROR_NOT_SUPPORTED while writing the same into Header.dwStatus.
 *
 * The runtime reaches everything through ONE injected pointer (struct
 * ogx_host_ctx). There are no absolute self-symbol loads and no guessed title
 * pointers: the trampolines load the ctx base PIC-relatively and the loader
 * fills ctx->xdevice_type_gamepad (VERIFIED 0x4127D8, injected, not guessed).
 */

#ifndef OGX_PRESENT_H
#define OGX_PRESENT_H

#include <stdint.h>
#include <stdbool.h>
#include <string.h>

#include "../halo2/xinput_model.h"
#include "../gip/og_gip.h"

#define OGX_MAX_PORTS     4
#define OGX_HANDLE_ARENA  16   /* 4 ports x up to 4 generations of live handles */

#define OGX_HANDLE_MAGIC  0x4a414b31u  /* "JAK1" */

#ifdef __i386__
#define OGX_STDCALL __attribute__((stdcall))
#else
#define OGX_STDCALL
#endif

/* Synthetic handle = address of an owned, stable object in a fixed arena. Only
 * handles pointing INSIDE this arena are ever intercepted; anything else is
 * chained to the real driver. Allocator is MONOTONIC (never recycles an issued
 * address): a closing handle's address is never reissued in this title session,
 * so a stale pre-unplug handle stays dead forever. The arena is a FINITE
 * resource: once all OGX_HANDLE_ARENA slots have been issued, ogx_XInputOpen
 * fails closed (NULL). generation is diagnostics only -- correctness relies on
 * the non-recycling allocator, not on the stored generation field. */
struct ogx_vhandle {
	uint32_t magic;
	uint32_t gen;     /* generation at issue time (diagnostics) */
	uint32_t port;    /* 0..3 */
	uint32_t live;    /* 1 while the device is present and opened */
};

/* The single injected runtime context. */
struct ogx_host_ctx {
	/* title pointer injected at load (do not guess at runtime) */
	uintptr_t xdevice_type_gamepad;

	/* Chain targets: relocated trampolines that re-run the displaced bytes and
	 * jmp resume. Filled by the installer/loader; when a hook is called these
	 * are how native handles reach the untouched title XID code. */
	uint32_t  (OGX_STDCALL *orig_XGetDeviceChanges)(uintptr_t dtype, uint32_t *ins, uint32_t *rem);
	uintptr_t (OGX_STDCALL *orig_XInputOpen)(uintptr_t dtype, uint32_t port, uint32_t slot, uintptr_t poll);
	void      (OGX_STDCALL *orig_XInputClose)(uintptr_t handle);
	uint32_t  (OGX_STDCALL *orig_XInputGetCapabilities)(uintptr_t handle, uintptr_t caps);
	uint32_t  (OGX_STDCALL *orig_XInputGetState)(uintptr_t handle, uintptr_t state);
	uint32_t  (OGX_STDCALL *orig_XInputSetState)(uintptr_t handle, uintptr_t feedback);

	/* Adapter snapshots: parsed GIP -> og_gamepad. Owned/driven by the transport
	 * ; this module only READS them. */
	struct og_gip_port *ports[OGX_MAX_PORTS];

	/* USB transport truth. bit i = physically attached; NEVER set by this module.
	 * `volatile` makes the store/load visible across threads, but it is NOT a
	 * synchronization primitive and confers no atomicity: any concurrent
	 * access must be serialized by the owning transport (see og_gip.h -- this
	 * layer claims single-owner, NOT lock-free). */
	volatile uint32_t attached_mask;

	/* native devices actually connected, mirrored from the chained
	 * XGetDeviceChanges ((mask & ~rem) | ins). Updated ONLY for the gamepad
	 * dtype (a memory-unit/headset insert must not touch this mask). Used to
	 * keep the virtual device OFF any port a real gamepad already owns. */
	uint32_t native_connected_mask;

	/* presentation state (owned here) */
	struct ogx_vhandle vh[OGX_HANDLE_ARENA];
	uint32_t next_handle;                /* monotonic allocator cursor (never reused) */
	uint32_t gen[OGX_MAX_PORTS];         /* issued generation per port */
	uint32_t prev_present[OGX_MAX_PORTS];/* EFFECTIVE presence last tick:
	                                      * present && !native-owned (edge detect) */
	uint32_t served_packet[OGX_MAX_PORTS];
	uint32_t last_served_seq[OGX_MAX_PORTS];
	uint32_t last_served_gen[OGX_MAX_PORTS]; /* generation that last_served_seq belongs to */

	/* diagnostics */
	uint32_t insertion_edges;
	uint32_t removal_edges;
	uint32_t forged_handles;

	/* Rumble: desired motor speeds (wLeft | wRight << 16) written by the
	 * virtual XInputSetState, consumed by ogx_module_pump. Title thread only. */
	uint32_t rumble_want[OGX_MAX_PORTS];
	uint32_t rumble_calls;        /* virtual SetState calls accepted        */
	uint32_t rumble_hevent;       /* hEvent of the first call (never signalled) */
	uint32_t rumble_hevent_seen;
};

/* whether a port is "present" under the decided contract */
bool ogx_port_present(const struct ogx_host_ctx *ctx, uint32_t port);

/* Transport-reported loss of the physical device behind `port` (generation
 * change: unplug, fast replug, or a lifecycle event lost to ring overflow).
 * Immediately kills every live synthetic handle of that port, so
 * GetState/GetCapabilities/SetState on them return DEVICE_NOT_CONNECTED even
 * before the title's next XGetDeviceChanges. It does NOT touch prev_present:
 * the game's removal edge is still reported by the next XGetDeviceChanges
 * (the caller must also drop attached_mask until that edge is reported).
 * Title thread only (same owner as the six entry points). */
void ogx_present_port_lost(struct ogx_host_ctx *ctx, uint32_t port);

/* The six intercepted entry points. Each one discriminates the handle/value and
 * either serves the virtual path or chains to orig_* (never swallows native). */
uint32_t  ogx_XGetDeviceChanges(struct ogx_host_ctx *ctx, uintptr_t dtype,
	                                uint32_t *ins, uint32_t *rem);
uintptr_t ogx_XInputOpen(struct ogx_host_ctx *ctx, uintptr_t dtype,
	                         uint32_t port, uint32_t slot, uintptr_t poll);
void      ogx_XInputClose(struct ogx_host_ctx *ctx, uintptr_t handle);
uint32_t  ogx_XInputGetCapabilities(struct ogx_host_ctx *ctx, uintptr_t handle,
	                                    uintptr_t caps);
uint32_t  ogx_XInputGetState(struct ogx_host_ctx *ctx, uintptr_t handle,
	                             uintptr_t state);
uint32_t  ogx_XInputSetState(struct ogx_host_ctx *ctx, uintptr_t handle,
	                             uintptr_t feedback);

#endif /* OGX_PRESENT_H */
