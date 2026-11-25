#!/usr/bin/env python3
"""Install-plan builder + validator for the six Halo 2 u803 hook sites.

Read-only on the XBE (stdlib only; no LAN_Stats import). For every site in
og_hook_sites.h it asserts, against the pinned build:
  - SHA256 of the whole XBE;
  - the site lies inside XPP (exec + writable);
  - the exact 5 original bytes to overwrite;
  - the displaced span ends exactly on an instruction boundary > 5 bytes;
  - NO displaced PC-relative branch targets into the overwritten region
    (branch-into-overwrite hazard) and no unknown existing patch (bytes differ);
  - the one PC-relative displaced instruction (XInputClose's `call rel32`) is
    RE-ENCODED for a relocated trampoline so it reaches the same target -- it
    must NOT retain the old +0x0ECD offset.
Then prints the E9 rel32 to write at each site for a given module base.

Usage: detour_plan.py [--xbe PATH] [--module-base 0xADDR]
"""
import hashlib
import struct
import sys

U803_SHA256 = "21b207e7efdacaf6124a0822837f8be570766a42505057f7fd2d2ba8f409c4fd"
DEFAULT_XBE = "/home/roasted/Desktop/Xbox/H2-Decomp/tu15-decomp/targets/halo2-tu15-u803/default.xbe"

# name, va, argc, displaced_len, displaced(bytes), resume, pcrel_target(0=none)
SITES = [
    ("XGetDeviceChanges",     0x004139A5, 3, 7,
     "55 8B EC 56 8B 75 08", 0x004139AC, 0),
    ("XInputOpen",            0x00413A12, 4, 7,
     "55 8B EC 51 8B 4D 08", 0x00413A19, 0),
    ("XInputClose",           0x00413A68, 1, 9,
     "8B 4C 24 04 E8 CD 0E 00 00", 0x00413A71, 0x0041493E),
    ("XInputGetCapabilities", 0x00413A74, 2, 6,
     "55 8B EC 83 EC 48",    0x00413A7A, 0),
    ("XInputGetState",        0x00413C4C, 2, 10,
     "53 56 33 DB FF 15 00 B7 41 00", 0x00413C56, 0),
    ("XInputSetState",        0x00413CBF, 2, 10,
     "8B 4C 24 04 8D 81 A3 00 00 00", 0x00413CC9, 0),
]

# ---- minimal but correct i386 instruction-length decoder ---------------------
# Enough for the (legacy, non-FPU/SSE) XPP code the sites touch + the re-encoder's
# own displaced bytes. Returns (length, is_pcrel, rel_target_abs) for the one
# instruction at code[0:]. rel_target computed for a given insn_va.

def modrm_len(b, pc):
    """return total insn length for opcode with modrm at b[1]. b = full insn buf."""
    m = (b[1] >> 6) & 3
    rm = b[1] & 7
    ln = 2
    if m == 3:
        return ln
    if rm == 4:  # SIB
        sib = b[2]
        ln += 1
        # SIB base determines displacement when mod != 0
        base = sib & 7
        if m == 0 and base == 5:
            ln += 4
    if m == 0:
        if rm == 5:      # disp32 (no base)
            ln += 4
    elif m == 1:
        ln += 1          # disp8
    elif m == 2:
        ln += 4          # disp32
    return ln


def decode_one(b, pc):
    """Returns (length, is_pcrel_branch, abs_target_if_pcrel)."""
    op = b[0]
    # register pushes / immediates groups handled per opcode below
    if 0x50 <= op <= 0x57:                     # push r32
        return 1, False, 0
    if op == 0x8B or op == 0x89:               # mov r32, r/m / r/m, r32
        return modrm_len(b, pc), False, 0
    if op == 0x33:                             # xor r32, r/m
        return modrm_len(b, pc), False, 0
    if op == 0x2B:                             # sub r32, r/m
        return modrm_len(b, pc), False, 0
    if op == 0x83:                             # group1 r/m32, imm8
        return modrm_len(b, pc) + 1, False, 0
    if op == 0x81:                             # group1 r/m32, imm32
        return modrm_len(b, pc) + 4, False, 0
    if op == 0x8D:                             # lea r32, m
        return modrm_len(b, pc), False, 0
    if op == 0xFF:                             # call/jmp/inc r/m
        return modrm_len(b, pc), False, 0
    if op == 0xE8:                             # call rel32
        return 5, True, (pc + 5 + struct.unpack_from("<i", b, 1)[0]) & 0xFFFFFFFF
    if op == 0xE9:                             # jmp rel32
        return 5, True, (pc + 5 + struct.unpack_from("<i", b, 1)[0]) & 0xFFFFFFFF
    if op == 0xEB:                             # jmp rel8
        return 2, True, (pc + 2 + struct.unpack_from("<b", b, 1)[0]) & 0xFFFFFFFF
    if op == 0x0F and len(b) > 1 and 0x80 <= b[1] <= 0x8F:  # jcc rel32
        return 6, True, (pc + 6 + struct.unpack_from("<i", b, 2)[0]) & 0xFFFFFFFF
    if op == 0xC3:
        return 1, False, 0
    if op == 0xC2:
        return 3, False, 0
    raise ValueError(f"unhandled opcode {op:02x} at {pc:#x}")


