#!/usr/bin/env python3
"""Extract COFF object symbols + machine code from xapilib.lib, and (optionally)
FID-match them into Halo 2 u803 default.xbe.

Read-only on both inputs. Stdlib only (no external deps).

subcommands:
  members  <lib>                 list archive members (name, off, size, section count)
  symbols  <lib>                 list every external symbol (name, obj, section, value)
  funcs    <lib> <outdir>        dump each function's raw bytes to outdir/<name>.bin
  fid      <lib> <xbe> [names]   match function byte prefixes into the XBE
"""
import struct
import sys
import os
import hashlib

I386 = 0x14C


# -------------------------------------------------------------------- archive ----
def parse_archive(path):
    d = open(path, "rb").read()
    assert d[:8] == b"!<arch>\n", "not a COFF archive"
    # members
    members = []  # (name, header_off, data_off, size)
    off = 8
    while off < len(d):
        if off + 60 > len(d):
            break
        hdr = d[off:off + 60]
        name = hdr[0:16].decode("latin1").rstrip()
        size = int(hdr[48:58].decode("latin1").strip() or 0)
        data_off = off + 60
        members.append((name, off, data_off, size))
        off = data_off + size + (size & 1)
    # string table is the '//' member (long names)
    longnames = {}
    symtab = None
    for name, hoff, doff, size in members:
        if name == "//":
            longnames = d[doff:doff + size]
        elif name == "/":
            symtab = d[doff:doff + size]
    # resolve member names: '/N' => longnames[N:]
    resolved = []
    for name, hoff, doff, size in members:
        if name.startswith("/") and name != "/" and name != "//":
            idx = int(name[1:] or "0")
            # find end of the null-terminated string at longnames[idx]
            end = longnames.find(b"\0", idx)
            name = longnames[idx:end].decode("latin1", "replace")
        elif name.endswith("/"):
            name = name[:-1]
        resolved.append((name, hoff, doff, size))
    # symbol table mapping (name -> member index) -- optional; we parse objects directly
    symmap = {}
    try:
        # use the FIRST '/'-named member that parses as a symbol table
        for name, hoff, doff, size in members:
            if name == "/":
                cnt = 0
                try:
                    cnt = struct.unpack_from(">I", d, doff)[0]
                except Exception:
                    continue
                if 4 + cnt * 4 <= size:
                    idxs = [struct.unpack_from(">I", d, doff + 4 + i * 4)[0] for i in range(cnt)]
                    names = d[doff + 4 + cnt * 4:doff + size].split(b"\0")
                    for i in range(cnt):
                        if i < len(names) and names[i]:
                            symmap.setdefault(names[i].decode("latin1", "replace"), idxs[i])
                    break
    except Exception:
        symmap = {}
    return d, resolved, symmap


# -------------------------------------------------------------------- coff ----
def parse_coff(d, base):
    """Return (sections, symbols) of a COFF object at offset base in archive data d."""
    if d[base:base + 2] != b"\x4c\x01":  # i386 machine
        return None
    nsec = struct.unpack_from("<H", d, base + 2)[0]
    symptr = struct.unpack_from("<I", d, base + 8)[0]
    nsym = struct.unpack_from("<I", d, base + 12)[0]
    sechead = base + 20
    sections = []
    for i in range(nsec):
        o = sechead + i * 40
        name = d[o:o + 8].split(b"\0")[0].decode("latin1", "replace")
        vsize = struct.unpack_from("<I", d, o + 8)[0]
        vaddr = struct.unpack_from("<I", d, o + 12)[0]
        rawsize = struct.unpack_from("<I", d, o + 16)[0]
        rawptr = struct.unpack_from("<I", d, o + 20)[0]
        sections.append(dict(name=name, vsize=vsize, vaddr=vaddr,
                             rawsize=rawsize, rawptr=rawptr,
                             data=d[base + rawptr:base + rawptr + rawsize]))
    # symbol table
    symoff = base + symptr
    strtab_off = symoff + nsym * 18
    strtab_len = struct.unpack_from("<I", d, strtab_off)[0]
    strtab = d[strtab_off:strtab_off + strtab_len]
    symbols = []
    i = 0
    idx = 0
    while idx < nsym:
        o = symoff + idx * 18
        name8 = d[o:o + 8]
        if name8[:4] == b"\0\0\0\0":
            soff = struct.unpack_from("<I", d, o + 4)[0]
            end = strtab.find(b"\0", soff)
            name = strtab[soff:end].decode("latin1", "replace")
        else:
            name = name8.split(b"\0")[0].decode("latin1", "replace")
        value = struct.unpack_from("<I", d, o + 8)[0]
        secno = struct.unpack_from("<h", d, o + 12)[0]
        typ = struct.unpack_from("<H", d, o + 14)[0]
        sclass = d[o + 16]
        naux = d[o + 17]
        symbols.append(dict(name=name, value=value, secno=secno, typ=typ,
                            sclass=sclass, naux=naux))
        idx += 1 + naux
    return sections, symbols


