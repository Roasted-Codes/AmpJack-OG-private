#!/usr/bin/env python3
"""One owned GDB client (existing LAN_Stats gdbrsp.RSP) on loopback 1239.

Emulator (Z0) breakpoints are set BEFORE the title launch. Hits whose live XBE
timestamp at 0x10114 != u803 (2b a6 00 46) are ignored (bp removed, one step,
bp re-inserted, continue). Authenticated hits are logged in order. The client
stops for good at the FIRST authenticated hit of TU main 0x12E1A0 provided no
authenticated XInitDevices hit (thunk 0x4139A0, body 0x412D37, call site
0x1273F4) came first. If an XInitDevices hit comes first it halts there and
records FAIL_ORDER. Then: record full raw 'g' packet, guards, live thunk table,
remove ALL breakpoints, close socket WITHOUT 'D' (CPU stays halted).
"""
import json, socket, sys, time, hashlib
from pathlib import Path
sys.path.insert(0, '/home/roasted/Desktop/Xbox/LAN_Stats/tools/xemu')
from gdbrsp import RSP
HERE = Path(__file__).resolve().parent
PORT = 1239
TS = bytes.fromhex('2ba60046')
S = json.loads((HERE / 'static-xbe.json').read_text())
FROZEN = Path('/home/roasted/Desktop/Xbox/H2-Decomp/tu15-decomp/targets/halo2-tu15-u803/default.xbe').read_bytes()
ENTRY = int(S['entry'], 16)
BPS = {ENTRY: 'xbe_entry', 0x121D2: 'call_main_site', 0x12E1A0: 'main',
       0x1273F4: 'call_XInitDevices_site', 0x4139A0: 'XInitDevices_thunk', 0x412D37: 'XInitDevices_body'}
INIT = {0x1273F4, 0x4139A0, 0x412D37}
LOG = HERE / 'logs/hold.log'
def log(*a):
    line = time.strftime('%H:%M:%S ') + ' '.join(str(x) for x in a)
    print(line, flush=True)
    with LOG.open('a') as f: f.write(line + '\n')

r = RSP(port=PORT, timeout=10)
log('connected; initial stop', r.last_stop, 'reason', r.reason())
# expected code bytes for the guarded addresses (frozen file) -> checked on authenticated hits
for a in BPS: r.bp(a)
log('breakpoints set', {hex(a): n for a, n in BPS.items()})
hits = []
result = None
try:
    while True:
        r.cont()
        while True:
            try:
                pkt = r.recv(timeout=60); break
            except socket.timeout:
                log('waiting (VM running)...')
        regs = r.regs(); eip = regs['eip']
        try: ts = r.read(0x10114, 4)
        except Exception as e: ts = b''
        auth = ts == TS
        hits.append(dict(t=time.time(), eip=hex(eip), name=BPS.get(eip, '?'), ts=ts.hex(), auth=auth, pkt=pkt))
        log('stop', pkt, 'eip', hex(eip), BPS.get(eip, '?'), 'ts', ts.hex(), 'AUTH' if auth else 'ignored')
        if eip not in BPS:
            result = 'UNEXPECTED_STOP'; break
        if auth and eip == ENTRY and len(sys.argv) > 1 and sys.argv[1] == '--at-entry':
            result = 'XBE_ENTRY_BEFORE_XINITDEVICES'; break
        if auth and eip == 0x12E1A0:
            result = 'MAIN_BEFORE_XINITDEVICES'; break
        if auth and eip in INIT:
            result = 'FAIL_ORDER_XINITDEVICES_FIRST'; break
        r.bp(eip, False); r.step(); r.bp(eip, True)
    raw = r.raw_regs()
    st = dict(result=result, stop_packet=pkt, raw_g_packet=raw, regs={k: hex(v) for k, v in r.regs().items()}, hits=hits)
    st['live_ts_0x10114'] = r.read(0x10114, 4).hex(' ')
    hdr = r.read(0x10000, 0x178)
    st['live_header_0x178_sha256'] = hashlib.sha256(hdr).hexdigest();    st['live_header_matches_frozen'] = hdr == FROZEN[:0x178]
    st['live_header_diff'] = [dict(off=hex(i), live=hdr[i], frozen=FROZEN[i]) for i in range(0x178) if hdr[i] != FROZEN[i]]
    st['live_bytes_at_eip16'] = r.read(regs['eip'], 16).hex(' ')
    st['hook_sites_live'] = {n: dict(va=s['va'], live5=r.read(int(s['va'], 16), 5).hex(' '), orig5=s['orig5'],
                                     original=r.read(int(s['va'], 16), 5).hex(' ') == s['orig5']) for n, s in S['hook_sites'].items()}
    st['xinitdevices_live16'] = r.read(0x4139A0, 16).hex(' ')
    st['main_live16'] = r.read(0x12E1A0, 16).hex(' ')
    th = int(S['thunk'], 16); n = S['thunk_count']
    live = r.read(th, 4 * n)
    st['kernel_thunks_resolved'] = [hex(int.from_bytes(live[i*4:i*4+4], 'little')) for i in range(n)]
    st['kernel_thunks_all_resolved'] = all(int(x, 16) >= 0x80000000 for x in st['kernel_thunks_resolved'])
    st['esp_stack64'] = r.read(regs['esp'], 64).hex(' ')
finally:
    for a in BPS:
        try: r.bp(a, False)
        except Exception as e: log('unbreak', hex(a), e)
    log('all breakpoints removed; closing socket without D')
    r.close()
    try:
        (HERE / 'stop-state.json').write_text(json.dumps(st, indent=1))
        log('RESULT', st['result'], 'eip', st['regs']['eip'], 'header_match', st['live_header_matches_frozen'],
            'sites_orig', all(v['original'] for v in st['hook_sites_live'].values()), 'thunks_resolved', st['kernel_thunks_all_resolved'])
    except NameError:
        (HERE / 'stop-state.json').write_text(json.dumps(dict(result=result or 'EXCEPTION', hits=hits), indent=1))
