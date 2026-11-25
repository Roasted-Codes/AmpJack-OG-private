#!/usr/bin/env python3
"""Verify Add/RemoveComplete bodies, find 0x4127D8 xrefs, resolve GetTickCount/CancelRequest."""
import struct
import sys

sys.path.insert(0, "/home/roasted/Desktop/Xbox/LAN_Stats/tools")
sys.path.insert(0, "/home/roasted/Desktop/Xbox/AmpJack-OG/ogxbox/work/07-binding")
import xapilib_extract as X  # noqa: E402
from xbe_va import XBE, U803_SHA256, fmt  # noqa: E402

XBE_PATH = "/home/roasted/Desktop/Xbox/H2-Decomp/tu15-decomp/targets/halo2-tu15-u803/default.xbe"
SHA256 = "21b207e7efdacaf6124a0822837f8be570766a42505057f7fd2d2ba8f409c4fd"
LIB = "/home/roasted/Desktop/Xbox/H2-Decomp/tu15-decomp/work/xdk5849/XDK/xbox/lib/xapilib.lib"

x = XBE(XBE_PATH, expect_sha256=SHA256)


def r32(va):
    return struct.unpack("<i", x.read(va, 4))[0]


def rel32(va):
    return (va + 5 + r32(va + 1)) & 0xFFFFFFFF


def dis(va, n=20, indent="  "):
    ins = x.dis(va, n)
    for z in ins:
        print(indent + fmt(z))
    return ins


print("=== AddComplete @0x416992 (expect thiscall, ret 4) ===")
dis(0x416992, 20)
print()
print("=== RemoveComplete @0x4165C6 (expect thiscall, ret 0) ===")
dis(0x4165C6, 20)
print()

# ---- xrefs to 0x4127D8 (the XDEVICE_TYPE_GAMEPAD pointer slot) ----
print("=== xrefs to immediate 0x4127D8 (LE d8 27 41 00) in exec sections ===")
needle = b"\xd8\x27\x41\x00"
seen = set()
for s in x.sections:
    if not (s["flags"] & 0x4) or not s["rawsize"]:
        continue
    blob = x.data[s["raw"]:s["raw"] + s["rawsize"]]
    st = 0
    while True:
        i = blob.find(needle, st)
        if i < 0:
            break
        va = s["va"] + i
        if va not in seen:
            seen.add(va)
            # disasm a window ending at va
            for z in x.dis(va - 11, 4):
                print("  " + fmt(z))
            print("   -------")
        st = i + 1
print("  total distinct xref sites:", len(seen))
print()

# ---- data surrounding 0x4127D8 ----
print("=== data at 0x4127C0..0x412830 (class table tail + neighbours) ===")
for a in range(0x4127C0, 0x412830, 0x10):
    b = x.read(a, 0x10)
    vals = b.hex(" ")
    print("  0x%08X  %s" % (a, vals))
print()

# ---- GetTickCount body + match ----
print("=== _GetTickCount@0 (datetime.obj) ===")
d, resolved, symmap = X.parse_archive(LIB)
def get_body(want):
    for name, hoff, doff, size in resolved:
        r = X.parse_coff(d, doff)
        if r is None:
            continue
        sections, symbols = r
        for s in symbols:
            if s["name"] == want and s["sclass"] == 2 and (s["typ"] >> 4) == 0x2 and s["secno"] > 0:
                sec = sections[s["secno"] - 1]
                st = s["value"]
                end = sec["rawsize"]
                for o in symbols:
                    if o is not s and o["secno"] == s["secno"] and o["value"] > st:
                        end = min(end, o["value"])
                return name, sec["data"][st:end]
    return None, None

nm, body = get_body("_GetTickCount@0")
print("  obj=%s body=%s" % (nm, body.hex(" ") if body else None))

# ---- CancelRequest: dump all syms in usbdev.obj sec 31 around it, and its callers ----
print()
print("=== usbdev.obj sec 31 symbols (CancelRequest context) ===")
for name, hoff, doff, size in resolved:
    if "usbdev" not in name:
        continue
    r = X.parse_coff(d, doff)
    if r is None:
        continue
    sections, symbols = r
    for s in symbols:
        if s["secno"] == 31 and s["sclass"] == 2:
            print("   val=0x%03x typ=0x%04x class=%d %s" % (s["value"], s["typ"], s["sclass"], s["name"]))
