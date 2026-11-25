#!/usr/bin/env python3
import struct
XBE = "/home/roasted/Desktop/Xbox/H2-Decomp/tu15-decomp/targets/halo2-tu15-u803/default.xbe"
data = open(XBE, "rb").read()
u32 = lambda o: struct.unpack_from("<I", data, o)[0]
base = u32(0x104); nsec = u32(0x11C); sec_addr = u32(0x120)
secs = []
for k in range(nsec):
    o = sec_addr - base + k * 0x38; np = u32(o + 20) - base
    secs.append(dict(name=data[np:np+16].split(b"\0")[0].decode(), flags=u32(o),
                     va=u32(o + 4), vs=u32(o + 8), raw=u32(o + 12), rs=u32(o + 16)))
def va_off(va):
    for s in secs:
        if s["va"] <= va < s["va"] + s["vs"] and va - s["va"] < s["rs"]:
            return s["raw"] + (va - s["va"])
    return None
print("class table [0x4127B4..0x4127CC):")
p = 0x4127B4
while p < 0x4127CC:
    o = va_off(p); ptr = u32(o)
    if ptr == 0:
        print("  %08X -> NULL" % p)
    else:
        po = va_off(ptr)
        mb0 = data[po]; mb1 = data[po+1]; reg = u32(po+4); att = u32(po+8); rm = u32(po+12)
        print("  %08X -> 0x%08X [mb0=0x%02X mb1=0x%02X reg=0x%X att=0x%X rm=0x%X]" %
              (p, ptr, mb0, mb1, reg, att, rm))
    p += 4
o = va_off(0x4127D8)
print("XDEVICE_TYPE_GAMEPAD @0x4127D8 = 0x%08X" % u32(o))
