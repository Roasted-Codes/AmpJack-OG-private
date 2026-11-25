#!/usr/bin/env python3
"""Read-only: locate kernel export HalReadSMCTrayState (ord 9) and dump its code.
Always continues the VM before exit."""
import os, struct, subprocess, sys
sys.path.insert(0, os.path.expanduser('~/Desktop/Xbox/LAN_Stats/tools/xemu'))
from gdbrsp import RSP
HERE = os.path.dirname(os.path.abspath(__file__))
r = RSP(port=1236)
try:
    K = 0x80010000
    mz = r.read(K, 0x40); pe = struct.unpack_from('<I', mz, 0x3C)[0]
    nt = r.read(K + pe, 0xF8)
    exp_rva, exp_sz = struct.unpack_from('<II', nt, 0x78)
    ed = r.read(K + exp_rva, 40)
    base, nfun = struct.unpack_from('<II', ed, 16)
    aof = struct.unpack_from('<I', ed, 28)[0]
    funcs = struct.unpack('<%dI' % nfun, r.read(K + aof, 4 * nfun))
    out = {}
    for o in (9, 10, 11):  # HalReadSMCTrayState=9, HalReadWritePCISpace=?
        va = K + funcs[o - base]
        code = r.read(va, 0x80)
        open(f'{HERE}/ord{o}.bin', 'wb').write(code)
        out[o] = hex(va)
    print('base', base, 'nfun', nfun, out)
    print('regs', {k: hex(v) for k, v in r.regs().items() if k in ('eip', 'esp')})
finally:
    r.cont(); r.close()
