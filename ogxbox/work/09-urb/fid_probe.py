#!/usr/bin/env python3
"""FID-probe helper for worker 09: match xapilib.lib function byte-prefixes into the
u803 XBE and report (VA, matched bytes, first disasm). Read-only on both inputs.

Usage:
  fid_probe.py --names "XID_fOpenEndpoints,XID_NewInterruptData" [--min 12] [--all-hits]
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, "/home/roasted/Desktop/Xbox/AmpJack-OG/ogxbox/work/07-binding")
sys.path.insert(0, "/home/roasted/Desktop/Xbox/LAN_Stats/tools")

import xapilib_extract as X
from xbe_va import XBE, U803_SHA256, fmt

LIB = "/home/roasted/Desktop/Xbox/H2-Decomp/tu15-decomp/work/xdk5849/XDK/xbox/lib/xapilib.lib"
XBE_PATH = "/home/roasted/Desktop/Xbox/H2-Decomp/tu15-decomp/targets/halo2-tu15-u803/default.xbe"


def load_functions(d, resolved):
    funcs = {}
    per_obj_sizes = {}
    for objname, hoff, doff, size in resolved:
        r = X.parse_coff(d, doff)
        if r is None:
            continue
        sections, symbols = r
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
                    funcs[name] = body
    return funcs


def exec_regions(x):
    return [(s, x.data[s["raw"]:s["raw"] + s["rawsize"]])
            for s in x.sections if (s["flags"] & 0x4) and s["rawsize"]]


def find_all(blob, pat):
    out = []
    i = blob.find(pat)
    while i != -1:
        out.append(i)
        i = blob.find(pat, i + 1)
    return out


def main(argv):
    args = argv[1:]
    names = []
    minlen = 12
    all_hits = False
    dump = False
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--names":
            names += args[i + 1].split(",")
            i += 2
        elif a == "--min":
            minlen = int(args[i + 1])
            i += 2
        elif a == "--all-hits":
            all_hits = True
            i += 1
        elif a == "--dump":
            dump = True
            i += 1
        else:
            i += 1

    d, resolved, _ = X.parse_archive(LIB)
    funcs = load_functions(d, resolved)
    x = XBE(XBE_PATH, expect_sha256=U803_SHA256)

    targets = [(n, b) for n, b in funcs.items()
               if any(sub in n for sub in names)]

    print(f"lib functions loaded {len(funcs)}; targets {len(targets)}")
    regions = exec_regions(x)
    for name, fbytes in sorted(targets):
        if dump:
            print(f"\n=== {name} len={len(fbytes)} ===")
            print(fbytes.hex(" "))
            continue
        hits = []
        k_used = 0
        for k in (28, 20, 16, 12):
            pref = fbytes[:k]
            if len(pref) < k:
                continue
            hits = []
            for s, blob in regions:
                for off in find_all(blob, pref):
                    hits.append((s["va"] + off, s, off))
            if len(hits) >= 1 and (len(hits) == 1 or all_hits):
                k_used = k
                break
        if not hits:
            print(f"NO MATCH len={len(fbytes)}  {name}")
            continue
        for va, s, off in hits:
            ext = 0
            for b in fbytes:
                try:
                    got = x.read(va + ext, 1)[0]
                except ValueError:
                    break
                if got != b:
                    break
                ext += 1
            print(f"{va:08X}  {s['name']:<8} prefix={k_used} match={ext}/{len(fbytes)}  {name}")
            for ins in x.dis(va, 3):
                print(f"    {fmt(ins)}")
            if not all_hits:
                break


if __name__ == "__main__":
    main(sys.argv)
