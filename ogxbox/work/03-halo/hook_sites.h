/* AmpJack OG - Halo 2 u803 XInput hook sites (constant, machine-verifiable). */
#ifndef AMPJACK_OG_HOOK_SITES_H
#define AMPJACK_OG_HOOK_SITES_H

#include <stdint.h>

/* Every address is an Xbox VA in halo2-tu15-u803 default.xbe
 * (sha256 21b207e7...), section XPP (va 0x4127A0.., executable+writable).
 * All XInput/XGetDeviceChanges code is STATICALLY LINKED into the XPP section,
 * not imported from the kernel. stdcall (WINAPI) throughout.
 *
 * Detour primitive: replace 5 bytes at `va` with `E9 rel32` to our trampoline.
 * The trampoline must re-execute `displaced[displaced_len]` then jmp `resume`,
 * OR take the virtual path. `resume = va + displaced_len`.
 */

typedef struct {
    const char  *name;
    uint32_t     va;              /* hook point VA */
    uint8_t      orig5[5];        /* exact bytes to overwrite */
    uint8_t      displaced[16];   /* full instruction bytes to re-run (chain case) */
    uint8_t      displaced_len;   /* == resume - va */
    uint32_t     resume;          /* va + displaced_len */
    uint8_t      argc;            /* stdcall arg count (for ret N, N=argc*4) */
} ampjack_hook_site_t;

static const ampjack_hook_site_t AMPJACK_HOOK_SITES[] = {
    /* XGetDeviceChanges(DeviceType, &insert, &removes); ret 12; prologue push ebp */
    { "XGetDeviceChanges", 0x004139A5,
      {0x55,0x8B,0xEC,0x56,0x8B},
      {0x55,0x8B,0xEC,0x56,0x8B,0x75,0x08}, 7, 0x004139AC, 3 },

    /* XInputOpen(DeviceType, port, slot, &poll); ret 16; prologue push ebp */
    { "XInputOpen", 0x00413A12,
      {0x55,0x8B,0xEC,0x51,0x8B},
      {0x55,0x8B,0xEC,0x51,0x8B,0x4D,0x08}, 7, 0x00413A19, 4 },

    /* XInputClose(handle); ret 4; no prologue (mov ecx,[esp+4]; call ...) */
    { "XInputClose", 0x00413A68,
      {0x8B,0x4C,0x24,0x04,0xE8},
      {0x8B,0x4C,0x24,0x04,0xE8,0xCD,0x0E,0x00,0x00}, 9, 0x00413A71, 1 },

    /* XInputGetCapabilities(handle, &caps); ret 8; prologue push ebp */
    { "XInputGetCapabilities", 0x00413A74,
      {0x55,0x8B,0xEC,0x83,0xEC},
      {0x55,0x8B,0xEC,0x83,0xEC,0x48}, 6, 0x00413A7A, 2 },

    /* XInputGetState(handle, &state); ret 8; prologue push ebx/push esi */
    { "XInputGetState", 0x00413C4C,
      {0x53,0x56,0x33,0xDB,0xFF},
      {0x53,0x56,0x33,0xDB,0xFF,0x15,0x00,0xB7,0x41,0x00}, 10, 0x00413C56, 2 },

    /* XInputSetState(handle, &feedback); ret 8; no prologue (mov ecx,[esp+4]) */
    { "XInputSetState", 0x00413CBF,
      {0x8B,0x4C,0x24,0x04,0x8D},
      {0x8B,0x4C,0x24,0x04,0x8D,0x81,0xA3,0x00,0x00,0x00}, 10, 0x00413CC9, 2 },
};
#define AMPJACK_HOOK_SITE_COUNT (sizeof(AMPJACK_HOOK_SITES)/sizeof(AMPJACK_HOOK_SITES[0]))

/* Disabled-by-default enable flag: a loader-mapped 1-byte VADDR patch.
 * 0 = pass through to original XID code (no virtual controller).
 * 1 = intercept and serve ampjack_input_snapshot_t. */
#define AMPJACK_ENABLE_FLAG (*(volatile uint8_t *)0x00000000u /* patched by loader */)

#endif /* AMPJACK_OG_HOOK_SITES_H */
