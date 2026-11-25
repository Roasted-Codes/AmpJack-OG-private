#!/usr/bin/env python3
"""Read-only post-attempt evidence; no endpoint client, disk read or launch."""
import sys
sys.dont_write_bytecode=True
from pathlib import Path
import json
import os
import subprocess
R=Path(__file__).resolve().parents[1]
OUT=R/'continuation-2/live'
handle=json.loads((OUT/'launch-handle.json').read_text())
unit=handle['unit'];inv=handle['invocation_id'];cg=handle['properties']['ControlGroup']
def command(args):
    p=subprocess.run(args,capture_output=True,text=True)
    return dict(command=args,returncode=p.returncode,stdout=p.stdout,stderr=p.stderr)
rows=command(['journalctl','--user','_SYSTEMD_INVOCATION_ID='+inv,'--no-pager','-o','json'])
records=[json.loads(line) for line in rows['stdout'].splitlines()]
assert all(x.get('_SYSTEMD_INVOCATION_ID')==inv and x.get('_SYSTEMD_USER_UNIT')==unit for x in records)
(OUT/'post-attempt-invocation-journal.json').write_text(json.dumps(rows,indent=2)+'\n')
pids=[int(n) for n in (Path('/sys/fs/cgroup')/cg.lstrip('/')/'cgroup.procs').read_text().split()]
probes=[]
for pid in pids:
    p=Path('/proc')/str(pid);row=dict(pid=pid)
    for key,action in {
        'exe':lambda:str((p/'exe').resolve(strict=True)),
        'cmdline':lambda:(p/'cmdline').read_bytes().decode(errors='replace').split('\0'),
        'start_ticks':lambda:int((p/'stat').read_text().rsplit(')',1)[1].split()[19]),
        'cgroup':lambda:(p/'cgroup').read_text(),
        'maps_access':lambda:dict(readable=True,loaded_sdl=sorted({line.split()[-1] for line in (p/'maps').read_text().splitlines() if 'libSDL3.so' in line})),
        'auxv_access':lambda:dict(readable=True,bytes=len((p/'auxv').read_bytes())),
        'fd_targets':lambda:[dict(fd=fd.name,target=os.readlink(fd)) for fd in (p/'fd').iterdir()],
        'capability_status':lambda:{key:value.strip() for line in (p/'status').read_text().splitlines() if ':' in line for key,value in [line.split(':',1)] if key.startswith('Cap') or key in ('Uid','Gid','NoNewPrivs','CoreDumping')},
    }.items():
        try:row[key]=action()
        except OSError as error:row[key]=dict(error=repr(error),errno=error.errno)
    probes.append(row)
result=dict(unit=unit,invocation_id=inv,host_boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
    cgroup=cg,cgroup_pids=pids,processes=probes,unit_state=command(['systemctl','--user','show',unit,'--no-pager','--property=ActiveState,SubState,MainPID,InvocationID,ControlGroup,Restart']),
    unix=command(['ss','-xlpnH']),rsp=command(['ss','-ltnpH','sport = :1242']),
    journal_native_pids=sorted({int(x['_PID']) for x in records if x.get('_COMM')=='xemu'}),
    selected_hardware=[x['MESSAGE'] for x in records if str(x.get('MESSAGE','')).startswith('Selected physical device:')],
    receipt_sha256=__import__('hashlib').sha256((R/'PARENT-RUNTIME-LEASE.json').read_bytes()).hexdigest(),
    guest_clients_opened=0,passthrough_requested=False,cleanup='UNRESOLVED; no native identity relaxation, endpoint contact, quit, kill, reset or retry')
result['unix']['stdout']='\n'.join(line for line in result['unix']['stdout'].splitlines() if str(R.parent/'42-enum-observer/parent-prepared-guest/runtime/qmp.sock') in line)
(OUT/'post-attempt-resource-proof.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
