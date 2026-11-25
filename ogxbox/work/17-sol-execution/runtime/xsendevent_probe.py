#!/usr/bin/env python3
"""Probe: does `xdotool keydown/keyup --window <id>` (XSendEvent, the dk.py
method) deliver a KeyPress to a harmless private window on :2? Mimics what SDL
must receive for menu control. No emulator, no uinput."""
import os, subprocess, sys, time
from pathlib import Path
from Xlib import display, X

DISP = ':2'
HOME = Path.home()
XD = str(HOME / '.local/bin/xdotool')
env = dict(os.environ, DISPLAY=DISP, LD_LIBRARY_PATH=str(HOME / '.local/lib'))
env.pop('XAUTHORITY', None)

d = display.Display(DISP)
root = d.screen().root
w = root.create_window(40, 40, 400, 120, 0, d.screen().root_depth,
                       X.InputOutput, X.CopyFromParent,
                       background_pixel=d.screen().white_pixel,
                       event_mask=X.KeyPressMask | X.KeyReleaseMask | X.ExposureMask)
w.set_wm_name('Hermes XSendEvent probe')
w.map()
d.sync()
time.sleep(0.5)

def xd(*a):
    return subprocess.run([XD, *a], env=env, capture_output=True, text=True)

# capture the window id as xdotool sees it
ids = xd('search', '--name', 'Hermes XSendEvent probe').stdout.split()
print('window ids:', ids)
wid = str(w.id)

# XSendEvent keydown/keyup directly to the window (no focus, no XTEST)
r1 = xd('keydown', '--window', wid, 'a')
time.sleep(0.1)
r2 = xd('keyup', '--window', wid, 'a')
time.sleep(0.2)
d.sync()

got = []
while d.pending_events():
    e = d.next_event()
    if e.type == X.KeyPress:
        got.append(('KeyPress', e.window.id, e.detail))
    elif e.type == X.KeyRelease:
        got.append(('KeyRelease', e.window.id, e.detail))

print('keydown rc=%s keyup rc=%s' % (r1.returncode, r2.returncode))
print('received:', got)

ok = any(t == 'KeyPress' and win == w.id for t, win, det in got)
print('RESULT:', 'XSendEvent DELIVERED KeyPress' if ok else 'NO KeyPress delivered')
w.destroy(); d.sync(); d.close()
sys.exit(0 if ok else 2)
