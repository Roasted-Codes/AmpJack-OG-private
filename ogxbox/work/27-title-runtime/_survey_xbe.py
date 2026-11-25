#!/usr/bin/env python3
"""Read-only survey of the frozen u803 XBE: header, sections, pinned bytes."""
import json, struct, hashlib
P = '/home/roasted/Desktop/Xbox/H2-Decomp/tu15-decomp/targets/halo2-tu15-u803/default.xbe'
b = open(P, 'rb').read()
print('sha256', hashlib.sha256(b).hexdigest())
base, hs, img = struct.unpack_from('<III', b, 0x104)
n, sh = struct.unpack_from('<II', b, 0x11C)
ep, = struct.unpack_from('<I', b, 0x128)
th, = struct.unpack_from('<I', b, 0x158)
print('base', hex(base), 'hdr', hex(hs), 'image', hex(img), 'end', hex(base + img), 'nsec', n,
      'ep(enc)', hex(ep), 'thunk(enc)', hex(th))
secs = []
for i in range(n):
    f, va, vs, ra, rs, na = struct.unpack_from('<6I', b, sh - base + i * 56)
    nm = b[na - base:b.index(b'\0', na - base)].decode()
    secs.append((nm, va, vs, ra, rs, f))
    print(f'{nm:10s} va {va:#x}-{va+vs:#x} raw {ra:#x}+{rs:#x} flags {f:#x}')
def rd(va, k):
    for nm, v, vs, ra, rs, f in secs:
        if v <= va and va + k <= v + rs:
            return b[ra + va - v:ra + va - v + k]
for va in (0x33B590, 0x33C29D, 0x41B774, 0x41B784, 0x4155BF, 0x416992, 0x4165C6, 0x41517D, 0x4127D8, 0x4127B4):
    r = rd(va, 10)
    print(hex(va), r.hex() if r else None)
d = json.load(open('/home/roasted/Desktop/Xbox/AmpJack-OG/ogxbox/work/26-u803-bindings/bindings.json'))
print(json.dumps(d, indent=1)[:3000])
