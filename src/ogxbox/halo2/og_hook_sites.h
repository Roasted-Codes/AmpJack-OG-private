/* SPDX-License-Identifier: GPL-3.0-or-later */
/*
 * og_hook_sites.h -- Halo 2 TU1.5 u803 XInput hook sites (VERIFIED constants).
 *
 * Promoted from the first hook_sites.h. The addresses,
 * original 5 bytes, displaced span and resume VA are re-asserted byte-for-byte
 * against the pinned XBE by ogxbox/integration/detour_plan.py (--xbe path).
 *
 * Target: default.xbe sha256 21b207e7efdacaf6124a0822837f8be570766a42505057f7fd2d2ba8f409c4fd,
 * section XPP (va 0x4127A0, executable+writable). All six functions are the
 * STATICALLY LINKED XID/XInput driver, not kernel imports. stdcall throughout.
 *
 * Detour primitive: replace 5 bytes at `va` with `E9 rel32` -> trampoline.
 * The trampoline re-runs `displaced[0..displaced_len)` then `jmp resume`
 * (resume == va + displaced_len), or takes the virtual path. Only XInputClose's
 * displaced span contains a PC-relative instruction (the `call rel32`); it must
 * be RE-ENCODED at the new address (see trampoline.S / detour_plan.py).
 */
#ifndef OGX_HOOK_SITES_H
#define OGX_HOOK_SITES_H

#include <stdint.h>

/* hazard flags for the displaced span */
#define OGX_HOOK_HAS_PCREL 0x1u  /* span contains a PC-relative branch to re-encode */

typedef struct {
	const char *name;
	uint32_t    va;              /* hook point VA */
	uint8_t     orig5[5];        /* exact bytes to overwrite */
	uint8_t     displaced[16];   /* full instructions re-run on the chain path */
	uint8_t     displaced_len;   /* == resume - va */
	uint32_t    resume;          /* va + displaced_len */
	uint8_t     argc;            /* stdcall arg count (ret N = argc*4) */
	uint8_t     flags;           /* OGX_HOOK_* ; HAS_PCREL for XInputClose */
	/* for HAS_PCREL: the absolute address that displaced PC-relative branch
	 * reached at its ORIGINAL location; the re-encoder must reproduce it. */
	uint32_t    pcrel_target_va;
} ogx_hook_site_t;

static const ogx_hook_site_t OGX_HOOK_SITES[] = {
	{ "XGetDeviceChanges",     0x004139A5,
	  {0x55,0x8B,0xEC,0x56,0x8B},
	  {0x55,0x8B,0xEC,0x56,0x8B,0x75,0x08},                        7, 0x004139AC, 3, 0, 0 },

	{ "XInputOpen",            0x00413A12,
	  {0x55,0x8B,0xEC,0x51,0x8B},
	  {0x55,0x8B,0xEC,0x51,0x8B,0x4D,0x08},                        7, 0x00413A19, 4, 0, 0 },

	/* `8B 4C 24 04` mov ecx,[esp+4] ; `E8 rel32` call -> 0x41493E XID_fCloseDevice.
	 * The call is PC-relative and MUST be re-encoded at a new address. */
	{ "XInputClose",           0x00413A68,
	  {0x8B,0x4C,0x24,0x04,0xE8},
	  {0x8B,0x4C,0x24,0x04,0xE8,0xCD,0x0E,0x00,0x00},              9, 0x00413A71, 1,
	  OGX_HOOK_HAS_PCREL, 0x0041493E },

	{ "XInputGetCapabilities", 0x00413A74,
	  {0x55,0x8B,0xEC,0x83,0xEC},
	  {0x55,0x8B,0xEC,0x83,0xEC,0x48},                             6, 0x00413A7A, 2, 0, 0 },

	/* `53 56 33 DB` push ebx; push esi; xor ebx,ebx ; `FF 15 [0x41b700]`
	 * call dword ptr [abs] -- ABSOLUTE indirect, NOT PC-relative. Moves verbatim
	 * because 0x41b700 is a fixed title VA. */
	{ "XInputGetState",        0x00413C4C,
	  {0x53,0x56,0x33,0xDB,0xFF},
	  {0x53,0x56,0x33,0xDB,0xFF,0x15,0x00,0xB7,0x41,0x00},        10, 0x00413C56, 2, 0, 0 },

	/* `8B 4C 24 04` mov ecx,[esp+4] ; `8D 81 disp32` lea eax,[ecx+disp32] --
	 * register-relative, NOT PC-relative. */
	{ "XInputSetState",        0x00413CBF,
	  {0x8B,0x4C,0x24,0x04,0x8D},
	  {0x8B,0x4C,0x24,0x04,0x8D,0x81,0xA3,0x00,0x00,0x00},        10, 0x00413CC9, 2, 0, 0 },
};

#define OGX_HOOK_SITE_COUNT (sizeof(OGX_HOOK_SITES) / sizeof(OGX_HOOK_SITES[0]))

/* XDEVICE_TYPE_GAMEPAD table pointer (VERIFIED: 0x4127D8 in XPP). NOT hardcoded
 * by the presentation runtime -- injected via ogx_host_ctx (see ogx_present.h)
 * so the runtime never guesses a title pointer. This constant is for the
 * install-plan validator only. */
#define OGX_VA_XDEVICE_TYPE_GAMEPAD 0x004127D8u

#endif /* OGX_HOOK_SITES_H */
