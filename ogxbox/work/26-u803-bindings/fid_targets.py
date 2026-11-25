#!/usr/bin/env python3
"""Extract exact SDK COFF bodies for the 4 target symbols and FID-match into u803 xbe.

Read-only. Uses xapilib_extract + xbe_va. Prints SDK bytes + match VA + extended len.
"""
import struct
import sys
import os

sys.path.insert(0, "/home/roasted/Desktop/Xbox/LAN_Stats/tools")
sys.path.insert(0, "/home/roasted/Desktop/Xbox/AmpJack-OG/ogxbox/work/07-binding")
import xapilib_extract as X  # noqa: E402
from xbe_va import XBE, U803_SHA256, fmt  # noqa: E402

XBE_PATH = "/home/roasted/Desktop/Xbox/H2-Decomp/tu15-decomp/targets/halo2-tu15-u803/default.xbe"
SHA256 = "21b207e7efdacaf6124a0822837f8be570766a42505057f7fd2d2ba8f409c4fd"

# candidate libs
LIBS = [
    "/home/roasted/Desktop/Xbox/H2-Decomp/tu15-decomp/work/xdk5849/XDK/xbox/lib/xapilib.lib",
    "/home/roasted/Desktop/Xbox/LAN_Stats/XDK/xbox/lib/xapilib.lib",
]
LIB = next((p for p in LIBS if os.path.exists(p)), None)
print("lib =", LIB)
for p in LIBS:
    print("   ", p, "exists" if os.path.exists(p) else "MISSING")

TARGETS = {
    "?AddComplete@IUsbDevice@@QAEXJ@Z": "IUsbDevice::AddComplete (tree.obj)",
    "?RemoveComplete@IUsbDevice@@QAEXXZ": "IUsbDevice::RemoveComplete (tree.obj)",
    "?CancelRequest@IUsbDevice@@QAEJPAT_URB@@@Z": "IUsbDevice::CancelRequest (usbdev.obj)",
    "_GetTickCount@0": "GetTickCount (datetime.obj)",
}

d, resolved, symmap = X.parse_archive(LIB)
x = XBE(XBE_PATH, expect_sha256=SHA256)


def get_func_bytes(d, resolved, want):
    """Return (objname, bytes) for the defined (secno>0) func named `want`."""
    for name, hoff, doff, size in resolved:
        r = X.parse_coff(d, doff)
        if r is None:
            continue
        sections, symbols = r
        for s in symbols:
            if s["name"] == want and s["sclass"] == 2 and (s["typ"] >> 4) == 0x2 and s["secno"] > 0:
                sec = sections[s["secno"] - 1]
                start = s["value"]
                end = sec["rawsize"]
                for o in symbols:
                    if o is not s and o["secno"] == s["secno"] and o["value"] > start:
                        end = min(end, o["value"])
                return name, sec["data"][start:end]
    return None, None


def exec_regions(x):
    out = []
    for s in x.sections:
        if (s["flags"] & 0x4) and s["rawsize"]:
            out.append((s, x.data[s["raw"]:s["raw"] + s["rawsize"]]))
    return out


def match_all(x, prefix):
    hits = []
    for s, blob in exec_regions(x):
        st = 0
        while True:
            i = blob.find(prefix, st)
            if i < 0:
                break
            hits.append((s["va"] + i, s["name"]))
            st = i + 1
    return hits


def ext_match(x, va, body):
    n = 0
    for b in body:
        try:
            if x.read(va + n, 1)[0] != b:
                break
        except ValueError:
            break
        n += 1
    return n


for sym, label in TARGETS.items():
    print("\n=== %s ===" % label)
    print("sym:", sym)
    objname, body = get_func_bytes(d, resolved, sym)
    if body is None:
        print("  NO DEFINED BODY FOUND")
        continue
    print("  obj=%s len=%d bytes=%s" % (objname, len(body), body.hex(" ")))
    # find prefix match (up to full body, relocation-masking by extended match)
    for k in (len(body), 24, 16, 12, 8):
        pref = body[:k]
        hits = match_all(x, pref)
        if hits:
            break
    if not hits:
        print("  NO MATCH (prefix %d)" % k)
        continue
    for va, sn in hits:
        ext = ext_match(x, va, body)
        print("  MATCH va=0x%08X sec=%s matched=%d/%d" % (va, sn, ext, len(body)))
        for ins in x.dis(va, 6):
            print("      " + fmt(ins))
