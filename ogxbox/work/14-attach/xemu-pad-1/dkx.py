#!/usr/bin/env python3
"""Thin wrapper over LAN_Stats dk.py that saves screenshots under this folder.
  dkx.py shot NAME | key [--hold s] [--gap s] k1 ... | combo HOLD k1 k2 ..."""
import os, subprocess, sys, time
from pathlib import Path
sys.path.insert(0, os.path.expanduser('~/Desktop/Xbox/LAN_Stats/work/autoboot'))
import dk  # noqa
HERE = Path(__file__).resolve().parent

op = sys.argv[1]
if op == 'shot':
    p = HERE / f'{sys.argv[2]}.png'
    subprocess.run(['import', '-display', ':2', '-window', dk.win(), str(p)], env=dk.ENV, check=True)
    print(p)
elif op == 'key':
    a = sys.argv[2:]; hold = 0.08; gap = 0.8
    while a and a[0] in ('--hold', '--gap'):
        if a[0] == '--hold': hold = float(a[1])
        else: gap = float(a[1])
        a = a[2:]
    dk.key(a, hold, gap); print('keys', *a, time.strftime('%H:%M:%S'))
elif op == 'combo':  # hold several keys simultaneously
    hold = float(sys.argv[2]); ks = sys.argv[3:]; w = dk.win()
    for k in ks: dk.run(dk.XD, 'keydown', '--window', w, k)
    time.sleep(hold)
    for k in reversed(ks): dk.run(dk.XD, 'keyup', '--window', w, k)
    print('combo', hold, *ks, time.strftime('%H:%M:%S'))
