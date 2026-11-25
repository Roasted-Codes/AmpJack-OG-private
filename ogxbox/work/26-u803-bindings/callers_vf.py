#!/usr/bin/env python3
"""Find call xrefs to AddComplete/RemoveComplete, and confirm AddComplete ret-4 byte."""
import struct
import sys

sys.path.insert(0, "/home/roasted/Desktop/Xbox/LAN_Stats/tools")
from xbe_va import XBE, U803_SHA256, fmt  # noqa: E402

XBE_PATH = "/home/roasted/Desktop/Xbox/H2-Decomp/tu15-decomp/targets/halo2-tu15-u803/default.xbe"
SHA256 = "21b207e7efdacaf6124a0822837f8be570766a42505057f7fd2d2ba8f409c4fd"
x = XBE(XBE_PATH, expect_sha256=SHA256)

ADD = 0x416992
REM = 0x4165C6


def callers(target):
    out = []
    for s in x.sections:
        if not (s["flags"] & 0x4) or not s["rawsize"]:
            continue
        blob = x.data[s["raw"]:s["raw"] + s["rawsize"]]
        for i in range(len(blob) - 4):
            if blob[i] == 0xE8:
                rel = struct.unpack_from("<i", blob, i + 1)[0]
                t = (s["va"] + i + 5 + rel) & 0xFFFFFFFF
                if t == target:
                    out.append((s["va"] + i, s["name"]))
        # also call [mem] via ff 15 (indirect) — skip, direct is enough
    return out


for name, tgt in (("AddComplete", ADD), ("RemoveComplete", REM)):
    cs = callers(tgt)
    print("callers of %s @0x%X: %d" % (name, tgt, len(cs)))
    for va, sn in cs:
        # disasm 4 instructions before the E8 (call) to show the setup
        print("  %s @0x%X  sec=%s" % ("  ", va, sn))
        for z in x.dis(va - 8, 3):
            print("      " + fmt(z))

# AddComplete tail: find ret 4
print()
print("AddComplete epilogue bytes (0x416AD0..0x416B1E):")
for a in range(0x416AD0, 0x416B1E, 0x10):
    b = x.read(a, 0x10)
    print("  0x%08X  %s" % (a, b.hex(" ")))
# find c2 04 00 in AddComplete
add = x.read(0x416992, 0x18C)
idx = add.find(b"\xc2\x04\x00")
print("AddComplete 'c2 04 00' (ret 4) at +0x%X (va 0x%X)" % (idx, 0x416992 + idx) if idx >= 0 else "NO ret4")
