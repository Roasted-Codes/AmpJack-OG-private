#!/usr/bin/env python3
"""Read-only static facts from the frozen u803 XBE: entry, thunk, timestamp, callers, 7 hook orig5."""
import hashlib, json, struct, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / '27-title-runtime'))
from ogx_title_loader import HOOK_SITES, FROZEN_XBE, FROZEN_XBE_SHA256
HERE = Path(__file__).resolve().parent
b = FROZEN_XBE.read_bytes(); assert hashlib.sha256(b).hexdigest() == FROZEN_XBE_SHA256
u = lambda o: struct.unpack_from('<I', b, o)[0]
base = u(0x104); assert base == 0x10000
ep_raw, th_raw = u(0x128), u(0x158)
keys = {'retail': (0xA8FC57AB, 0x5B6D40B6), 'debug': (0x94859D4B, 0xEFB1F152)}
secs = []
for i in range(u(0x11C)):
    o = u(0x120) - base + i * 56
    va, vs, ra, rs = struct.unpack_from('<4I', b, o + 4)
    no = u(o + 20) - base
    secs.append(dict(name=b[no:no + 16].split(b'\0')[0].decode(), va=va, vsize=vs, raw=ra, rsize=rs))
def v2f(va):
    if base <= va < base + u(0x10C) and va - base < u(0x108):
        return va - base  # headers
    for s in secs:
        if s['va'] <= va < s['va'] + s['rsize']:
            return s['raw'] + va - s['va']
res = {'sha256': FROZEN_XBE_SHA256, 'timestamp_0x114': b[0x114:0x118].hex(' '), 'sections': secs}
for k, (ek, tk) in keys.items():
    ep, th = ep_raw ^ ek, th_raw ^ tk
    if any(s['va'] <= ep < s['va'] + s['vsize'] for s in secs) and any(s['va'] <= th < s['va'] + s['vsize'] for s in secs):
        res.update(key=k, entry=hex(ep), thunk=hex(th))
ep = int(res['entry'], 16); th = int(res['thunk'], 16)
thunks = []; o = v2f(th)
while u(o):
    thunks.append(u(o)); o += 4
res['thunk_count'] = len(thunks)
res['thunk_file_values'] = [hex(t) for t in thunks]
def callers(t):
    out = []
    for s in secs:
        for off in range(s['raw'], s['raw'] + s['rsize'] - 5):
            if b[off] == 0xE8:
                va = s['va'] + off - s['raw']
                if (va + 5 + struct.unpack_from('<i', b, off + 1)[0]) & 0xffffffff == t:
                    out.append(hex(va))
    return out
T = {'main_0x12E1A0': 0x12E1A0, 'XInitDevices_0x4139A0': 0x4139A0}
res['targets'] = {k: dict(bytes16=b[v2f(v):v2f(v) + 16].hex(' '), e8_callers=callers(v)) for k, v in T.items()}
res['header_0x178_sha256'] = hashlib.sha256(b[:0x178]).hexdigest()
res['hook_sites'] = {n: dict(va=hex(va), orig5=b[v2f(va):v2f(va) + 5].hex(' '), matches_pin=b[v2f(va):v2f(va) + 5] == orig5)
                     for n, (va, orig5, _d, _b) in HOOK_SITES.items()}
(HERE / 'static-xbe.json').write_text(json.dumps(res, indent=1))
(HERE / 'entry.bin').write_bytes(b[v2f(ep):v2f(ep) + 0x100])
print(json.dumps({k: v for k, v in res.items() if k not in ('thunk_file_values', 'sections')}, indent=1))
