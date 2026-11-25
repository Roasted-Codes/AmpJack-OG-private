#!/usr/bin/env python3
"""Worker35 read-only probe of the live runtime31 guest.

One QMP client (greeting + query-status, closes BOTH makefile and socket),
then one RSP client: read regs/target.xml/memory ranges, ALWAYS 'c' in finally,
then QMP query-status again. No writes, no reset, no detach.
usage: probe.py OUTDIR [addr:len ...]   (hex)
"""
import json, os, socket, sys, time
sys.path.insert(0, os.path.expanduser('~/Desktop/Xbox/LAN_Stats/tools/xemu'))
from gdbrsp import RSP

QMP_SOCK = '/home/roasted/Desktop/Xbox/AmpJack-OG/ogxbox/work/31-title-runtime/guest/runtime/qmp.sock'
GDB_PORT = 1239
PID, START = 2533644, 18411909


def qmp_status():
    s = socket.socket(socket.AF_UNIX)
    s.settimeout(10)
    s.connect(QMP_SOCK)
    f = s.makefile('rwb')
    try:
        def rd():
            while True:
                m = json.loads(f.readline())
                if 'event' not in m:
                    return m
        greet = rd()
        f.write(b'{"execute":"qmp_capabilities"}\n'); f.flush(); rd()
        f.write(b'{"execute":"query-status"}\n'); f.flush()
        return {'greeting_ok': 'QMP' in greet, 'status': rd().get('return')}
    finally:
        f.close(); s.close()


def native_ok():
    st = open(f'/proc/{PID}/stat').read()
    return int(st.rsplit(')', 1)[1].split()[19]) == START


def main():
    out = sys.argv[1]; os.makedirs(out, exist_ok=True)
    ranges = [tuple(int(x, 16) for x in a.split(':')) for a in sys.argv[2:]]
    rec = {'t0': time.time(), 'native_identity_ok': native_ok(), 'qmp_before': qmp_status()}
    r = RSP(port=GDB_PORT, timeout=10)
    try:
        rec['stop_on_connect'] = r.last_stop
        if r.last_stop is None:
            rec['reason'] = r.reason()
        rec['regs'] = r.regs()
        raw = r.raw_regs(); rec['raw_g_len'] = len(raw) // 2
        open(f'{out}/g.hex', 'w').write(raw)
        if not os.path.exists(f'{out}/target.xml'):
            x = r.target_xml(); open(f'{out}/target.xml', 'w').write(x)
            import re
            for inc in re.findall(r'href="([^"]+)"', x):
                open(f'{out}/{inc}', 'w').write(r.target_xml(inc))
        rec['reads'] = {}
        for a, n in ranges:
            # page-wise; unreadable pages stored as zeros and listed
            buf, bad = bytearray(), []
            for p in range(a, a + n, 0x1000):
                k = min(0x1000, a + n - p)
                try:
                    buf += r.read(p, k)
                except Exception:
                    buf += bytes(k); bad.append(f'{p:08x}')
            open(f'{out}/mem_{a:08x}_{n:x}.bin', 'wb').write(buf)
            rec['reads'][f'{a:08x}'] = {'len': n, 'unreadable_pages': bad}
        rec['regs_after'] = r.regs()
    finally:
        r.cont()
        time.sleep(0.2)
        r.close()
    rec['qmp_after'] = qmp_status()
    rec['native_identity_ok_after'] = native_ok()
    json.dump(rec, open(f'{out}/probe-{int(rec["t0"])}.json', 'w'), indent=1)
    print(json.dumps({k: v for k, v in rec.items() if k != 'reads'}, indent=1))
    print('reads', rec['reads'])


if __name__ == '__main__':
    main()
