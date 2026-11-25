#!/usr/bin/env python3
"""Read-only title check: [0x10000] magic, XBE timestamp vs local file, regs. Continues VM."""
import json, os, struct, sys
sys.path.insert(0, os.path.expanduser('~/Desktop/Xbox/LAN_Stats/tools/xemu'))
from gdbrsp import RSP
HERE = os.path.dirname(os.path.abspath(__file__))
loc = open(os.path.join(HERE, 'default.xbe.copy'), 'rb').read()
r = RSP(port=1236)
try:
    hdr = r.read(0x10000, 0x180)
    regs = r.regs()
    res = {'magic': hdr[:4].decode('latin1'), 'ts_guest': hdr[0x114:0x118].hex(),
           'ts_local': loc[0x114:0x118].hex(), 'hdr_0x100_0x180_equal': hdr[0x100:0x180] == loc[0x100:0x180],
           'regs': {k: hex(v) for k, v in regs.items()}}
    print(json.dumps(res, indent=1))
    if len(sys.argv) > 1:
        open(os.path.join(HERE, sys.argv[1]), 'w').write(json.dumps(res, indent=1) + '\n')
finally:
    r.cont(); r.close()
