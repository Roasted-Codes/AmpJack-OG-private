#!/usr/bin/env python3
"""Owned :2 UI navigation/capture only; NEVER modern-pad input evidence."""
import sys
sys.dont_write_bytecode=True
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import live_adapter as a
R=a.ROOT
lease=json.loads(a.LEASE.read_text());ident=json.loads((R/'live/native-identity.json').read_text());a.check_native(ident,lease)
sys.path.insert(0,str(R))
from parent_launch import receipt, environment
lease=receipt()
env=environment(lease)
env['LD_LIBRARY_PATH']='/home/roasted/.local/lib'
env.pop('XAUTHORITY',None);assert env['DISPLAY']==':2'
XD='/home/roasted/.local/bin/xdotool'
def cmd(*args):return subprocess.check_output(args,env=env,text=True).strip()
wins=[]
for w in cmd(XD,'search','--name','xemu').split():
    try:
        if int(cmd(XD,'getwindowpid',w))==ident['pid']:wins.append(w)
    except Exception:pass
assert len(wins)==1,wins
w=wins[0]
if sys.argv[1]=='shot':
    p=R/'live'/sys.argv[2];assert p.parent==R/'live'
    subprocess.run(['import','-display',':2','-window',w,str(p)],env=env,check=True);print(p)
elif sys.argv[1]=='key':
    cmd(XD,'windowactivate','--sync',w);time.sleep(.2);cmd(XD,'windowfocus','--sync',w);time.sleep(.2)
    assert cmd(XD,'getwindowfocus')==w
    for k in sys.argv[2:]:
        assert k in ('Up','Down','Left','Right','a','b','Return'),k
        cmd(XD,'keydown',k);time.sleep(.10);cmd(XD,'keyup',k);time.sleep(.8)
    print('DASHBOARD NAVIGATION ONLY',sys.argv[2:])
else:raise SystemExit('shot NAME | key KEYS')
