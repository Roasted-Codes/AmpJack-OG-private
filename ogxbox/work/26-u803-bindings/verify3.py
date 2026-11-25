#!/usr/bin/env python3
"""Final evidence: Add/RemoveComplete epilogues, 0x4127D8 identity via callsite + desc table."""
import struct
import sys

sys.path.insert(0, "/home/roasted/Desktop/Xbox/LAN_Stats/tools")
from xbe_va import XBE, U803_SHA256, fmt  # noqa: E402

XBE_PATH = "/home/roasted/Desktop/Xbox/H2-Decomp/tu15-decomp/targets/halo2-tu15-u803/default.xbe"
SHA256 = "21b207e7efdacaf6124a0822837f8be570766a42505057f7fd2d2ba8f409c4fd"
x = XBE(XBE_PATH, expect_sha256=SHA256)

print("=== AddComplete @0x416992 FULL (tail = ret 4?) ===")
for z in x.dis(0x416992, 60):
    print("  " + fmt(z))
    if z.mnemonic == "ret":
        break
print()

print("=== RemoveComplete @0x4165C6 FULL (tail = ret 0?) ===")
for z in x.dis(0x4165C6, 80):
    print("  " + fmt(z))
    if z.mnemonic == "ret":
        break
print()

# ---- the code that references 0x4127D8: 0x1273DC caller ----
print("=== caller that stores 0x4127D8 (disasm 0x127380..0x127660) ===")
for z in x.dis(0x127380, 120):
    s = fmt(z)
    print("  " + s)
    if z.address > 0x127660:
        break
print()

# ---- second ref: push 0x4127d8 at 0x127620 ----
print("=== aligned data 0x4127D0..0x412850 ===")
for a in range(0x4127D0, 0x412850, 0x10):
    b = x.read(a, 0x10)
    # print each u32 for pointer-or-not readability
    words = [b[i:i+4].hex() for i in range(0, 16, 4)]
    print("  0x%08X  %s" % (a, "  ".join(words)))
