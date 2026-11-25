#!/usr/bin/env python3
"""
gen_pinned_findclass.py — derive the USBD_FindClassDriver E9-detour pin from the
BUILT gipdriver XBE and emit ogxbox/gipdriver/src/pinned_findclass.h.

Modeled on work/09-diagnostic/gen_pinned_load.py (which pins LoadClassDriver).
The hook this worker installs is different from the diagnostic's in one way that
matters: FindClassDriver's prologue in the title-linked xapilib is

    56                push esi
    b8 <imm32>        mov  eax, <class-table begin>   (absolute immediate)
    be <imm32>        mov  esi, <class-table end>     (absolute immediate)
    ...

The displaced span is `push esi; mov eax, <imm32>` = 6 bytes. The E9 overwrites
only the first 5 (`push esi` + the 4 imm-less header bytes of `mov eax` are
unaffected? no: E9 replaces push esi + the opcode B8 + 3 imm bytes; the LAST imm
byte at +5 is NOT overwritten). The trampoline re-executes the whole 6-byte span
by name (`push esi; mov eax, [g_findclass_begin]`) and jumps back to entry+6,
where `mov esi, <end>` runs normally.

The <imm32> immediates depend on where OUR class table lands in OUR OWN XBE, so
they are NOT a static byte pattern: the pin is a SHAPE pin (56 B8 ... BE) plus
the begin immediate, which main.c re-reads from the live bytes at arm time and
cross-checks against this header (fail-closed on any drift).

The script:
  1. reads ?USBD_FindClassDriver@@... VA from bin/AmpJackGip.map
  2. slices those bytes out of bin/AmpJackGip.exe (PE)
  3. verifies the prologue is EXACTLY `push esi; mov eax,imm32; mov esi,imm32`
     (anything else => refuse to emit, never guess)
  4. parses the final .xbe section headers, locates the section holding the
     function, and asserts dwFlags has the writable bit (0x1)
  5. emits src/pinned_findclass.h (default) or --verify compares to the
     committed header and exits non-zero on drift.

Usage:
  python3 gen_pinned_findclass.py [--verify] [repo-root]
"""
import struct, sys, os, subprocess

def repo_root():
    d = os.path.abspath(os.path.dirname(__file__))
    return os.path.dirname(os.path.dirname(os.path.dirname(d)))

def drv_dir(root):
    return os.path.join(root, "ogxbox", "gipdriver")

MANGLE = "?USBD_FindClassDriver@@"


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
            for tok in line.split():
                if tok.startswith("00000000") and len(tok) == 16:
                    best = int(tok, 16)
    if best is None:
        raise SystemExit("map symbol %r not found in %s" % (mangle, map_path))
    return best


def xbe_section_info(xbe_path, target_va):
    d = open(xbe_path, "rb").read()
    if d[0:4] != b"XBEH":
        raise SystemExit("not an XBE: %s" % xbe_path)
    base = struct.unpack_from("<I", d, 0x104)[0]
    nsections = struct.unpack_from("<I", d, 0x11C)[0]
    hdr_va = struct.unpack_from("<I", d, 0x120)[0]
    hdr_off = hdr_va - base
    for i in range(nsections):
        o = hdr_off + i*56
        flags = struct.unpack_from("<I", d, o)[0]
        vaddr = struct.unpack_from("<I", d, o+4)[0]
        vsize = struct.unpack_from("<I", d, o+8)[0]
        if vaddr <= target_va < vaddr + vsize:
            return base, flags, vaddr, vsize, i
    raise SystemExit("FindClassDriver VA 0x%x not inside any section" % target_va)


