#!/usr/bin/env python3
"""Read-only: decode live diagnostic globals + residual ring slots (map: bin/AmpJackProbe.map).
The ring is reset (count=0) after each drain, so slots keep stale data of earlier batches
until overwritten: this is residual memory, NOT a complete event log. Continues VM."""
import json, os, struct, sys
sys.path.insert(0, os.path.expanduser('~/Desktop/Xbox/LAN_Stats/tools/xemu'))
from gdbrsp import RSP
HERE = os.path.dirname(os.path.abspath(__file__))
F = 'kind device a b port speed iface dclass dsub dproto ifclass ifsub ifproto nep niface vendor product find seq'.split()
RING, ARMED, LOGH = 0x1edc0, 0x239c8, 0x1d000
r = RSP(port=1236)
try:
    raw = r.read(RING, 76 * 12)
    tail = r.read(RING + 76 * 256, 8)
    a, s, lo = struct.unpack('<III', r.read(ARMED, 12))
    lh, = struct.unpack('<I', r.read(LOGH, 4))
finally:
    r.cont(); r.close()
slots = []
for i in range(12):
    v = dict(zip(F, struct.unpack_from('<19I', raw, 76 * i)))
    if v['kind'] == 0 and v['seq'] == 0:
        continue
    slots.append({'slot': i, **{k: hex(x) for k, x in v.items()}})
out = {'g_armed': a, 'g_seq': s, 'g_logOpen': lo, 'g_logHandle': hex(lh),
       'ring_count_overflow': struct.unpack('<II', tail), 'residual_slots': slots}
print(json.dumps(out, indent=1))
if len(sys.argv) > 1:
    open(os.path.join(HERE, sys.argv[1]), 'w').write(json.dumps(out, indent=1) + '\n')
