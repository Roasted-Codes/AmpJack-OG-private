#!/usr/bin/env python3
"""FID-lite: match xapilib.lib function byte-prefixes into Halo 2 u803 default.xbe.

Because the USB/XInput stack is statically linked from xapilib.lib, each function's
machine code appears byte-identical in the XBE except at linker-relocated absolute
address/immediate sites. We search exact byte prefixes and, for each candidate VA,
extend the match as far as the bytes agree (reporting the matched length), then
disassemble the candidate.

Usage:
  fid_match.py <lib> <xbe> [--names SUBSTR ...] [--all] [--min 12] [--top N]
"""
import sys
import os
import struct

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, "/home/roasted/Desktop/Xbox/LAN_Stats/tools")
import xapilib_extract as X
from xbe_va import XBE, U803_SHA256, fmt

LIB = "/home/roasted/Desktop/Xbox/H2-Decomp/tu15-decomp/work/xdk5849/XDK/xbox/lib/xapilib.lib"
XBE_PATH = "/home/roasted/Desktop/Xbox/H2-Decomp/tu15-decomp/targets/halo2-tu15-u803/default.xbe"


def load_functions(d, resolved):
    """name -> (bytes,) using per-object function-start extents in each section.

    Extent = section data [value : next function symbol value in same section]
    (debug/static labels are ignored so .bf/.lf/$found_match no longer truncate)."""
    funcs = {}
    for objname, hoff, doff, size in resolved:
        r = X.parse_coff(d, doff)
        if r is None:
            continue
        sections, symbols = r
        # collect function starts per section (external, function type)
        per_sec = {}
        for s in symbols:
            if s["sclass"] == 2 and (s["typ"] >> 4) == 0x2 and s["secno"] > 0:
                per_sec.setdefault(s["secno"], []).append((s["value"], s["name"]))
        for secno, lst in per_sec.items():
            lst.sort()
            data = sections[secno - 1]["data"]
            endcap = sections[secno - 1]["rawsize"]
            for i, (val, name) in enumerate(lst):
                nxt = lst[i + 1][0] if i + 1 < len(lst) else endcap
                body = data[val:nxt]
                if len(body) >= 4:
                    funcs.setdefault(name, body)
    return funcs


def exec_regions(x):
    regions = []
    for s in x.sections:
        if (s["flags"] & 0x4) and s["rawsize"]:
            regions.append((s, x.data[s["raw"]:s["raw"] + s["rawsize"]]))
    return regions


def match_prefix(x, prefix, want_all=False):
    regions = exec_regions(x)
    hits = []
    for s, blob in regions:
        start = 0
        while True:
            i = blob.find(prefix, start)
            if i < 0:
                break
            va = s["va"] + i
            hits.append((va, s, i))
            if not want_all:
                return hits
            start = i + 1
    return hits


def extended_match(x, va, libbytes):
    """Count how many bytes agree from va onward (using LOADED bytes, skipping nothing)."""
    n = 0
    for b in libbytes:
        try:
            got = x.read(va + n, 1)[0]
        except ValueError:
            break
        if got != b:
            break
        n += 1
    return n


def main(argv):
    args = argv[1:]
    lib = args[0]
    xbe = args[1]
    names = []
    all_ = False
    minlen = 8
    want_all = False
    i = 2
    while i < len(args):
        a = args[i]
        if a == "--names":
            names += args[i + 1].split(",")
            i += 2
        elif a == "--all":
            all_ = True
            i += 1
        elif a == "--min":
            minlen = int(args[i + 1])
            i += 2
        elif a == "--all-hits":
            want_all = True
            i += 1
        elif a == "--top":
            i += 2
        else:
            i += 1

    d, resolved, _ = X.parse_archive(lib)
    funcs = load_functions(d, resolved)
    x = XBE(xbe, expect_sha256=U803_SHA256)

    if all_:
        targets = sorted(funcs.items())
    else:
        targets = [(n, b) for n, b in sorted(funcs.items())
                   if any(sub.lower() in n.lower() for sub in names)]

    print(f"lib functions loaded: {len(funcs)}; match targets: {len(targets)}")
    for name, fbytes in targets:
        hits = []
        for k in (28, 20, 14, 10):
            pref = fbytes[:k]
            if len(pref) < k:
                continue
            hits = match_prefix(x, pref, want_all=want_all)
            if len(hits) == 1 or (want_all and hits):
                break
        if not hits:
            print(f"NO MATCH  len={len(fbytes)}  {name}")
            continue
        for va, s, i in hits:
            ext = extended_match(x, va, fbytes)
            ins = x.dis(va, 4)
            dis = " | ".join(fmt(z) for z in ins)
            print(f"{va:08X}  {s['name']:<10} prefix={k} matched={ext}/{len(fbytes)}  {name}")
            print(f"           {dis}")
            if len(hits) > 1 and want_all:
                continue


if __name__ == "__main__":
    main(sys.argv)
