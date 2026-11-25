#!/usr/bin/env python3
"""Verify every Halo 2 u803 USB-binding claim in ogxbox/research/binding/REPORT.md
against the pinned XBE bytes. Read-only. Stdlib only. Exits non-zero on any
mismatch. This is the machine-checkable companion to the report: each claim is
re-derived from the XBE here, never from memory.

Requires capstone (present in /usr/bin/python3) only for disassembly strings.
"""
import struct
import sys

XBE_PATH = "/home/roasted/Desktop/Xbox/H2-Decomp/tu15-decomp/targets/halo2-tu15-u803/default.xbe"
SHA256 = "21b207e7efdacaf6124a0822837f8be570766a42505057f7fd2d2ba8f409c4fd"

sys.path.insert(0, "/home/roasted/Desktop/Xbox/LAN_Stats/tools")
from xbe_va import XBE, U803_SHA256, fmt  # noqa: E402

x = XBE(XBE_PATH, expect_sha256=SHA256)
assert x.sha256 == U803_SHA256 == SHA256

u32 = lambda va: struct.unpack("<I", x.read(va, 4))[0]
u8 = lambda va: x.read(va, 1)[0]

FAIL = 0
def check(name, cond, detail=""):
    global FAIL
    ok = "OK  " if cond else "FAIL"
    if not cond:
        FAIL += 1
    print(f"[{ok}] {name} {detail}")

# ---- 1. XPP section placement (read exact header/section map) ---------------
xpp = next(s for s in x.sections if s["name"] == "XPP")
check("XPP section", xpp is not None)
check("XPP flags wr+x+preload", xpp["flags"] == 0x7, hex(xpp["flags"]))
print(f"     XPP va {xpp['va']:#x} vsize {xpp['vsize']:#x} (executable+writable)")

# ---- 2. entry chain: XInitDevices -> USBD_Init -------------------------------
# XInitDevices public thunk at 0x4139A0 must be 'E9 rel32' to 0x412D37
check("XInitDevices @0x4139A0", u8(0x4139A0) == 0xE9)
rel = struct.unpack("<i", x.read(0x4139A1, 4))[0]
check("XInitDevices jmp->USBD_Init", (0x4139A0 + 5 + rel) & 0xFFFFFFFF == 0x412D37,
      f"target {((0x4139A0+5+rel)&0xFFFFFFFF):#x}")

# ---- 3. class driver table (walked by USBD_Init @0x412D52 and FindClassDriver) ----
BEGIN, END = 0x4127B4, 0x4127CC
# USBD_Init loads begin/end as immediates
check("USBD_Init imm begin", u32(0x412D53) == BEGIN)  # 'mov eax,0x4127b4' at 0x412D52
check("USBD_Init imm end",   u32(0x412D58) == END)    # 'mov esi,0x4127cc' at 0x412D57
check("table stride", (END - BEGIN) % 4 == 0 and (END - BEGIN) == 0x18)
entries = [u32(BEGIN + i * 4) for i in range((END - BEGIN) // 4)]
print(f"     class-driver table [0x{BEGIN:x}..0x{END:x}) stride 4:")
for i, p in enumerate(entries):
    d = x.read(p, 12)
    cls, sub = d[1], d[0]  # desc[0]=low byte, desc[1]=high byte (match order)
    reg = struct.unpack("<I", d[4:8])[0]
    at = struct.unpack("<I", d[8:12])[0]
    print(f"       [{i}] desc={p:#x} class={cls:#04x} subclass_field={sub:#04x} "
          f"Register={reg:#x} Attach={at:#x}")
# Houston: XID (class 0x58) present, Hub (0x09) present, MS(0x08), HID(0x03)
classes = [x.read(p, 2)[1] for p in entries]
check("XID class 0x58 in table", 0x58 in classes)
check("hub class 0x09 in table", 0x09 in classes)
check("mass-storage 0x08 in table", 0x08 in classes)
check("HID 0x03 in table", 0x03 in classes)

# ---- 4. FindClassDriver match semantics (disassembly @0x41517D) --------------
# cmp dh,[eax+1]; cmp dl,[eax]  =>  check literal instruction bytes
fcd = x.read(0x41517D, 50)
check("FindClassDriver walks begin/end",
      u32(0x41517F) == BEGIN and u32(0x415184) == END)
# locate the 'cmp dh, byte[eax+1]' opcode (3A 70 01) and 'cmp dl,[eax]' (3A 10)
check("match: cmp dh,[eax+1]", b"\x3a\x70\x01" in fcd)
check("match: cmp dl,[eax]", b"\x3a\x10" in fcd.replace(b"\x3a\x70\x01", b"__"))
check("FindClassDriver ret 4 (stdcall 1 arg)", fcd.rfind(b"\xc2\x04") != -1)

# ---- 5. LoadClassDriver attach contract (@0x416B1E) --------------------------
lc = x.read(0x416B1E, 60)
# 'call [eax+8]' == Attach (ff 50 08); 'push 0x80000400' == unsupported status
check("LoadClassDriver calls Attach", b"\xff\x50\x08" in lc)
check("LoadClassDriver status 0x80000400", struct.pack("<I", 0x80000400) in lc)

# ---- 6. URB header layout (SubmitRequest @0x4155BF) --------------------------
sr = x.read(0x4155BF, 64)
# bytes: 8a 46 01 = mov al,[esi+1] (Function at +1); 39 5e 08 = cmp [esi+8],ebx (CompleteProc)
check("URB Function@+1", b"\x8a\x46\x01" in sr)
check("URB CompleteProc@+8", b"\x39\x5e\x08" in sr)
check("URB CompleteContext@+0xC", b"\x89\x56\x0c" in sr, "(mov [esi+0xc],edx for default context)")
# default completion installed when CompleteProc==NULL
check("default CompleteProc=0x4145C6", struct.pack("<I", 0x4145C6) in x.read(0x4155F0, 12))

# ---- 7. completion callback dispatch (USBD_CompleteRequest @0x415120) --------
cr = x.read(0x415120, 20)
check("CompleteProc(urb, ctx): call ecx after push [eax+0xc],push eax",
      b"\xff\x70\x0c\x50\xff\xd1" in cr)

# ---- 8. IUsbDevice vtable-style member layout (CDeviceTree::AllocDevice @0x4150D0)
# default EP handle read from [ecx+8] in SubmitRequest branch
check("SubmitRequest default EP @ [device+8]",
      b"\x8b\x41\x08" in x.read(0x415637, 8), "mov eax,[ecx+8]")

print("-" * 60)
print(f"RESULT: {'ALL CHECKS PASSED' if FAIL == 0 else str(FAIL)+' CHECKS FAILED'}")
sys.exit(1 if FAIL else 0)