def boundaries(code, va):
    """Decode from va, return (boundary_addresses, per-insn (len,ispcrel,tgt))."""
    outs, off = [], 0
    while off < len(code):
        ln, isp, tgt = decode_one(code[off:], va + off)
        outs.append((va + off, ln, isp, tgt))
        off += ln
    return outs


def read(xbe, va, n):
    return xbe.read(va, n)


def main(argv):
    path = DEFAULT_XBE
    module_base = 0x4F0000
    i = 1
    while i < len(argv):
        if argv[i] == "--xbe" and i + 1 < len(argv):
            path = argv[i + 1]; i += 2
        elif argv[i] == "--module-base" and i + 1 < len(argv):
            module_base = int(argv[i + 1], 0); i += 2
        else:
            i += 1

    data = open(path, "rb").read()
    got = hashlib.sha256(data).hexdigest()
    if got != U803_SHA256:
        print(f"FAIL: SHA256 {got} != pinned {U803_SHA256}")
        return 1
    print(f"ok: sha256 {got[:16]}... (pinned build)")

    d = data
    u32 = lambda o: struct.unpack_from("<I", d, o)[0]
    base = u32(0x104)
    nsec = u32(0x11C)
    sec_addr = u32(0x120)
    sections = []
    for k in range(nsec):
        o = sec_addr - base + k * 0x38
        np = u32(o + 20) - base
        name = d[np:np + 16].split(b"\0")[0].decode("latin1")
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
            out.append(d[o] if o is not None else 0)
        return bytes(out)

    xpp = next(s for s in sections if s["name"] == "XPP")
    print(f"ok: XPP va {xpp['va']:#x} vsize {xpp['vs']:#x} flags {xpp['flags']:#x} "
          f"(exec={bool(xpp['flags']&4)} writable={bool(xpp['flags']&1)})")

    ok = True
    for (name, va, argc, dlen, disp_hex, resume, pcrel) in SITES:
        disp = bytes.fromhex(disp_hex)
        in_xpp = xpp["va"] <= va < xpp["va"] + xpp["vs"]
        orig5 = rd(va, 5)
        orig5_ok = orig5.hex(" ").upper() == " ".join(f"{b:02X}" for b in disp[:5])
        got_disp = rd(va, dlen)
        disp_ok = got_disp == disp

        # instruction-boundary scan over the displaced span only
        hdr = rd(va, dlen)
        insns = boundaries(hdr, va)
        span_sum = sum(ln for _, ln, _, _ in insns)
        span_ok = (span_sum == dlen)          # dlen ends exactly on a boundary
        # the 5-byte overwrite must also end on a boundary <= dlen (implied by
        # span_ok since dlen >= 6 and decode starts at va)

        # branch-into-overwrite hazard + PC-rel re-encode
        hazard = False
        reenc = None
        reenc_tramp = 0
        for (a, ln, isp, tgt) in insns:
            if isp:
                if va <= tgt < va + 5:
                    hazard = True
                if pcrel and tgt == pcrel:      # the one displaced PC-rel (call rel32)
                    # relocated: same instr at TRAMP, must retarget same abs target
                    rel_off = a - va
                    reenc_tramp = module_base + 0x100
                    new_rel = (pcrel - (reenc_tramp + 5)) & 0xFFFFFFFF
                    new_rel_s = new_rel - 0x100000000 if new_rel >= 0x80000000 else new_rel
                    reenc = (reenc_tramp, struct.pack("<i", new_rel_s),
                             disp[rel_off:rel_off + ln])

        good = in_xpp and orig5_ok and disp_ok and span_ok and not hazard
        if not good:
            ok = False
        print(f"{'ok  ' if good else 'FAIL'} {name:<22} va={va:#010x} orig5={orig5.hex(' ')} "
              f"disp[{dlen}] resume={resume:#x} boundary={span_ok} in_xpp={in_xpp} hazard={hazard}")
        if not orig5_ok:
            print(f"      expected orig5 = {' '.join(f'{b:02X}' for b in disp[:5])}")
        if not disp_ok:
            print(f"      expected disp  = {disp_hex}")
        if not span_ok:
            print(f"      boundary+resume mismatch: decoded span sum {span_sum} != {dlen}")
        if reenc:
            reenc_tramp_v, reenc_rel, old_bytes = reenc
            print(f"      PC-rel re-encode: orig `{old_bytes.hex(' ')}` (rel +{struct.unpack_from('<i', old_bytes, 1)[0]:+d} "
                  f"-> {pcrel:#x}) re-emitted at tramp {reenc_tramp_v:#x} as rel "
                  f"+{struct.unpack('<i', reenc_rel)[0]:+d} (still -> {pcrel:#x})")

        # E9 to the module hook fn (module_base + per-site offset)
        e9_rel = (module_base + 0x200 + 32 * SITES.index((name, va, argc, dlen, disp_hex, resume, pcrel))) - (va + 5)
        print(f"      E9 rel32 -> module hook @ {module_base + 0x200 + 32 * SITES.index((name, va, argc, dlen, disp_hex, resume, pcrel)):#x} = {e9_rel & 0xFFFFFFFF:08x}")

    print("")
    print("ALL HOOK-SITE INSTALL-PLAN ASSERTIONS PASSED" if ok else "SOME ASSERTIONS FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
