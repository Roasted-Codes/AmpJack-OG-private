#!/usr/bin/env python3
"""Bound the one real cable session independently of incoming chat turns."""
from pathlib import Path
import subprocess,json,time,hashlib
R=Path(__file__).resolve().parent
w=json.loads((R/'physical-window.json').read_text())
def run(args,check=True):
 p=subprocess.run(args,capture_output=True,text=True)
 if check and p.returncode:raise RuntimeError(str(args)+' '+p.stdout+p.stderr)
 return p
# Keep the recording through at least five host minutes; stop before6-min watchdog.
time.sleep(max(0,w['launch_epoch']+315-time.time()))
print('LAST_SAMPLE',run(['python3',str(R/'sample.py'),'physical-final'],False).stdout,flush=True)
print('LAST_SCREEN',run(['python3',str(R/'rt.py'),'shot','physical-final'],False).stdout,flush=True)
print('TRACE_STOP',run(['python3',str(R/'control.py'),'hmp','log none'],False).stdout,flush=True)
print('MANUAL_EXIT',run(['python3',str(R/'rt.py'),'key','--hold','1.3','BackSpace+Return','sleep:3'],False).stdout,flush=True)
print('EXIT_SCREEN',run(['python3',str(R/'rt.py'),'shot','physical-exit'],False).stdout,flush=True)
print('QMP_QUIT',run(['python3',str(R/'rt.py'),'quit']).stdout,flush=True)
time.sleep(3)
s=run(['systemctl','--user','is-active','ampjack-parent23-devkit.service'],False).stdout.strip();assert s=='inactive',s
assert not Path('/proc/2266537').exists(),'Native still active: disk reads forbidden'
tool=str(Path.home()/'.hermes/skills/xemu-development-workflow/scripts/roqfatx.py')
raw=subprocess.run(['python3',tool,str(R/'guest/iguana-dev.qcow2'),'E','/AmpJack-OG/gip-probe.log','cat'],capture_output=True,check=True).stdout
(R/'E-gip-probe-physical.log').write_bytes(raw)
block='GIPINIT'+raw.decode(errors='replace').rsplit('GIPINIT',1)[1]
(R/'physical-run.log').write_text(block)
assert hashlib.sha256((Path('/home/roasted/Desktop/_Parked/halo2-system-link-bridge/devkit--xemu--0.8.136/xemu.toml')).read_bytes()).hexdigest()=='58ea136fbe73a09928363d69d769eac96288b451f96a2f3534d305c25ea44841'
run(['systemctl','--user','stop','hermes-xbox-desktop.service'])
result={'native_exited':True,'private_desktop_stopped':True,'primary_config_unchanged':True,'finished_epoch':time.time(),'owner_confirmations':'Parent must reconcile actual1/2/3done messages; no automatic physical acceptance','rx_records':sum(x.startswith('RX ') for x in block.splitlines()),'state_records':sum(x.startswith('STATE ') for x in block.splitlines()),'events':[x for x in block.splitlines() if x.startswith(('GIP_ATTACH','ADDCOMPLETE','DETACH','REMOVED','STEPFAIL','CFGFAIL','GIPEXIT','ATTACH_REFUSED'))],'host_driver':str(Path('/sys/bus/usb/devices/3-1:1.0/driver').resolve())}
(R/'physical-result.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2),flush=True)
