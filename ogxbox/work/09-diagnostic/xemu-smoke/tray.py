#!/usr/bin/env python3
"""Set kernel cached SMC tray state (HalReadSMCTrayState globals) to MEDIA_DETECTED.
QMP blockdev-change-medium does not refresh xemu's SMC tray register, and the xemu
UI Load Disc path would persist dvd_path into xemu.toml (not approved).
tray.py read | set [VALUE, default 0x60; 0x10=open]"""
import os, struct, sys
sys.path.insert(0, os.path.expanduser('~/Desktop/Xbox/LAN_Stats/tools/xemu'))
from gdbrsp import RSP
ST, CNT, FLAG = 0x800423B4, 0x80043858, 0x80048E90
r = RSP(port=1236)
try:
    st, = struct.unpack('<I', r.read(ST, 4)); cnt, = struct.unpack('<I', r.read(CNT, 4))
    fl = r.read(FLAG, 1)[0]
    print('before state=0x%x count=%d flag=%d' % (st, cnt, fl))
    if sys.argv[1:2] == ['set']:
        v = int(sys.argv[2], 0) if len(sys.argv) > 2 else 0x60
        r.write(ST, struct.pack('<I', v)); r.write(CNT, struct.pack('<I', cnt + 1))
        st, = struct.unpack('<I', r.read(ST, 4)); cnt, = struct.unpack('<I', r.read(CNT, 4))
        print('after  state=0x%x count=%d' % (st, cnt))
finally:
    r.cont(); r.close()
