#!/usr/bin/env python3
"""Finish this one listening window, quit cleanly, pull the real guest log."""
from pathlib import Path
import subprocess,time,json,hashlib,os
ROOT=Path(__file__).resolve().parent
PROJECT=ROOT.parents[2]
GUEST=ROOT/'guest'
RT=ROOT/'rt.py'
w=json.loads((ROOT/'button-window.json').read_text())
w['go_was_sent_before_epoch']=time.time()
(ROOT/'button-window.json').write_text(json.dumps(w,indent=2))
def run(args,check=True):
 r=subprocess.run(args,capture_output=True,text=True)
 if check and r.returncode:raise RuntimeError(str(args)+': '+r.stdout+r.stderr)
 return r
for t in (30,50,72):
 time.sleep(max(0,w['launch_epoch']+t-time.time()))
 result=run(['python3',str(RT),'shot','buttons-%02ds'%t],False)
 print('SCREEN',t,result.returncode,result.stdout,result.stderr,flush=True)
 if (ROOT/'usb.log').stat().st_size>240*1024*1024:break
print('TRACE_STOP',run(['python3',str(ROOT/'control.py'),'hmp','log none'],False).stdout,flush=True)
q=run(['python3',str(RT),'quit']);print('QMP_QUIT',q.returncode,q.stdout,flush=True)
time.sleep(3)
state=run(['systemctl','--user','is-active','ampjack-parent20-devkit.service'],False).stdout.strip();assert state=='inactive',state
assert not Path('/proc/2209761').exists(),'Native emulator still exists; do not read disk'
tool=str(Path.home()/'.hermes/skills/xemu-development-workflow/scripts/roqfatx.py')
raw=subprocess.run(['python3',tool,str(GUEST/'iguana-dev.qcow2'),'E','/AmpJack-OG/gip/gip-probe.log','cat'],capture_output=True,check=True).stdout
(ROOT/'E-gip-probe-button.log').write_bytes(raw)
block='GIPINIT'+raw.decode(errors='replace').rsplit('GIPINIT',1)[1]
(ROOT/'button-run.log').write_text(block)
sha=run(['python3',tool,str(GUEST/'iguana-dev.qcow2'),'E','/AmpJack-OG/gip/default.xbe','sha']).stdout.strip();assert w['candidate'] in sha
primary=Path('/home/roasted/Desktop/_Parked/halo2-system-link-bridge/devkit--xemu--0.8.136')
assert hashlib.sha256((primary/'xemu.toml').read_bytes()).hexdigest()=='58ea136fbe73a09928363d69d769eac96288b451f96a2f3534d305c25ea44841'
run(['systemctl','--user','stop','hermes-xbox-desktop.service'])
result={'capture_finished_epoch':time.time(),'guest_log':'button-run.log','candidate':sha,'native_exited':True,'private_desktop_stopped':True,'primary_config_unchanged':True,'RX':sum(l.startswith('RX ') for l in block.splitlines()),'TXDONE':sum(l.startswith('TXDONE ') for l in block.splitlines()),'state_lines':[l for l in block.splitlines() if l.startswith(('STATE','GIPSTATE'))],'auto_exit':'GIPEXIT auto' in block,'physical_completion':'Await actual owner done/confirmation; no failure verdict solely from empty state list','host_driver':str((Path('/sys/bus/usb/devices/3-1:1.0/driver')).resolve())}
(ROOT/'button-result.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result,indent=2),flush=True)
