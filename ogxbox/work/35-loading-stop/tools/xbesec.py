#!/usr/bin/env python3
"""Print XBE section table from a dump of the live header page at 0x10000 and
locate addresses. usage: xbesec.py HDR.bin [ADDR...]"""
import struct, sys
m = open(sys.argv[1], 'rb').read(); B = 0x10000
assert m[:4] == b'XBEH', m[:4]
ts = struct.unpack_from('<I', m, 0x114)[0]
n, sh = struct.unpack_from('<II', m, 0x11c)
print('XBE timestamp', hex(ts), 'sections', n)
secs = []
for i in range(n):
    flags, va, vs, ra, rs, name = struct.unpack_from('<IIIIII', m, sh - B + 56 * i)
    nm = m[name - B:m.index(b'\0', name - B)].decode() if B <= name < B + len(m) else hex(name)
    secs.append((va, vs, nm)); print(f'  {nm:10s} {va:#010x} {vs:#x}')
for s in sys.argv[2:]:
    a = int(s, 16)
    print(s, [f'{nm}+{a-va:#x}' for va, vs, nm in secs if va <= a < va + vs] or '-')
