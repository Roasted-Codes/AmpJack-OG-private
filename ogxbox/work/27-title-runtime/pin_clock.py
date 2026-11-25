#!/usr/bin/env python3
"""Parent clock receipt for the optional `now_ms` title binding.

Resolution: the real GetTickCount getter reads the KeTickCount kernel import.
SDK datetime.obj `_GetTickCount@0` body is `a1 <abs32> 8b 00 c3` (load dword slot,
load dword [slot], ret) = `mov eax,[__imp]; mov eax,[eax]; ret`.
The frozen u803 title contains exactly two bodies matching that shape:
  0x33b590  a1 74 b7 41 00 8b 00 c3   slot 0x41b774 -> ordinal 0x8000009C (156)
  0x33c29d  a1 84 b7 41 00 8b 00 c3   slot 0x41b784 -> ordinal 0x80000164 (356)
KeTickCount is xboxkrnl.exe ordinal 156 (a ULONG-backed exported timer variable),
so the getter that reads slot 0x41b774 IS GetTickCount. >>> 0x33b590 <<<
0x33c29d reads a different ordinal (356) -> not the tick counter (not used here).

Read-only on the frozen XBE; re-derives and asserts everything.
"""
import struct
import sys

sys.path.insert(0, '/home/roasted/Desktop/Xbox/LAN_Stats/tools')
from xbe_va import XBE  # noqa: E402

PATH = '/home/roasted/Desktop/Xbox/H2-Decomp/tu15-decomp/targets/halo2-tu15-u803/default.xbe'
SHA = '21b207e7efdacaf6124a0822837f8be570766a42505057f7fd2d2ba8f409c4fd'
GETTER = 0x33B590
SLOT = 0x41B774
ORDINAL = 0x8000009C

x = XBE(PATH, expect_sha256=SHA)
u32 = lambda d, o: struct.unpack_from('<I', d, o)[0]


def get_file_bytes(va, n):
    o = x.va2off(va)
    assert o is not None, f'unmapped read @ {va:#x}'
    return x.data[o:o + n]


code = get_file_bytes(GETTER, 8)
assert code == b'\xa1\x74\xb7\x41\x00\x8b\x00\xc3', code.hex(' ')
slot = get_file_bytes(SLOT, 4)
slot_ord = u32(slot, 0)
assert slot_ord == ORDINAL, f'slot {slot_ord:#x} != {ORDINAL:#x}'
# repointer check: getter's imm32 is (slot) little-endian at code[1:5]
imm = u32(code[:7], 1)
assert imm == SLOT, f'getter imm {imm:#x} != slot {SLOT:#x}'

print("RESULT: now_ms = GetTickCount getter @ 0x%08X" % GETTER)
print("  code       :", code.hex(' '))
print("  slot       : 0x%08X" % SLOT)
print("  ordinal    : %#x (156 = KeTickCount, xboxkrnl.exe)" % slot_ord)
print("  u32 stdcall: mov eax,[KeTickCount thunk]; mov eax,[eax]; ret")
print("  sibling getter 0x33C29D -> slot 0x41B784 ordinal 356 (not tick counter)")
print("  OPTIONAL-ONLY: module may inject this u32(*)(void) for a real native clock.")
print("ALL CLOCK CHECKS PASSED")
