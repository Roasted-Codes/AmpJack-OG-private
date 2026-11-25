#!/usr/bin/env python3
"""Timed run: A (launch) -> shots -> wait yellow -> QMP hot-add hub+pad -> shots to 75 s."""
import os, subprocess, sys, time, json
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.expanduser('~/Desktop/Xbox/LAN_Stats/tools/xemu'))
from qmp import QMP
SOCK = '/home/roasted/Desktop/_Parked/halo2-system-link-bridge/devkit--xemu--0.8.136/runtime/qmp.sock'
LOG = open(os.path.join(HERE, 'run-log.txt'), 'a')


def log(s):
    line = '%s +%.1fs %s' % (time.strftime('%H:%M:%S'), time.time() - T0, s)
    print(line, flush=True); LOG.write(line + '\n'); LOG.flush()


def sh(*a):
    return subprocess.run(a, cwd=HERE, capture_output=True, text=True).stdout.strip()


def shot(name):
    p = sh('python3', 'dkx.py', 'shot', name)
    col = sh('magick', p, '-crop', '64x64+288+208', '-resize', '1x1!', '-format', '%[pixel:p{0,0}]', 'info:')
    log('shot %s centre=%s' % (name, col))
    return col


def q(cmd, **kw):
    Q = QMP(SOCK)
    try:
        r = Q.hmp(kw['c']) if cmd == 'hmp' else Q.cmd(cmd, **kw)
    finally:
        Q.close()
    log('QMP %s %s -> %s' % (cmd, json.dumps(kw), r if isinstance(r, str) else json.dumps(r)))
    return r


T0 = time.time()
sh('python3', 'dkx.py', 'key', 'a')
log('A pressed (launch E:\\AmpJack-OG\\gip\\default.xbe)')
time.sleep(3 - (time.time() - T0))
c = shot('20-run-03s')
for i in range(6):
    if 'srgb(255,255,0)' in c or 'yellow' in c:
        break
    time.sleep(1); c = shot('20-run-wait%d' % i)
log('armed-colour=%s; hot-adding' % c)
q('device_add', driver='usb-hub', id='pt_hub', bus='usb-bus.1', port='1.2', ports=3)
q('device_add', driver='usb-host', id='pt_pad', bus='usb-bus.1', port='1.2.1', vendorid=1118, productid=2834)
time.sleep(1.5)
q('hmp', c='info usb')
log('host driver 3-1:1.0 = %r' % (os.path.realpath('/sys/bus/usb/devices/3-1:1.0/driver')
                                  if os.path.exists('/sys/bus/usb/devices/3-1:1.0/driver') else ''))
for t, n in [(8, '21-run-08s'), (12, '21-run-12s'), (18, '21-run-18s'), (25, '22-run-25s'),
             (40, '22-run-40s'), (58, '23-run-58s'), (65, '24-run-65s'), (72, '24-run-72s'), (78, '25-run-78s')]:
    d = t - (time.time() - T0)
    if d > 0:
        time.sleep(d)
    shot(n)
q('query-status')
log('done')