def main():
    argv = sys.argv[1:]
    root = repo_root()
    verify = False
    for a in argv:
        if a == "--verify":
            verify = True
        elif os.path.isdir(a):
            root = a
    ddir = drv_dir(root)
    exe = os.path.join(ddir, "bin", "AmpJackGip.exe")
    xbe = os.path.join(ddir, "bin", "default.xbe")
    mapp = os.path.join(ddir, "bin", "AmpJackGip.map")
    out = os.path.join(ddir, "src", "pinned_findclass.h")

    data, imgbase, secs, rva_to_off = parse_pe(exe)
    symva = read_map_symbol(mapp, MANGLE)
    rva = symva - imgbase
    off, name = rva_to_off(rva)
    if off is None:
        raise SystemExit("RVA 0x%x not in any PE section" % rva)
    code = data[off:off+40]
    if len(code) < 12:
        raise SystemExit("FindClassDriver prologue too short")

    # shape pin: push esi; mov eax,imm32; mov esi,imm32  (6 + 6 = 12 bytes)
    if code[0] != 0x56:
        raise SystemExit("prologue[0]=0x%02x, not push esi (0x56)" % code[0])
    if code[1] != 0xB8:
        raise SystemExit("prologue[1]=0x%02x, not mov eax,imm32 (0xB8)" % code[1])
    if code[6] != 0xBE:
        raise SystemExit("prologue[6]=0x%02x, not mov esi,imm32 (0xBE); resume shape changed" % code[6])

    begin_imm = struct.unpack_from("<I", code, 2)[0]
    end_imm   = struct.unpack_from("<I", code, 7)[0]
    if end_imm <= begin_imm or (end_imm - begin_imm) % 4:
        raise SystemExit("table bounds strange: begin=0x%x end=0x%x" % (begin_imm, end_imm))

    span_len = 6
    span = code[:span_len]

    xbe_base, flags, vaddr, vsize, sidx = xbe_section_info(xbe, symva)
    writable = bool(flags & 0x1)

    span_c = ", ".join("0x%02x" % b for b in span)
    text = """/* pinned_findclass.h — GENERATED by ogxbox/work/11-gipdriver/gen_pinned_findclass.py.
 * Do NOT hand-edit. Regenerate with:  python3 ogxbox/work/11-gipdriver/gen_pinned_findclass.py
 *
 * Derived from the BUILT artifacts (bin/AmpJackGip.exe + bin/default.xbe):
 *   FindClassDriver VA   = 0x%(symva)08x  (RVA 0x%(rva)08x, PE section %(sect)s)
 *   XBE section          = %(sidx)d  (VA 0x%(vaddr)08x size 0x%(vsize)x, flags 0x%(flags)x)
 *   writable             = %(writable)s  (XBE dwFlags bit 0)
 *   displaced span       = %(span_len)d bytes: %(span)s  (push esi; mov eax, imm32)
 *   class table          = [0x%(begin)08x .. 0x%(end)08x)  (%(n)d entry pointers)
 *   resume offset        = 6  (jump back to `mov esi, imm32` at entry + 6)
 *   rel32 in span        = NONE  (the imm32 is an absolute table address, not PC-relative)
 */
#ifndef PINNED_FINDCLASS_H
#define PINNED_FINDCLASS_H

#define PINNED_FC_ENTRY_RVA       0x%(rva)08x
#define PINNED_FC_SPAN_LEN         %(span_len)d
#define PINNED_FC_RESUME_OFF       %(span_len)d
#define PINNED_FC_BEGIN_IMM        0x%(begin)08x   /* class-table begin immediate */
#define PINNED_FC_END_IMM          0x%(end)08x     /* class-table end   immediate */
#define PINNED_FC_TABLE_ENTRIES    %(n)d
#define PINNED_FC_SECTION_WRITABLE %(writable)d   /* 0 => main.c fails closed with PINFAIL */

static const unsigned char PINNED_FC_SPAN[%(span_len)d] = { %(span_c)s };

#endif /* PINNED_FINDCLASS_H */
""" % {
        "symva": symva, "rva": rva, "sect": name,
        "sidx": sidx, "vaddr": vaddr, "vsize": vsize, "flags": flags,
        "writable": 1 if writable else 0,
        "span_len": span_len, "span": " ".join("%02x" % b for b in span),
        "span_c": span_c,
        "begin": begin_imm, "end": end_imm,
        "n": (end_imm - begin_imm) // 4,
    }

    obd = None
    try:
        obd = subprocess.run(
            ["llvm-objdump", "-d",
             "--start-address=0x%x" % symva,
             "--stop-address=0x%x" % (symva + 16), exe],
            capture_output=True, text=True).stdout
    except Exception as e:
        obd = "llvm-objdump not run: %s" % e

    if verify:
        cur = open(out).read() if os.path.exists(out) else ""
        if cur != text:
            print("PIN MISMATCH: committed pinned_findclass.h differs from generated")
            print("regenerate with: python3 ogxbox/work/11-gipdriver/gen_pinned_findclass.py")
            sys.exit(1)
        print("pinned_findclass.h up-to-date (begin=0x%x end=0x%x writable=%s)" %
              (begin_imm, end_imm, writable))
    else:
        open(out, "w").write(text)

    print("entry VA 0x%x RVA 0x%x section %s" % (symva, rva, name))
    print("XBE section %d VA 0x%x flags 0x%x writable=%s" % (sidx, vaddr, flags, writable))
    print("class table [0x%x .. 0x%x) = %d pointers" % (begin_imm, end_imm, (end_imm - begin_imm)//4))
    print("displaced span %d bytes: %s" % (span_len, " ".join("%02x" % b for b in span)))
    print("llvm-objdump proof:\n%s" % (obd or "(none)"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
