#!/usr/bin/env python3
"""Timed run v3: A (launch) -> wait yellow -> QMP hot-add hub+pad -> PRESS_NOW -> shots to 78 s."""
import os, subprocess, sys, time, json, datetime
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.expanduser('~/Desktop/Xbox/LAN_Stats/tools/xemu'))
from qmp import QMP
SOCK = '/home/roasted/Desktop/_Parked/halo2-system-link-bridge/devkit--xemu--0.8.136/runtime/qmp.sock'
PRESS = os.path.join(os.path.dirname(HERE), 'PRESS_NOW')
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
time.sleep(max(0, 3 - (time.time() - T0)))
c = shot('20-run-03s')
for i in range(6):
    if 'srgb(255,255,0)' in c or 'yellow' in c:
        break
    time.sleep(1); c = shot('20-run-wait%d' % i)
log('armed-colour=%s; hot-adding' % c)
q('device_add', driver='usb-hub', id='pt_hub', bus='usb-bus.1', port='1.2', ports=3)
q('device_add', driver='usb-host', id='pt_pad', bus='usb-bus.1', port='1.2.1', vendorid=1118, productid=2834)
ts = datetime.datetime.now().astimezone().isoformat(timespec='seconds')
open(PRESS, 'w').write(ts + '\n')
log('PRESS_NOW written %s' % ts)
time.sleep(1.0)
q('hmp', c='info usb')
log('host driver 3-1:1.0 = %r' % (os.path.realpath('/sys/bus/usb/devices/3-1:1.0/driver')
                                  if os.path.exists('/sys/bus/usb/devices/3-1:1.0/driver') else ''))
for t in (8, 20, 35, 50, 58, 66, 76):
    d = t - (time.time() - T0)
    if d > 0:
        time.sleep(d)
    shot('2x-run-%02ds' % t)
q('query-status')
log('done')
