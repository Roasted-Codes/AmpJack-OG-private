#!/usr/bin/env python3
"""Verify every AmpJack hook site against halo2-tu15-u803 default.xbe bytes.

Read-only on the XBE. Imports the shared XBE loader from LAN_Stats/tools.
Asserts the exact 5-byte original at each hook point, the displaced-bytes span,
and the resume address (va + displaced_len). Prints the `E9 rel32` to write.

Usage: verify_hooks.py [path/to/u803/default.xbe]
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, "/home/roasted/Desktop/Xbox/LAN_Stats/tools")
from xbe_va import XBE, U803_SHA256  # noqa: E402

DEFAULT_XBE = "/home/roasted/Desktop/Xbox/H2-Decomp/tu15-decomp/targets/halo2-tu15-u803/default.xbe"

# (name, va, arg count, ret N) — byte-level data re-derived independently here;
# duplicate of hook_sites.h on purpose so each file can be checked standalone.
SITES = [
    ("XGetDeviceChanges",    0x004139A5, 3),
    ("XInputOpen",           0x00413A12, 4),
    ("XInputClose",          0x00413A68, 1),
    ("XInputGetCapabilities",0x00413A74, 2),
    ("XInputGetState",       0x00413C4C, 2),
    ("XInputSetState",       0x00413CBF, 2),
]

# Exact 5-byte original (VERIFIED from XBE hex dump at dispatch time).
ORIG5 = {
    "XGetDeviceChanges":    "55 8B EC 56 8B",
    "XInputOpen":           "55 8B EC 51 8B",
    "XInputClose":          "8B 4C 24 04 E8",
    "XInputGetCapabilities":"55 8B EC 83 EC",
    "XInputGetState":       "53 56 33 DB FF",
    "XInputSetState":       "8B 4C 24 04 8D",
}
# Full displaced instruction bytes to re-run when chaining to the original.
DISPLACED = {
    "XGetDeviceChanges":     ("55 8B EC 56 8B 75 08", 0x004139AC),
    "XInputOpen":            ("55 8B EC 51 8B 4D 08", 0x00413A19),
    "XInputClose":           ("8B 4C 24 04 E8 CD 0E 00 00", 0x00413A71),
    "XInputGetCapabilities": ("55 8B EC 83 EC 48", 0x00413A7A),
    "XInputGetState":        ("53 56 33 DB FF 15 00 B7 41 00", 0x00413C56),
    "XInputSetState":        ("8B 4C 24 04 8D 81 A3 00 00 00", 0x00413CC9),
}


def main(argv):
    path = argv[1] if len(argv) > 1 else DEFAULT_XBE
    x = XBE(path, expect_sha256=U803_SHA256)

    # Section address-space fact: all six sites must be inside XPP (exec+writable).
    xpp = next(s for s in x.sections if s["name"] == "XPP")
    print(f"XPP section: va {xpp['va']:#x} vsize {xpp['vsize']:#x} "
          f"flags {xpp['flags']:#x} (exec={bool(xpp['flags'] & 4)}, writable={bool(xpp['flags'] & 1)})")

    ok = True
    for name, va, argc in SITES:
        # 1. section check
        in_xpp = xpp["va"] <= va < xpp["va"] + xpp["vsize"]
        # 2. original 5 bytes
        orig = x.read(va, 5).hex(" ").upper()
        orig_match = orig == ORIG5[name]
        # 3. displaced span + resume
        disp, resume = DISPLACED[name]
        disp_bytes = bytes.fromhex(disp)
        got_disp = x.read(va, len(disp_bytes)).hex(" ").upper()
        disp_match = got_disp == disp and resume == va + len(disp_bytes)
        # 4. ret N == argc*4 (stdcall)
        ret = x.read(resume + 0, 1) if disp_match else b""
        # find the `ret` imm16: read a few bytes past resume
        tail = x.read(resume, 16)
        ret_expected = (argc * 4).to_bytes(2, "little")
        ret_found = (b"\xC2" + ret_expected) in tail or (b"\xC3") in tail and argc == 0

        status = "OK" if (in_xpp and orig_match and disp_match) else "MISMATCH"
        if not (in_xpp and orig_match and disp_match):
            ok = False
        print(f"{status:9} {name:<22} va={va:#010x} orig5={orig} "
              f"disp[{len(disp_bytes)}] resume={resume:#x} argc={argc} in_xpp={in_xpp}")
        if not orig_match:
            print(f"      expected orig5={ORIG5[name]}")
        if not disp_match:
            print(f"      expected disp={disp} got={got_disp}")

    print("\n" + ("ALL ASSERTIONS PASSED" if ok else "SOME ASSERTIONS FAILED"))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main(sys.argv)
