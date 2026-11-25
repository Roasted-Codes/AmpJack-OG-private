#!/usr/bin/env python3
"""Disassemble a window of a raw dump. usage: dis.py DUMP.bin DUMPBASE ADDR LEN [ADDR LEN...]"""
import os, subprocess, sys
m = open(sys.argv[1], 'rb').read(); base = int(sys.argv[2], 16)
a = sys.argv[3:]
for i in range(0, len(a), 2):
    s, n = int(a[i], 16), int(a[i+1], 16)
    tmp = os.environ.get('TMPDIR', '/tmp') + '/dis_win.bin'
    open(tmp, 'wb').write(m[s-base:s-base+n])
    out = subprocess.run(['objdump', '-D', '-b', 'binary', '-mi386', '-Mintel', f'--adjust-vma={s:#x}', tmp],
                         capture_output=True, text=True).stdout
    print(f'== {s:#x}')
    print('\n'.join(l[:100] for l in out.splitlines()[7:]))
