#!/usr/bin/env python3
"""install_harness.py -- OFF-LINE dry-run of the module stage + hook install.

Read-only on the frozen XBE. It:
  1. verifies the frozen XBE sha256 (build gate),
  2. parses out/pic.elf for the module's symbol offsets / sections / relocations,
  3. verifies, per patch site, the EXACT original 5 bytes to overwrite (six XInput
     sites from og_hook_sites.h + the FindClassDriver site @0x41517D),
  4. computes the real E9 rel32 for each site -> module hook (module_base+offset),
  5. applies the patches to a WORK COPY of the XBE and reads them back.

This executes the actual patch bytes/math (no text search), so the parent can
audit the exact transform its runtime injector will perform. It does NOT boot a
guest and does NOT modify the original XBE.

Usage:
  python3 install_harness.py [--module-base 0x4F0000] [--elf out/pic.elf]
"""
import hashlib
import struct
import sys
import os

U803_SHA256 = "21b207e7efdacaf6124a0822837f8be570766a42505057f7fd2d2ba8f409c4fd"
XBE = "/home/roasted/Desktop/Xbox/H2-Decomp/tu15-decomp/targets/halo2-tu15-u803/default.xbe"
ELF = os.path.join(os.path.dirname(__file__), "..", "..", "integration", "out", "pic.elf")
WORK = os.path.join(os.path.dirname(__file__), "staged.xbe")  # work COPY (never the original)

# six XInput sites (name, va, orig5 hex) + FindClassDriver (VERIFIED pin_u803.py)
SITES = [
    ("XGetDeviceChanges",     0x004139A5, "55 8B EC 56 8B"),
    ("XInputOpen",            0x00413A12, "55 8B EC 51 8B"),
    ("XInputClose",           0x00413A68, "8B 4C 24 04 E8"),
    ("XInputGetCapabilities", 0x00413A74, "55 8B EC 83 EC"),
    ("XInputGetState",        0x00413C4C, "53 56 33 DB FF"),
    ("XInputSetState",        0x00413CBF, "8B 4C 24 04 8D"),
]
FC_VA = 0x0041517D
FC_ORIG5 = "56 B8 B4 27 41"
FC_HOOK_SYM = "ogx_findclassdriver"
XINPUT_HOOK_SYMS = [
    "ogx_stub_xgetdevicechanges", "ogx_stub_xinputopen", "ogx_stub_xinputclose",
    "ogx_stub_xinputgetcaps", "ogx_stub_xinputgetstate", "ogx_stub_xinputsetstate",
]


def xbe_sections(data):
    u32 = lambda o: struct.unpack_from("<I", data, o)[0]
    base = u32(0x104); nsec = u32(0x11C); sec_addr = u32(0x120)
    secs = []
    for k in range(nsec):
        o = sec_addr - base + k * 0x38
        np = u32(o + 20) - base
        secs.append(dict(name=data[np:np+16].split(b"\0")[0].decode("latin1"),
                         flags=u32(o), va=u32(o + 4), vs=u32(o + 8),
                         raw=u32(o + 12), rs=u32(o + 16)))
    return secs


def va_off(secs, va):
    for s in secs:
        if s["va"] <= va < s["va"] + s["vs"] and va - s["va"] < s["rs"]:
            return s["raw"] + (va - s["va"])
    return None


