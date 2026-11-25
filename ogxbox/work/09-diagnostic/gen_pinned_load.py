#!/usr/bin/env python3
"""
gen_pinned_load.py — derive the usbd_LoadClassDriver detour pin from the BUILT
XBE's actual bytes and emit ogxbox/diagnostic/src/pinned_load.h.

Why this exists (fail-closed): the E9 detour at usbd_LoadClassDriver overwrites
the first 5 bytes of the function.  Those 5 bytes + whatever instruction they
cut into are the "displaced span", which the trampoline must re-execute verbatim
before jumping back to `entry + span_len`.  Hand-guessing that span is exactly
the class of error this worker is not allowed to ship, so the pin is derived
here, at build time, from the linked .exe (lld output) and cross-checked against
the final .xbe section headers.

The script:
  1. reads the symbol VA of ?USBD_LoadClassDriver@@... from bin/AmpJackProbe.map
  2. slices the raw code bytes at that RVA out of bin/AmpJackProbe.exe (PE)
  3. disassembles with a small, conservative x86 length decoder (anything it
     does not recognise => refuse to emit, never guess) until >= 5 bytes are
     covered by whole instructions
  4. detects PC-relative (rel8/rel32) instructions in the span and records the
     absolute target of the first rel32 `call`/`jmp` (re-encoded in the
     trampoline as `mov eax, imm32; call eax`)
  5. parses the final .xbe section headers, locates the section holding the
     function, and asserts its dwFlags has the writable bit (0x1) — otherwise
     the header emits PINNED_LOAD_SECTION_WRITABLE 0 and main.c must fail closed
     with PINFAIL instead of patching.

Usage:
  python3 gen_pinned_load.py [--verify] [repo-root]
    (default repo-root = dirname(dirname(dirname(__file__))))  # .../AmpJack-OG
  The normal mode writes src/pinned_load.h.
  --verify regenerates and compares to the committed header; exit non-zero on
  any drift (fail-closed against a stale pin).
"""
import struct, sys, os, subprocess

def repo_root():
    d = os.path.abspath(os.path.dirname(__file__))
    # .../AmpJack-OG/ogxbox/work/09-diagnostic -> .../AmpJack-OG
    return os.path.dirname(os.path.dirname(os.path.dirname(d)))

def diag_dir(root):
    return os.path.join(root, "ogxbox", "diagnostic")

MANGLE = "?USBD_LoadClassDriver@@"

# ---------------------------------------------------------------- PE parsing
def parse_pe(path):
    d = open(path, "rb").read()
    pe = struct.unpack_from("<I", d, 0x3C)[0]
    if d[pe:pe+2] != b"PE":
        raise SystemExit("not a PE: %s" % path)
    nsec = struct.unpack_from("<H", d, pe+6)[0]
    opt = struct.unpack_from("<H", d, pe+20)[0]
    imgbase = struct.unpack_from("<I", d, pe+24+0x1C)[0]
    sectab = pe + 24 + opt
    secs = []
    for i in range(nsec):
        o = sectab + i*40
        name = d[o:o+8].rstrip(b"\x00").decode("latin1")
        vsize, va, rsize, roff = struct.unpack_from("<IIII", d, o+8)
        secs.append((name, va, vsize, roff, rsize))
    def rva_to_off(rva):
        for name, va, vsize, roff, rsize in secs:
            if va <= rva < va + vsize:
                return roff + (rva - va), name
        return None, None
    return d, imgbase, secs, rva_to_off

def read_map_symbol(map_path, mangle):
    best = None
    for line in open(map_path, "r", errors="replace"):
        if mangle in line:
            # "0005:0000250a  ?USBD_LoadClassDriver...  000000000002350a  ..."
            parts = line.split()
            # address is the 3rd whitespace token (hex)
            for tok in parts:
                if tok.startswith("00000000") and len(tok) == 16:
                    best = int(tok, 16)
    if best is None:
        raise SystemExit("map symbol %r not found in %s" % (mangle, map_path))
    return best

