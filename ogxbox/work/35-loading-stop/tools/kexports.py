#!/usr/bin/env python3
"""Map addresses to nearest Xbox kernel export ordinal (kernel dump at 0x80010000).
usage: kexports.py KDUMP.bin ADDR...   ('all' lists every export)"""
import struct, sys
m = open(sys.argv[1], 'rb').read(); B = 0x80010000
pe = struct.unpack_from('<I', m, 0x3c)[0]; o = pe + 24
erva = struct.unpack_from('<I', m, o + 96)[0]
base, nf = struct.unpack_from('<II', m, erva + 16)
af = struct.unpack_from('<I', m, erva + 28)[0]
ex = {}
for i in range(nf):
    f = struct.unpack_from('<I', m, af + 4 * i)[0]
    if f:
        ex.setdefault(B + f, []).append(base + i)
print('kernel timestamp', hex(struct.unpack_from('<I', m, pe + 8)[0]), 'exports', len(ex))
if sys.argv[2:] == ['all']:
    for a in sorted(ex): print(hex(a), ex[a])
for s in sys.argv[2:]:
    if s == 'all': continue
    a = int(s, 16)
    b = max((x for x in ex if x <= a), default=None)
    print(s, f'ord{ex[b]}+{a-b:#x}' if b else '?')
