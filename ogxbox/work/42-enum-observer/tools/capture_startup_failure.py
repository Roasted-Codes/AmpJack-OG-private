#!/usr/bin/env python3
"""Preserve the one launch's startup assertion. No launch or repair actions."""
import json
from pathlib import Path
import subprocess
import live_adapter as a
R=a.ROOT
out=R/'continuation';out.mkdir(exist_ok=True)
unit='ampjack-parent42-devkit.service'
fields='MESSAGE,_PID,_BOOT_ID,COREDUMP_PID,COREDUMP_EXE,COREDUMP_CMDLINE,COREDUMP_PROC_STAT,__REALTIME_TIMESTAMP'
command=['journalctl','--user','-u',unit,'-o','json','--all','--output-fields='+fields,'--no-pager']
p=subprocess.run(command,text=True,capture_output=True,check=True)
allowed=set(fields.split(','));records=[]
for line in p.stdout.splitlines():
    d=json.loads(line);records.append({k:v for k,v in d.items() if k in allowed})
a.save('continuation/launch-journal.json',dict(command=command,records=records))
messages='\n'.join(str(x.get('MESSAGE','')) for x in records)
(out/'launch-journal.txt').write_text(messages+'\n')
show=subprocess.run(['systemctl','--user','show',unit,'-p','ActiveState','-p','SubState','-p','MainPID','-p','Result','-p','ExecMainStatus','-p','ExecMainCode'],text=True,capture_output=True,check=True).stdout
(out/'unit-final.txt').write_text(show)
coredumps=[x for x in records if 'COREDUMP_PID' in x]
pids=sorted({int(x['COREDUMP_PID']) for x in coredumps})
assert pids==[2580515],pids
assert not Path('/proc/2580515').exists(),'native process still present'
assert not Path('/proc/2580475').exists(),'runtime worker still present'
starts=[]
for x in coredumps:
    st=x.get('COREDUMP_PROC_STAT')
    if st:
        starts.append(int(st.rsplit(')',1)[1].split()[19]))
lease=json.loads(a.LEASE.read_text());assert lease['boot_launch_commands']==1
assert 'display_very_early_init' in messages and 'gtkiconhelper.c:495' in messages
result=dict(native_pid=2580515,native_start_ticks_from_coredump=starts or None,
            boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
            native_exe=str(Path(lease['fresh_clone'])/'xemu'),native_sha256=a.obs.sha((Path(lease['fresh_clone'])/'xemu').read_bytes()),
            process_exit_verified=True,runtime_worker_exit_verified=True,unit_final=show,
            launch_commands_consumed=1,guest_title_boots_observed=0,qmp_rsp_connections=0,
            title_entry_observed=False,allocation=False,module_installed=False,passthrough_attached=False,
            first_failed_boundary='GTK/libdecor SVG icon loader assertion during display_very_early_init, before QMP availability',
            graceful_quit='not possible: native had already aborted; no QMP client connected',
            no_reset_no_kill_no_retry=True,trace_jsonl_created=(R/'trace.jsonl').exists(),
            manifest_hashes={str(f):a.obs.sha(f.read_bytes()) for f in (a.obs.ELF,a.obs.LAYOUT,a.obs.XBE,a.LOADER_PATH)},
            authored_tools={f.name:a.obs.sha(f.read_bytes()) for f in sorted((R/'tools').glob('*.py'))})
a.save('continuation/final-identity-cleanup.json',result)
print(json.dumps({k:v for k,v in result.items() if k not in ('authored_tools','manifest_hashes','unit_final')},indent=2))
