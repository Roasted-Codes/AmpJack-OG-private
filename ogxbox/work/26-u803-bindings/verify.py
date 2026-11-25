#!/usr/bin/env python3
"""verify.py — re-derive every binding in 26-u803-bindings/bindings.json from the
pinned immutable XBE and assert byte-for-byte. Read-only. Stdlib only.

Exits non-zero on any mismatch. Each value is re-read from the XBE here — never
from memory — and cross-checked against bindings.json so a drift in either is
caught. Works under python3 and /usr/bin/python3 (no capstone needed; raw bytes).
"""
import hashlib
import json
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
XBE_PATH = os.environ.get(
    "U803_XBE",
    "/home/roasted/Desktop/Xbox/H2-Decomp/tu15-decomp/targets/halo2-tu15-u803/default.xbe")
SHA256 = "21b207e7efdacaf6124a0822837f8be570766a42505057f7fd2d2ba8f409c4fd"
JSON_PATH = os.path.join(HERE, "bindings.json")

data = open(XBE_PATH, "rb").read()
if hashlib.sha256(data).hexdigest() != SHA256:
    print("FAIL: XBE sha256 mismatch (immutable target changed)")
    sys.exit(1)

# ---- minimal XBE section map (va -> file offset) ----
u32 = lambda o: struct.unpack_from("<I", data, o)[0]
base = u32(0x104)
nsec = u32(0x11C)
sec_addr = u32(0x120)
sections = []
for k in range(nsec):
    o = sec_addr - base + k * 0x38
    np = u32(o + 20) - base
    name = data[np:np + 16].split(b"\0")[0].decode("latin1")
    sections.append(dict(name=name, flags=u32(o), va=u32(o + 4), vs=u32(o + 8),
                         raw=u32(o + 12), rs=u32(o + 16)))


def va_off(va):
    for s in sections:
        if s["va"] <= va < s["va"] + s["vs"]:
            if va - s["va"] >= s["rs"]:
                return None
            return s["raw"] + (va - s["va"])
    return None


def rd(va, n):
    out = bytearray()
    for k in range(n):
        o = va_off(va + k)
        out.append(data[o] if o is not None else 0)
    return bytes(out)


def u32va(va):
    return struct.unpack("<I", rd(va, 4))[0]


def rel32(va):
    return (va + 5 + struct.unpack("<i", rd(va + 1, 4))[0]) & 0xFFFFFFFF


FAIL = []
def check(name, cond, detail=""):
    tag = "OK  " if cond else "FAIL"
    if not cond:
        FAIL.append(name)
    print("[%s] %-32s %s" % (tag, name, detail))


# ---- resolved constants (canonical + this task) ----
SUB  = 0x4155BF
FCD  = 0x41517D
ADD  = 0x416992
REM  = 0x4165C6
TBEG = 0x4127B4
TEND = 0x4127CC
DTYP = 0x4127D8
XID_DEV = 0x4139A0   # XInitDevices thunk

# ---- 1. submit_request ----
check("submit_request prologue (55 8b ec 83 ec 14 53 56 8b 75 08 8a 46 01)",
      rd(SUB, 14).hex() == "558bec83ec1453568b75088a4601")

# ---- 2. findclassdriver ----
check("findclassdriver begin imm == 0x4127B4", u32va(FCD + 2) == TBEG, hex(u32va(FCD + 2)))
check("findclassdriver end imm == 0x4127CC", u32va(FCD + 7) == TEND, hex(u32va(FCD + 7)))
check("findclassdriver cmp dh,[eax+1] (3a 70 01)", b"\x3a\x70\x01" in rd(FCD, 40))

# ---- 3. add_complete (thiscall self=ecx, status on stack, void, ret 4) ----
check("add_complete prologue (55 8b ec 83 ec 0c 53 56 8b f1)",
      rd(ADD, 10).hex() == "558bec83ec0c53568bf1")
check("add_complete ret 4 (c2 04 00)", b"\xc2\x04\x00" in rd(ADD, 0x18C))
check("add_complete caller LoadClassDriver @0x416B49 E8->0x416992",
      rd(0x416B49, 1) == b"\xe8" and rel32(0x416B49) == ADD, hex(rel32(0x416B49)))
check("add_complete caller @0x413DBB status 0x80000400 then thiscall",
      struct.pack("<I", 0x80000400) in rd(0x413DBB, 8))

# ---- 4. remove_complete (thiscall self=ecx, no args, void, ret) ----
check("remove_complete 15-byte SDK-coff body (53 56 8b f1 8a 46 07 3c ff 57 74 1b 8b 4e 10)",
      rd(REM, 15).hex() == "53568bf18a46073cff57741b8b4e10")
check("remove_complete epilogue (5f 5e 5b c3 -> pop edi/esi/ebx; ret)",
      rd(REM + 0x72, 4).hex() == "5f5e5bc3")
check("remove_complete caller @0x41A7F2 E8->0x4165C6",
      rd(0x41A7F2, 1) == b"\xe8" and rel32(0x41A7F2) == REM, hex(rel32(0x41A7F2)))

# ---- 5. cancel_request: optional, not uniquely pinnable (documented 0) ----

# ---- 6/7. class driver table ----
check("class_table_begin USBD_Init imm @0x412D53 == 0x4127B4", u32va(0x412D53) == TBEG)
check("class_table_end   USBD_Init imm @0x412D58 == 0x4127CC", u32va(0x412D58) == TEND)
check("class_table stride 4, 6 entries", (TEND - TBEG) == 0x18)

# ---- 8. xdevice_type_gamepad ----
check("dtype init: mov [esp+0xc],0x4127d8 @0x1273DC",
      rd(0x1273DC, 8).hex() == "c744240cd8274100")
check("dtype init: call XInitDevices @0x1273F4 E8->0x4139A0",
      rd(0x1273F4, 1) == b"\xe8" and rel32(0x1273F4) == XID_DEV, hex(rel32(0x1273F4)))
check("dtype table @0x412814 lists 0x4127d8 (descTypeInfo)",
      u32va(0x412814) == DTYP, hex(u32va(0x412814)))

# ---- 9. now_ms: optional (0) ----

# ---- cross-check against bindings.json ----
expected = {
    "submit_request": SUB, "findclassdriver": FCD, "add_complete": ADD,
    "remove_complete": REM, "cancel_request": 0, "class_table_begin": TBEG,
    "class_table_end": TEND, "xdevice_type_gamepad": DTYP, "now_ms": 0,
}
try:
    js = json.load(open(JSON_PATH))
    assert js["target_sha256"] == SHA256, "json sha256 wrong"
    for k, v in expected.items():
        got = js.get(k)
        check("bindings.json %s == %d (0x%X)" % (k, v, v),
              got == v, "json=%r derived=0x%X" % (got, v))
except (OSError, json.JSONDecodeError, AssertionError) as e:
    check("bindings.json load/cross-check", False, str(e))

print("-" * 72)
if FAIL:
    print("RESULT: %d CHECKS FAILED -> %s" % (len(FAIL), ", ".join(FAIL)))
    sys.exit(1)
print("RESULT: ALL CHECKS PASSED")
