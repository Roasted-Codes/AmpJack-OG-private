#!/usr/bin/env python3
"""Scan a dumped kernel stack for return addresses that follow a CALL.
usage: stackscan.py STACK.bin STACK_BASE_HEX LO_HEX HI_HEX code1.bin:base ...
Prints [addr] value region call-check. Pure offline; no guest access.
"""
import struct, sys

st = open(sys.argv[1], 'rb').read(); sb = int(sys.argv[2], 16)
lo, hi = int(sys.argv[3], 16), int(sys.argv[4], 16)
codes = []
for a in sys.argv[5:]:
    p, b = a.rsplit(':', 1); codes.append((int(b, 16), open(p, 'rb').read()))


def byte_at(v, k):
    for b, d in codes:
        if b <= v - k and v < b + len(d):
            return d[v - k - b:v - b]
    return None


def is_ret(v):
    for k, test in ((5, lambda x: x[0] == 0xe8), (6, lambda x: x[0] == 0xff and (x[1] >> 3) & 7 == 2),
                    (2, lambda x: x[0] == 0xff and (x[1] >> 3) & 7 == 2), (3, lambda x: x[0] == 0xff and (x[1] >> 3) & 7 == 2),
                    (7, lambda x: x[0] == 0xff and (x[1] >> 3) & 7 == 2)):
        x = byte_at(v, k)
        if x and test(x):
            if k == 5:
                return 'call %08x' % ((v + struct.unpack('<i', x[1:5])[0]) & 0xffffffff)
            return 'call indirect(%d)' % k
    return None


for off in range(lo - sb, hi - sb, 4):
    v = struct.unpack_from('<I', st, off)[0]
    r = is_ret(v)
    if r:
        print(f'[{sb+off:08x}] {v:08x} {r}')