# ------------------------------------------------------- conservative decoder
# Returns (length, has_pcrel, rel_target_or_None).  Raises on unknown opcode.
def decode_one(code, va):
    b = code[0]
    def imm8(off):  return code[off] if off < len(code) else None
    def rel8(off):
        v = code[off] if off < len(code) else 0
        if v & 0x80: v -= 0x100
        return va + off + 1 + v
    def rel32(off):
        if off + 4 >= len(code): raise ValueError("truncated rel32 @%x" % va)
        v = struct.unpack_from("<i", code, off)[0]
        return va + off + 4 + v

    if b == 0xCC or b == 0x90:            # int3 / nop
        return 1, False, None
    if 0x50 <= b <= 0x57:                 # push reg
        return 1, False, None
    if 0x58 <= b <= 0x5F:                 # pop reg
        return 1, False, None
    if 0x40 <= b <= 0x4F:                 # inc/dec reg
        return 1, False, None
    if 0xB8 <= b <= 0xBF:                 # mov reg, imm32
        return 5, False, None
    if 0x68 <= b <= 0x6A:                 # push imm8/16/32
        n = 1 if b == 0x6A else (2 if b == 0x69 else 0)
        return (1 + (4 if b == 0x68 else 0) + (4 if b == 0x69 else 0)) if b != 0x6A else 2, False, None
    if b == 0xC3:                         # ret
        return 1, False, None
    if 0x70 <= b <= 0x7F:                 # jcc rel8
        return 2, True, rel8(1)
    if b in (0xE8, 0xE9):                 # call/jmp rel32
        return 5, True, rel32(1)
    if b == 0xEB:                         # jmp rel8
        return 2, True, rel8(1)

    # mod-reg-rm instructions (mov/cmp/test/add/sub/and/or/xor/lea/...)
    if len(code) < 2:
        raise ValueError("truncated modrm @%x" % va)
    modrm = code[1]
    mod = modrm >> 6; reg = (modrm >> 3) & 7; rm = modrm & 7
    has_disp = (mod == 1) or (mod == 2) or (mod == 0 and rm == 5) or (mod == 0 and rm == 4 and (code[2] if len(code) > 2 else 0) & 7 == 5)
    # decode 8/16/32 group by opcode width flag
    group = b >> 4  # coarse
    if b in (0x83,):   # group1 imm8 (signed extend)
        disp = 1 if mod == 1 else (4 if (mod == 2) else (4 if has_disp and mod == 0 else 0))
        sib = 1 if rm == 4 and mod != 3 else 0
        return 2 + disp + sib + 1, False, None    # +1 imm8
    if b in (0x81,):   # group1 imm32
        disp = 1 if mod == 1 else (4 if mod == 2 else (4 if has_disp and mod == 0 else 0))
        sib = 1 if rm == 4 and mod != 3 else 0
        return 2 + disp + sib + 4, False, None
    # simple 8-bit ops with modrm but no imm: c6/c7 are mov r/m,imm -> handle separately
    if b in (0x8B, 0x89, 0x85, 0x39, 0x3B, 0x8D, 0x03, 0x0B, 0x23, 0x2B, 0x33, 0x3A,
             0x80, 0x01, 0x09, 0x11, 0x19, 0x21, 0x29, 0x31):
        disp = 1 if mod == 1 else (4 if mod == 2 else (4 if has_disp else 0))
        sib = 1 if rm == 4 and mod != 3 else 0
        if b == 0x8D:  # lea
            return 2 + disp + sib, False, None
        return 2 + disp + sib, False, None
    if b == 0xC7:   # mov r/m32, imm32
        disp = 1 if mod == 1 else (4 if mod == 2 else (4 if has_disp else 0))
        sib = 1 if rm == 4 and mod != 3 else 0
        return 2 + disp + sib + 4, False, None
    if b == 0xFF:   # call/jmp/push [rm] or inc/dec
        disp = 1 if mod == 1 else (4 if mod == 2 else (4 if has_disp else 0))
        sib = 1 if rm == 4 and mod != 3 else 0
        return 2 + disp + sib, False, None   # indirect: target via memory, not a rel32 in our span
    raise ValueError("unknown opcode 0x%02x @ rva 0x%x" % (b, va))

