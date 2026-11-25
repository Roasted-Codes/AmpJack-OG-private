#!/usr/bin/env python3
"""Exploratory pin of the 4 unresolved bindings in halo2-tu15-u803/default.xbe.

Read-only. Prints candidate VAs + evidence; does not commit to a mapping.
"""
import struct
import sys

sys.path.insert(0, "/home/roasted/Desktop/Xbox/LAN_Stats/tools")
from xbe_va import XBE, U803_SHA256, fmt  # noqa: E402

XBE_PATH = "/home/roasted/Desktop/Xbox/H2-Decomp/tu15-decomp/targets/halo2-tu15-u803/default.xbe"
SHA256 = "21b207e7efdacaf6124a0822837f8be570766a42505057f7fd2d2ba8f409c4fd"

x = XBE(XBE_PATH, expect_sha256=SHA256)


def u8(va):
    return x.read(va, 1)[0]


def u32(va):
    return struct.unpack("<I", x.read(va, 4))[0]


def r32(va):
    return struct.unpack("<i", x.read(va, 4))[0]


def rel32_target(op_va):
    return (op_va + 5 + r32(op_va + 1)) & 0xFFFFFFFF


def dis(va, n=40):
    for ins in x.dis(va, n):
        print("   " + fmt(ins))


print("=== USBD_LoadClassDriver @0x416B1E (find AddComplete call) ===")
dis(0x416B1E, 40)
print()

print("=== XID Attach @0x414F22 (XID driver; find AddComplete/RemoveComplete) ===")
dis(0x414F22, 60)
print()
