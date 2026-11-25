#!/usr/bin/env python3
import sys
sys.dont_write_bytecode=True
import json
import os
from pathlib import Path
import subprocess
import sys
import live_adapter as a
R=a.ROOT
sys.path.insert(0,str(R))
from parent_launch import receipt, environment
lease=receipt(); guest=Path(lease['fresh_clone'])
environment(lease)
procs=[]
for p in Path('/proc').iterdir():
    if not p.name.isdigit():continue
    try:
        exe=(p/'exe').resolve(strict=True)
        if exe.name.lower()=='xemu' or 'xemu.appimage' in exe.name.lower() or exe.name.startswith('qemu-system'):procs.append(a.native(int(p.name)))
    except (OSError,ProcessLookupError):pass
assert len(procs)<2
# No offline disk reads if any process owns this exact disk.
disk=guest/'iguana-dev.qcow2'
for fd in Path('/proc').glob('[0-9]*/fd/*'):
    try: assert fd.resolve()!=disk.resolve(),str(fd)
    except OSError: pass
roq=a.load_file('roq_w45','/home/roasted/.hermes/skills/xemu-development-workflow/scripts/roqfatx.py')
dev=roq.Qcow2(str(disk)); listing={}; hashes={}
try:
    for part,paths in {'C':['/'],'E':['/','/DEVKIT','/DEVKIT/Tools','/DEVKIT/Tools/Halo2','/Tools','/Tools/Halo2','/TDATA/4d530064','/TDATA/4d530064/$u','/dashboard.xbx']}.items():
        off,length=roq.PARTS[part]; fs=roq.Fatx(dev,off,length)
        for path in paths:
            x=fs.find(path)
            if x and x[1]:listing[part+':'+path]=list(fs.listdir(x[0]))
            elif x:
                data=fs.read(path);hashes[part+':'+path]={'sha256':a.obs.sha(data),'size':len(data)}
                if path=='/dashboard.xbx':listing['dashboard_shortcut_ascii']=data.decode('latin1',errors='replace')
        if part=='E':
            for path in ('/DEVKIT/Tools/Halo2/default.xbe','/Tools/Halo2/default.xbe','/TDATA/4d530064/$u/default.xbe'):
                data=fs.read(path)
                if data:hashes[part+':'+path]={'sha256':a.obs.sha(data),'size':len(data)}
finally:dev.f.close()
usb=[]
for d in Path('/sys/bus/usb/devices').iterdir():
    try:
        if (d/'idVendor').read_text().strip()=='045e' and (d/'idProduct').read_text().strip()=='0b12':
            info={k:(d/k).read_text().strip() for k in ('busnum','devnum','speed')};info['sysfs']=str(d)
            node=Path(f"/dev/bus/usb/{int(info['busnum']):03d}/{int(info['devnum']):03d}")
            info.update(node=str(node),readable=os.access(node,os.R_OK),writable=os.access(node,os.W_OK));usb.append(info)
    except OSError:pass
assert len(usb)==1 and usb[0]['readable'] and usb[0]['writable']
assert a.obs.sha((guest/'xemu').read_bytes())==lease['xemu_sha256']
ldd=subprocess.run(['ldd',str(guest/'xemu')],text=True,capture_output=True,check=True).stdout
assert 'not found' not in ldd
env=json.loads(Path(lease['environment_file']).read_text());assert env['DISPLAY']==':2' and Path(env['WAYLAND_DISPLAY']).is_socket()
result=dict(native_guests=procs,listing=listing,hashes=hashes,usb=usb,dependencies=ldd,environment=env,
            config_sha256=a.obs.sha((guest/'xemu.toml').read_bytes()),loader_sha256=a.obs.sha(a.LOADER_PATH.read_bytes()),lease=lease)
a.save('continuation/preflight.json',result)
expected=a.obs.HASHES['xbe']
mismatches={key:value for key,value in hashes.items() if key in ('E:/DEVKIT/Tools/Halo2/default.xbe','E:/TDATA/4d530064/$u/default.xbe') and value['sha256']!=expected}
missing=[key for key in ('E:/DEVKIT/Tools/Halo2/default.xbe','E:/TDATA/4d530064/$u/default.xbe') if key not in hashes]
if mismatches or missing:
    import time
    a.save('qualification.json',dict(runtime_authorized=False,epoch=time.time(),receipt_sha256=a.obs.sha(a.LEASE.read_bytes()),first_unsupported_boundary='required guest title artifact identity mismatch',expected_title_sha256=expected,mismatches=mismatches,missing=missing,launch_commands_used=0))
    raise SystemExit('STOP: required guest title hash mismatch; see qualification.json. No launch/claim permitted; no artifact substitution.')
print(json.dumps({k:v for k,v in result.items() if k not in ('dependencies','lease','environment')},indent=2))
