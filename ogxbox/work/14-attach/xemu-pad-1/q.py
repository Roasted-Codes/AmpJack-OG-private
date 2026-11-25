#!/usr/bin/env python3
"""q.py hmp 'cmd' | q.py qmp '{json}'  -- devkit QMP, prints result, appends to qmp-log.txt"""
import sys, json, time, os
sys.path.insert(0, os.path.expanduser('~/Desktop/Xbox/LAN_Stats/tools/xemu'))
from qmp import QMP
from pathlib import Path
Q = QMP('/home/roasted/Desktop/_Parked/halo2-system-link-bridge/devkit--xemu--0.8.136/runtime/qmp.sock')
op, arg = sys.argv[1], sys.argv[2]
if op == 'hmp': r = Q.hmp(arg)
else:
    j = json.loads(arg); r = Q.cmd(j['execute'], **j.get('arguments', {}))
Q.close()
out = r if isinstance(r, str) else json.dumps(r)
print(out)
with open(Path(__file__).parent / 'qmp-log.txt', 'a') as f:
    f.write(f"### {time.strftime('%H:%M:%S')} {op} {arg}\n{out}\n")
