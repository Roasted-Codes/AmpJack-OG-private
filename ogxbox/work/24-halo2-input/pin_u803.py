#!/usr/bin/env python3
"""Read-only pin of the u803 USBD/XInput binding bytes from the frozen XBE.

VERIFIES (not just dumps) every value the module depends on, from the immutable
image (sha256 asserted), and exits non-zero on any mismatch so a partial dump can
never be labelled PASS. Bindings are the worker26 static receipts (bindings.json /
verify.py) — no duplicate research:

  USBD_FindClassDriver      0x41517D   (class-match hook site + begin/end imm)
  IUsbDevice::SubmitRequest 0x4155BF   (thiscall URB submit)
  IUsbDevice::AddComplete   0x416992   (thiscall, void, ret 4)   [REQUIRED]
  IUsbDevice::RemoveComplete0x4165C6   (thiscall, void)          [REQUIRED]
  class-driver table        0x4127B4..0x4127CC  (6 entries, stride 4)
  XDEVICE_TYPE_GAMEPAD      0x4127D8   (POINTER identity, not its DWORD)
  six XInput hook sites                  (cross-check)

The instruction-length decoder is cosmetic display only; it is fully bounded and
cannot raise on a truncated tail (never reads past the buffer). Stdlib only.
"""
import hashlib
import struct
import sys

U803_SHA256 = "21b207e7efdacaf6124a0822837f8be570766a42505057f7fd2d2ba8f409c4fd"
XBE = "/home/roasted/Desktop/Xbox/H2-Decomp/tu15-decomp/targets/halo2-tu15-u803/default.xbe"


def modrm_len(b):
    """Length of a modrm(+SIB+disp) group given the modrm byte at b[0]; bounded."""
    if len(b) < 2:
        return 1
    m = (b[1] >> 6) & 3
    rm = b[1] & 7
    ln = 2
    if m == 3:
        return ln
    if rm == 4:  # SIB
        if len(b) < 3:
            return None  # truncated: cannot decode SIB
        sib = b[2]
        ln += 1
        base = sib & 7
        if m == 0 and base == 5:
            ln += 4
    elif m == 0 and rm == 5:
        ln += 4  # disp32, no base
    elif m == 1:
        ln += 1  # disp8
    elif m == 2:
        ln += 4  # disp32
    return ln


def decode_one(b, pc):
    op = b[0]
    if 0x50 <= op <= 0x57:
        return 1, False, 0, "push r32"
    if op == 0x85:
        return modrm_len(b), False, 0, "test"
    if op in (0x8B, 0x89):
        return modrm_len(b), False, 0, "mov"
    if op == 0x33:
        return modrm_len(b), False, 0, "xor"
    if op == 0x2B:
        return modrm_len(b), False, 0, "sub"
    if op == 0x83:
        l = modrm_len(b); return None if l is None else l + 1, False, 0, "grp1 imm8"
    if op == 0x81:
        l = modrm_len(b); return None if l is None else l + 4, False, 0, "grp1 imm32"
    if op == 0x8D:
        return modrm_len(b), False, 0, "lea"
    if op == 0xFF:
        return modrm_len(b), False, 0, "call/jmp/inc r/m"
    if op == 0xE8:
        return (5, True, (pc + 5 + struct.unpack_from("<i", b, 1)[0]) & 0xFFFFFFFF,
                "call rel32") if len(b) >= 5 else (None, False, 0, "call rel32")
    if op == 0xE9:
        return (5, True, (pc + 5 + struct.unpack_from("<i", b, 1)[0]) & 0xFFFFFFFF,
                "jmp rel32") if len(b) >= 5 else (None, False, 0, "jmp rel32")
    if op == 0xEB:
        return (2, True, (pc + 2 + struct.unpack_from("<b", b, 1)[0]) & 0xFFFFFFFF,
                "jmp rel8") if len(b) >= 2 else (None, False, 0, "jmp rel8")
    if op == 0x0F and len(b) > 1 and 0x80 <= b[1] <= 0x8F:
        return (6, True, (pc + 6 + struct.unpack_from("<i", b, 2)[0]) & 0xFFFFFFFF,
                "jcc rel32") if len(b) >= 6 else (None, False, 0, "jcc rel32")
    if op == 0xC3:
        return 1, False, 0, "ret"
    if op == 0xC2:
        return 3, False, 0, "ret N"
    if op in (0xB8, 0xBE, 0xBF, 0xB9, 0xBA):
        return 5, False, 0, "mov r,imm32"
    if op == 0x3B:
        return modrm_len(b), False, 0, "cmp"
    if op in (0x75, 0x74):  # jne/je rel8
        return (2, True, (pc + 2 + struct.unpack_from("<b", b, 1)[0]) & 0xFFFFFFFF,
                "jcc rel8") if len(b) >= 2 else (None, False, 0, "jcc rel8")
    if op == 0x88:
        return modrm_len(b), False, 0, "mov8"
    if op == 0x8A:
        return modrm_len(b), False, 0, "mov8b"
    if op == 0x0F and len(b) > 1 and 0xB6 <= b[1] <= 0xBF:  # movzx (0x0F prefix +1)
        l = modrm_len(b[1:])
        return (None if l is None else l + 1), False, 0, "movzx"
    return None  # unknown opcode -> stop (not an error)


