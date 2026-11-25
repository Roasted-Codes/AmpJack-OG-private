import sys, struct
sys.path.insert(0, "/home/roasted/Desktop/Xbox/LAN_Stats/tools")
from xbe_va import XBE, U803_SHA256
x = XBE("/home/roasted/Desktop/Xbox/H2-Decomp/tu15-decomp/targets/halo2-tu15-u803/default.xbe", expect_sha256=U803_SHA256)
for va, n in ((0x4155BF, 14), (0x416992, 10), (0x1273DC, 8)):
    print("0x%X (%d): %s" % (va, n, x.read(va, n).hex(" ")))