def disassemble_span(code, base_rva, rva):
    """Walk from entry until whole instructions cover >= 5 bytes.
       Returns (span_len, entries, rel_targets)."""
    off = 0
    entries = []   # (offset_in_span, length, mnemonic_hint, has_pcrel, target)
    rel_targets = []
    while off < 5:
        va = rva + off
        ln, pc, tgt = decode_one(code[off:off+16], va)
        instr = code[off:off+ln]
        entries.append((off, ln, instr, pc, tgt))
        if pc:
            rel_targets.append((off, ln, tgt))
        off += ln
        if off > 32:
            raise SystemExit("prologue sill longer than 32 bytes; refusing")
    return off, entries, rel_targets

# ---------------------------------------------------------------- XBE flags
def xbe_section_flags(xbe_path, target_va):
    d = open(xbe_path, "rb").read()
    if d[0:4] != b"XBEH":
        raise SystemExit("not an XBE: %s" % xbe_path)
    base = struct.unpack_from("<I", d, 0x104)[0]
    nsections = struct.unpack_from("<I", d, 0x11C)[0]
    hdr_va = struct.unpack_from("<I", d, 0x120)[0]
    hdr_off = hdr_va - base   # XBE header addresses are image VAs, not file offsets
    for i in range(nsections):
        o = hdr_off + i*56
        flags = struct.unpack_from("<I", d, o)[0]
        vaddr = struct.unpack_from("<I", d, o+4)[0]
        vsize = struct.unpack_from("<I", d, o+8)[0]
        if vaddr <= target_va < vaddr + vsize:
            return base, flags, vaddr, vsize, i
    raise SystemExit("LoadClassDriver VA 0x%x not inside any %s section" % (target_va, xbe_path))