def xbe_sections(data):
    u32 = lambda o: struct.unpack_from("<I", data, o)[0]
    base = u32(0x104)
    nsec = u32(0x11C)
    sec_addr = u32(0x120)
    secs = []
    for k in range(nsec):
        o = sec_addr - base + k * 0x38
        np = u32(o + 20) - base
        secs.append(dict(name=data[np:np + 16].split(b"\0")[0].decode("latin1"),
                         flags=u32(o), va=u32(o + 4), vs=u32(o + 8),
                         raw=u32(o + 12), rs=u32(o + 16)))
    return secs


def main():
    data = open(XBE, "rb").read()
    got = hashlib.sha256(data).hexdigest()
    secs = xbe_sections(data)
    u32 = lambda o: struct.unpack_from("<I", data, o)[0]
    fails = []

    def va_off(va):
        for s in secs:
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

    def check(name, cond, detail=""):
        tag = "OK  " if cond else "FAIL"
        if not cond:
            fails.append(name)
        print("[%s] %-40s %s" % (tag, name, detail))

    print("sha256:", "MATCH" if got == U803_SHA256 else "MISMATCH " + got)
    check("XBE sha256", got == U803_SHA256, got)

    SUB = 0x4155BF
    FCD = 0x41517D
    ADD = 0x416992
    REM = 0x4165C6
    TBEG = 0x4127B4
    TEND = 0x4127CC
    DTYP = 0x4127D8

    def dump(va, label, n=16, decode=False):
        b = rd(va, n)
        s = next((x for x in secs if x["va"] <= va < x["va"] + x["vs"]), None)
        print("%-28s va=0x%08X sec=%s flags=0x%x" %
              (label, va, s["name"] if s else "?", s["flags"] if s else 0))
        print("   bytes: " + " ".join("%02X" % x for x in b))
        if decode:
            off = 0
            while off < n:
                r = decode_one(bytes(b[off:]), va + off)
                if r is None or r[0] is None or off + r[0] > n:
                    print("    +0x%02x  (decode stop: truncated/unhandled)" % off)
                    break
                ln, isp, tgt, desc = r
                print("    +0x%02x 0x%08X  %-14s %s" %
                      (off, va + off, desc, " ".join("%02X" % x for x in b[off:off + ln])))
                off += ln
        print()

    # ---- REQUIRED binding byte-asserts (worker26 receipts) ----
    print("=== REQUIRED binding assertions ===")
    check("FindClassDriver orig5 (56 B8 B4 27 41)", rd(FCD, 5) == bytes.fromhex("56B8B42741"),
          rd(FCD, 5).hex(" "))
    check("FindClassDriver begin imm == 0x4127B4", u32va(FCD + 2) == TBEG, hex(u32va(FCD + 2)))
    check("FindClassDriver end imm == 0x4127CC", u32va(FCD + 7) == TEND, hex(u32va(FCD + 7)))
    submit_prefix = bytes.fromhex("558bec83ec1453568b75088a460133db")
    check("SubmitRequest prologue (" + submit_prefix.hex(" ").upper() + ")",
          rd(SUB, len(submit_prefix)) == submit_prefix,
          rd(SUB, len(submit_prefix)).hex(" "))
    check("AddComplete @0x416992 prologue (55 8B EC 83 EC 0C 53 56 8B F1)",
          rd(ADD, 10) == bytes.fromhex("558bec83ec0c53568bf1"), rd(ADD, 10).hex(" "))
    check("AddComplete ret 4 (c2 04 00) present", b"\xc2\x04\x00" in rd(ADD, 0x18C))
    check("AddComplete caller USBD_LoadClassDriver @0x416B49 E8->0x416992",
          rd(0x416B49, 1) == b"\xe8" and rel32(0x416B49) == ADD, hex(rel32(0x416B49)))
    check("RemoveComplete @0x4165C6 body (53 56 8B F1 8A 46 07 3C FF 57 74 1B 8B 4E 10)",
          rd(REM, 15) == bytes.fromhex("53568bf18a46073cff57741b8b4e10"), rd(REM, 15).hex(" "))
    check("RemoveComplete epilogue (5F 5E 5B C3)", rd(REM + 0x72, 4) == bytes.fromhex("5f5e5bc3"))
    check("RemoveComplete caller @0x41A7F2 E8->0x4165C6",
          rd(0x41A7F2, 1) == b"\xe8" and rel32(0x41A7F2) == REM, hex(rel32(0x41A7F2)))
    check("class table begin imm @0x412D53 == 0x4127B4", u32va(0x412D53) == TBEG)
    check("class table end imm @0x412D58 == 0x4127CC", u32va(0x412D58) == TEND)
    check("class table 6 entries stride 4", (TEND - TBEG) == 0x18)

    # ---- XDEVICE_TYPE_GAMEPAD: POINTER identity, not the DWORD ----
    print("=== XDEVICE_TYPE_GAMEPAD (pointer identity) ===")
    check("dtype init @0x1273DC mov [esp+0xc],0x4127D8",
          rd(0x1273DC, 8) == bytes.fromhex("c744240cd8274100"), rd(0x1273DC, 8).hex(" "))
    check("dtype init call XInitDevices @0x1273F4 E8->0x4139A0",
          rd(0x1273F4, 1) == b"\xe8" and rel32(0x1273F4) == 0x4139A0, hex(rel32(0x1273F4)))
    check("descTypeInfo @0x412814 lists 0x4127D8 first", u32va(0x412814) == DTYP,
          hex(u32va(0x412814)))
    print("  note: DWORD @0x4127D8 = 0x%08X (runtime BSS0 is expected; identity is the\n"
          "        POINTER 0x4127D8, proven by the two static references above, not by an\n"
          "        alive value)." % u32va(DTYP))

    # ---- informational dumps (cosmetic; bounded decoder) ----
    dump(FCD, "USBD_FindClassDriver", 24, decode=True)
    dump(SUB, "IUsbDevice::SubmitRequest", 16, decode=True)
    dump(0x416B1E, "USBD_LoadClassDriver", 16, decode=True)

    print("=== XInput hook sites (cross-check) ===")
    SITES = [
        ("XGetDeviceChanges", 0x004139A5), ("XInputOpen", 0x00413A12),
        ("XInputClose", 0x00413A68), ("XInputGetCapabilities", 0x00413A74),
        ("XInputGetState", 0x00413C4C), ("XInputSetState", 0x00413CBF),
    ]
    for name, va in SITES:
        print("  %-22s 0x%08X  %s" % (name, va, " ".join("%02X" % x for x in rd(va, 10))))

    print("=" * 72)
    if fails:
        print("PIN: %d CHECKS FAILED -> %s" % (len(fails), ", ".join(fails)))
        return 1
    print("PIN: ALL CHECKS MATCH")
    return 0


if __name__ == "__main__":
    sys.exit(main())