def elf_symbols(elf):
    """parse 32-bit ELF symbol table -> {name: value}."""
    e_shoff, = struct.unpack_from("<I", elf, 32)
    e_shentsize, e_shnum, e_shstrndx = struct.unpack_from("<HHH", elf, 46)
    raw = [struct.unpack_from("<10I", elf, e_shoff + i * e_shentsize) for i in range(e_shnum)]
    strtab = raw[e_shstrndx]

    def name(off):
        b = elf[strtab[4] + off:]
        return b[:b.index(0)].decode()

    syms = {}
    for s in raw:
        if s[1] != 2:  # not SHT_SYMTAB
            continue
        strs = raw[s[6]]  # sh_link -> associated string table section
        for i in range(s[5] // 16):  # s[5]=sh_size
            st_name, value, size, info, other, shndx = struct.unpack_from(
                "<IIIBBH", elf, s[4] + i * 16)  # s[4]=sh_offset
            b = elf[strs[4] + st_name:]  # strs[4]=sh_offset of strtab
            nm = b[:b.index(0)].decode()
            if value:
                syms[nm] = value
    return syms


def reloc_summary(elf):
    """collect R_386_RELATIVE offsets + image/bss sizes from section headers."""
    e_shoff, = struct.unpack_from("<I", elf, 32)
    e_shentsize, e_shnum, e_shstrndx = struct.unpack_from("<HHH", elf, 46)
    raw = [struct.unpack_from("<10I", elf, e_shoff + i * e_shentsize) for i in range(e_shnum)]
    strtab = raw[e_shstrndx]

    def name(off):
        b = elf[strtab[4] + off:]
        return b[:b.index(0)].decode()

    secs = [dict(name=name(s[0]), type=s[1], flags=s[2], addr=s[3], off=s[4],
                 size=s[5], entsize=s[9]) for s in raw]
    relocs = []
    for s in secs:
        if s["name"] in (".rel.dyn", ".rel.plt") and s["size"]:
            for i in range(s["size"] // 8):
                off, info = struct.unpack_from("<II", elf, s["off"] + i * 8)
                assert info & 0xFF == 8, f"non-RELATIVE reloc {info & 0xff:#x}"
                relocs.append(off)
    image_end = end = 0
    for s in secs:
        if s["name"] == ".bss":
            end = s["addr"] + s["size"]
    # image_end = end of .data (last allocated non-bss section)
    max_alloc = 0
    for s in secs:
        if s["flags"] & 2 and s["type"] != 8 and s["name"] not in (".rel.dyn", ".rel.plt",
                                                                   ".dynamic", ".dynsym", ".dynstr",
                                                                   ".hash", ".gnu.hash"):
            max_alloc = max(max_alloc, s["addr"] + s["size"])
    image_end = max_alloc
    texts = sum(s["size"] for s in secs if s["name"] == ".text")
    datas = sum(s["size"] for s in secs if s["name"] in (".data", ".rodata"))
    bss = sum(s["size"] for s in secs if s["name"] == ".bss")
    return relocs, image_end, end, texts, datas, bss


def main(argv):
    module_base = 0x4F0000
    elf_path = ELF
    i = 1
    while i < len(argv):
        if argv[i] == "--module-base":
            module_base = int(argv[i + 1], 0); i += 2
        elif argv[i] == "--elf":
            elf_path = argv[i + 1]; i += 2
        else:
            i += 1

    xbe = open(XBE, "rb").read()
    got = hashlib.sha256(xbe).hexdigest()
    assert got == U803_SHA256, f"XBE sha256 mismatch: {got}"
    secs = xbe_sections(xbe)

    elf = open(elf_path, "rb").read()
    syms = elf_symbols(elf)
    relocs, image_end, end, texts, datas, bss = reloc_summary(elf)

    report = {"xbe_sha256": got, "module_base": hex(module_base),
              "module": {"image_size": image_end, "mem_size": end,
                         "text": texts, "data": datas, "bss": bss,
                         "reloc_count": len(relocs), "reloc_rel_only": True},
              "symbols": {k: hex(v) for k, v in syms.items()
                          if k.startswith("ogx_") and ("stub" in k or k in
                          ("ogx_findclassdriver", "ogx_module_entry", "ogx_module_pump",
                           "ogx_transport_init", "ogx_install_hooks", "ogx_g_module"))},
              "patches": []}

    # the module hook addresses (relocated)
    def hook(sym):
        return module_base + syms[sym]

    # 1. FindClassDriver
    fc_off = va_off(secs, FC_VA)
    fc_actual = xbe[fc_off:fc_off + 5]
    fc_ok = fc_actual.hex(" ").upper() == " ".join(f"{int(x,16):02X}" for x in FC_ORIG5.split())
    fc_symoff = syms.get(FC_HOOK_SYM)
    fc_hook = module_base + fc_symoff if fc_symoff else 0
    fc_rel = (fc_hook - (FC_VA + 5)) & 0xFFFFFFFF if fc_symoff else 0
    report["findclassdriver"] = {"va": hex(FC_VA), "orig5": fc_actual.hex(" "),
                                 "orig5_ok": fc_ok, "hook": hex(fc_hook) if fc_symoff else None}
    report["patches"].append(dict(site="FindClassDriver", va=hex(FC_VA),
                                  e9_rel32=hex(fc_rel) if fc_symoff else None,
                                  patch=("E9 " + bytes.fromhex("%08x" % fc_rel).hex(" "))
                                         if fc_symoff else None))

    # 2. six XInput
    for (nm, va, orig5hex), symname in zip(SITES, XINPUT_HOOK_SYMS):
        off = va_off(secs, va)
        actual = xbe[off:off + 5]
        ok = actual.hex(" ").upper() == " ".join(f"{int(x,16):02X}" for x in orig5hex.split())
        symoff = syms.get(symname)
        hva = module_base + symoff if symoff else 0
        rel = (hva - (va + 5)) & 0xFFFFFFFF if symoff else 0
        report["patches"].append(dict(site=nm, va=hex(va),
                                      orig5=actual.hex(" "), orig5_ok=ok,
                                      hook=hex(hva) if symoff else None,
                                      e9_rel32=hex(rel) if symoff else None,
                                      patch=("E9 " + bytes.fromhex("%08x" % rel).hex(" "))
                                             if symoff else None))

    all_ok = fc_ok and all(p.get("orig5_ok") for p in report["patches"][1:])
    missing = [s for s in [FC_HOOK_SYM] + XINPUT_HOOK_SYMS if s not in syms]
    report["all_orig5_ok"] = all_ok
    report["missing_symbols"] = missing

    # FAIL BEFORE ANY WRITE: a wrong original byte or a missing required symbol
    # must never produce a staged copy (a partial patch is never shipped).
    if not all_ok or missing:
        report["staged_copy"] = None
        report["staged_readback_e9_ok"] = False
        print(json.dumps(report, indent=2))
        print("\n%s: refusing to stage (orig5 mismatch or missing symbol)" %
              ("ORIG5 MISMATCH" if not all_ok else "MISSING SYMBOL"))
        return 1

    # apply all 7 E9 patches to a WORK COPY, each rel computed from its OWN
    # symbol offset (the FindClassDriver rel is fc_rel, NOT the last six-site
    # rel -- the bug that previously pointed FC at 0x4F1B11).
    staged = bytearray(xbe)
    patched = []   # (va, orig5, hook_addr) for readback + rollback
    staged[fc_off:fc_off + 5] = bytes([0xE9]) + struct.pack("<i", fc_rel & 0xFFFFFFFF)
    patched.append((FC_VA, fc_actual, fc_hook))
    for (nm, va, _), symname in zip(SITES, XINPUT_HOOK_SYMS):
        off = va_off(secs, va)
        hva = module_base + syms[symname]
        rel = (hva - (va + 5)) & 0xFFFFFFFF
        orig = xbe[off:off + 5]
        staged[off:off + 5] = bytes([0xE9]) + struct.pack("<i", rel & 0xFFFFFFFF)
        patched.append((va, orig, hva))

    open(WORK, "wb").write(bytes(staged))
    rb = open(WORK, "rb").read()

    # full 5-byte destination verification (opcode + rel32), not just the E9
    # opcode byte: decode each staged site's actual branch target and compare it
    # against the intended module hook address.
    dest_ok = True
    dest_report = []
    for va, orig5, hook_addr in patched:
        off = va_off(secs, va)
        if rb[off] != 0xE9:
            dest_ok = False
            dest_report.append(dict(site=hex(va), error="no E9 opcode"))
            continue
        actual_dest = (va + 5 + struct.unpack_from("<i", rb, off + 1)[0]) & 0xFFFFFFFF
        ok = actual_dest == hook_addr
        dest_ok = dest_ok and ok
        dest_report.append(dict(site=hex(va), actual=hex(actual_dest),
                                expected=hex(hook_addr), correct=ok))
    report["staged_destinations"] = dest_report
    report["staged_destinations_ok"] = dest_ok

    # rollback demonstration: restore every patched site to its original 5 bytes
    # on an IN-MEMORY copy and verify it is byte-identical to the frozen XBE
    # (the on-disk staged.xbe stays patched for parent_branch_check.py to audit).
    rolled = bytearray(rb)
    for va, orig5, _ in patched:
        off = va_off(secs, va)
        rolled[off:off + 5] = orig5
    report["rollback_restores_original"] = bytes(rolled) == xbe

    report["staged_copy"] = os.path.abspath(WORK)
    report["staged_fixture"] = ("branch patches ONLY: no embedded module/BSS/"
                                "relocations; NOT a launchable title")
    report["staged_readback_e9_ok"] = dest_ok

    print(json.dumps(report, indent=2))
    print("\nALL ORIG5 OK, all 7 E9 destinations verified = %s, rollback restores = %s"
          % (dest_ok, report["rollback_restores_original"]))
    return 0 if dest_ok else 1


import json
if __name__ == "__main__":
    sys.exit(main(sys.argv))
