/* SPDX-License-Identifier: GPL-3.0-or-later */
/*
 * Compile-only demonstration of the two i386 call conventions a stage-2 driver
 * must use on the original Xbox. Not linked into the diagnostic module: this
 * proves the instruction encodings clang emits, never behaviour. DISABLED.
 *
 * Convention 1 (kernel import): the Halo 2 u803 XBE resolves its kernel imports
 * into a table at VA 0x41B600 (153 import slots, VERIFIED in LAN_Stats
 * references/u803-addresses.json). A module calls a kernel service indirectly
 * through the slot: `call dword ptr [slot]`. MmAllocateContiguousMemoryEx is
 * slot 0x41B640 (ordinal 166).
 *
 * Convention 2 (title code/data): a game address is an integer constant cast to a
 * function pointer — position-independent, no relocation — and clang calls it as
 * `mov ecx, imm32; call ecx`.
 */
#include <stdint.h>

typedef unsigned int u32;
#define STDCALL __attribute__((stdcall))

#define U803_K_MmAllocateContiguousMemoryEx 0x41B640u
#define PAGE_READWRITE 4u

/* Indirect call through the XBE's own kernel-import slot. */
__attribute__((noinline, used))
void *ogx_alloc_via_thunk_slot(u32 n)
{
    return ((void *(STDCALL *)(u32, u32, u32, u32, u32))
            (*(void **)U803_K_MmAllocateContiguousMemoryEx))
               (n, 0, 0xFFFFFFFFu, 0, PAGE_READWRITE);
}

/* Call to a title function at a fixed u803 address (0x2DB483 is a mere example of
 * a real call site form; the real address must be VERIFIED per exact XBE). */
__attribute__((noinline, used))
void ogx_call_title_absolute(void)
{
    ((void (*)(void))(uintptr_t)0x002DB483u)();
}

/* Force emission regardless of section GC so objdump always sees both. */
__attribute__((used)) static void (*const ogx_call_keep[])(void) = { ogx_call_title_absolute };
__attribute__((used)) static void *(*const ogx_alloc_keep)(u32) = ogx_alloc_via_thunk_slot;