def main():
    argv = sys.argv[1:]
    root = repo_root()
    verify = False
    for a in argv:
        if a == "--verify":
            verify = True
        elif os.path.isdir(a):
            root = a
    ddir = diag_dir(root)
    exe = os.path.join(ddir, "bin", "AmpJackProbe.exe")
    xbe = os.path.join(ddir, "bin", "default.xbe")
    mapp = os.path.join(ddir, "bin", "AmpJackProbe.map")
    out = os.path.join(ddir, "src", "pinned_load.h")

    data, imgbase, secs, rva_to_off = parse_pe(exe)
    symva = read_map_symbol(mapp, MANGLE)
    rva = symva - imgbase
    off, name = rva_to_off(rva)
    if off is None:
        raise SystemExit("RVA 0x%x not in any PE section" % rva)
    # disassemble in *absolute* VA space so rel32 targets are image VAs
    span_len, entries, rel_targets = disassemble_span(data[off:off+40], imgbase, symva)

    # gather rel32 target (must be a call or jmp), else PINNED_LOAD_REL32_TARGET = 0
    rel32_target = None
    rel32_offset = 0
    for (o, ln, instr, pc, tgt) in entries:
        if pc and ln == 5:      # rel32
            rel32_target = tgt
            rel32_offset = o
    span = data[off:off+span_len]

    xbe_base, flags, vaddr, vsize, sidx = xbe_section_flags(xbe, symva)
    writable = bool(flags & 0x1)

    # call target delta relative to LoadClassDriver entry (for trampoline re-encode)
    if rel32_target is not None:
        call_delta = rel32_target - symva
        delta_c = ("(-0x%x)" % (-call_delta)) if call_delta < 0 else ("0x%x" % call_delta)
    else:
        call_delta = 0
        delta_c = "0"

    span_c = ", ".join("0x%02x" % b for b in span)
    prologue = span[:5]
    prologue_c = ", ".join("0x%02x" % b for b in prologue)

    text = """/* pinned_load.h — GENERATED by ogxbox/work/09-diagnostic/gen_pinned_load.py.
 * Do NOT hand-edit. Regenerate with:  python3 ogxbox/work/09-diagnostic/gen_pinned_load.py
 *
 * Derived from the BUILT artifacts (bin/AmpJackProbe.exe + bin/default.xbe):
 *   LoadClassDriver VA   = 0x%(symva)08x  (RVA 0x%(rva)08x, PE section %(sect)s)
 *   XBE section          = %(sidx)d  (VA 0x%(vaddr)08x size 0x%(vsize)x, flags 0x%(flags)x)
 *   writable             = %(writable)s  (XBE dwFlags bit 0)
 *   displaced span       = %(span_len)d bytes: %(span)s
 *   E9 overwrites        = first 5 bytes: %(prologue)s
 *   resume offset        = %(span_len)d  (jump back to entry + %(span_len)d)
 *   rel32 in span        = %(rel32_present)s  (at span offset %(rel32_offset)d -> abs 0x%(rel32_target)08x)
 * The trampoline re-executes the displaced instructions, re-encoding any rel32
 * `call` as `mov eax, <abs target>; call eax` (using the runtime symbol base,
 * so it is image-base independent).  If the span ever contains a rel32 we did
 * not expect, PINNED_LOAD_REL32_PRESENT still recovers the entry and the
 * re-encode is computed from PINNED_LOAD_CALL_TARGET_DELTA.
 */
#ifndef PINNED_LOAD_H
#define PINNED_LOAD_H

#define PINNED_LOAD_ENTRY_RVA       0x%(rva)08x    /* RVA of usbd_LoadClassDriver */
#define PINNED_LOAD_SPAN_LEN        %(span_len)d
#define PINNED_LOAD_RESUME_OFF      %(span_len)d
#define PINNED_LOAD_PROLOGUE_LEN    5
#define PINNED_LOAD_REL32_PRESENT   %(rel32_pres)d
#define PINNED_LOAD_REL32_OFFSET    %(rel32_offset)d
#define PINNED_LOAD_CALL_TARGET_DELTA %(delta_c)s
#define PINNED_LOAD_SECTION_WRITABLE %(writable)d   /* 0 => main.c fails closed with PINFAIL */

static const unsigned char PINNED_LOAD_SPAN[%(span_len)d] = { %(span_c)s };

#endif /* PINNED_LOAD_H */
""" % {
        "symva": symva, "rva": rva, "sect": name,
        "sidx": sidx, "vaddr": vaddr, "vsize": vsize, "flags": flags,
        "writable": 1 if writable else 0,
        "span_len": span_len, "span": " ".join("%02x" % b for b in span),
        "prologue": " ".join("%02x" % b for b in prologue),
        "rel32_present": 1 if rel32_target is not None else 0,
        "rel32_offset": rel32_offset,
        "rel32_target": rel32_target if rel32_target else 0,
        "rel32_pres": 1 if rel32_target is not None else 0,
        "call_delta": call_delta,
        "delta_c": delta_c,
        "writable": 1 if writable else 0,
        "span_c": span_c,
        "prologue_c": prologue_c,
    }

    # Optional objdump cross-check (human-verifiable proof the span is right)
    obd = None
    try:
        obd = subprocess.run(
            ["llvm-objdump", "-d",
             "--start-address=0x%x" % symva,
             "--stop-address=0x%x" % (symva + span_len), exe],
            capture_output=True, text=True).stdout
    except Exception as e:
        obd = "llvm-objdump not run: %s" % e

    if verify:
        cur = ""
        if os.path.exists(out):
            cur = open(out).read()
        if cur != text:
            print("PIN MISMATCH: committed pinned_load.h differs from generated")
            print("regenerate with: python3 ogxbox/work/09-diagnostic/gen_pinned_load.py")
            sys.exit(1)
        print("pinned_load.h up-to-date (span=%d, writable=%s, rel32=%s)" % (
            span_len, writable, rel32_target))
    else:
        open(out, "w").write(text)

    print("entry VA 0x%x RVA 0x%x section %s" % (symva, rva, name))
    print("XBE section %d VA 0x%x flags 0x%x writable=%s" % (sidx, vaddr, flags, writable))
    print("displaced span %d bytes: %s" % (span_len, " ".join("%02x" % b for b in span)))
    if rel32_target is not None:
        print("rel32 call/jmp at offset %d -> abs 0x%x (delta 0x%x)" % (
            rel32_offset, rel32_target, call_delta))
    else:
        print("no PC-relative instruction in displaced span")
    print("llvm-objdump proof:\n%s" % (obd or "(none)"))
    return 0

if __name__ == "__main__":
    sys.exit(main())