def iter_obj_symbols(d, resolved, skip_aux=True):
    """Yield (objname, symbol, section_data_offset) for external defined funcs."""
    for name, hoff, doff, size in resolved:
        r = parse_coff(d, doff)
        if r is None:
            continue
        sections, symbols = r
        for s in symbols:
            yield name, s, sections


def function_bytes(sections, sym, symbols):
    """Return (bytes, va_base) for a function: code until the next function symbol
    in the same section with a larger value, else end of section."""
    if sym["secno"] <= 0 or sym["secno"] > len(sections):
        return None, None
    sec = sections[sym["secno"] - 1]
    start = sym["value"]
    # find end = next symbol in same section with value > start
    end = sec["rawsize"]
    for other in symbols:
        if other is sym:
            continue
        if other["secno"] == sym["secno"] and other["value"] > start:
            end = min(end, other["value"])
    data = sec["data"][start:end]
    return data, start


def _demangle_ms(name):
    # crude: strip leading ? and locate the unmangled tail of a C++ mangled name
    return name


def xbe_text_sections(x):
    return [(s, x.data[s["raw"]:s["raw"] + s["rawsize"]])
            for s in x.sections if (s["flags"] & 0x4) and s["rawsize"]]


def find_all(haystack, needle):
    out = []
    i = haystack.find(needle)
    while i != -1:
        out.append(i)
        i = haystack.find(needle, i + 1)
    return out


def main(argv):
    cmd = argv[1]
    lib = argv[2]
    if cmd == "members":
        d, resolved, symmap = parse_archive(lib)
        for name, hoff, doff, size in resolved:
            print(f"{doff:8} {size:8} {name}")
    elif cmd == "symbols":
        d, resolved, symmap = parse_archive(lib)
        for objname, s, sections in iter_obj_symbols(d, resolved, False):
            print(f"{objname:24} sec={s['secno']:3} val={s['value']:#06x} "
                  f"class={s['sclass']} typ={s['typ']:#04x} {s['name']}")
    elif cmd == "funcs":
        outdir = argv[3]
        os.makedirs(outdir, exist_ok=True)
        d, resolved, symmap = parse_archive(lib)
        # collect func bytes per symbol; group symbols per object first
        done = {}
        for objname, s, sections in iter_obj_symbols(d, resolved, False):
            if s["secno"] <= 0 or s["sclass"] != 2:
                continue
            if s["typ"] >> 4 == 0x2:  # function
                syms = [x for x, _ in _obj_symbols_for(d, resolved, objname)]
                data, _ = function_bytes(sections, s, syms)
                if data and len(data) >= 4:
                    key = s["name"]
                    if key in done:
                        continue
                    done[key] = 1
                    safe = key.replace("?", "_").replace("@", "_").replace(":", "_")
                    if len(safe) > 120:
                        safe = safe[:120]
                    with open(os.path.join(outdir, safe + ".bin"), "wb") as f:
                        f.write(data)
        print("wrote", len(done), "functions to", outdir)
    else:
        raise SystemExit("unknown cmd")


def _obj_symbols_for(d, resolved, objname):
    out = []
    for name, hoff, doff, size in resolved:
        if name != objname:
            continue
        r = parse_coff(d, doff)
        if r is None:
            return out
        sections, symbols = r
        for s in symbols:
            out.append((s, sections))
        return out
    return out


if __name__ == "__main__":
    main(sys.argv)
