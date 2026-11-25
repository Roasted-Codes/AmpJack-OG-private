#!/usr/bin/env python3
"""Dump disassembly of a VA range in the u803 XBE. Read-only."""
import sys
sys.path.insert(0, "/home/roasted/Desktop/Xbox/LAN_Stats/tools")
from xbe_va import XBE, U803_SHA256, fmt

XBE_PATH = "/home/roasted/Desktop/Xbox/H2-Decomp/tu15-decomp/targets/halo2-tu15-u803/default.xbe"


def main(argv):
    va = int(argv[1], 0)
    n = int(argv[2], 0) if len(argv) > 2 else 0x140
    x = XBE(XBE_PATH, expect_sha256=U803_SHA256)
    for ins in x.dis(va, n):
        print(fmt(ins))


if __name__ == "__main__":
    main(sys.argv)
