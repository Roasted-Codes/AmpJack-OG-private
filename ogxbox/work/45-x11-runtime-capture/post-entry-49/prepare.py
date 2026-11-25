#!/usr/bin/env python3
"""Mechanical PREPARE_ONLY checkpoint; no launch, claim or runtime clients."""
import sys
sys.dont_write_bytecode=True
import ast
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
R=Path(__file__).resolve().parents[1];D=R/'post-entry-49'
sys.path[:0]=[str(R),str(R/'tools')]
import parent_launch as w
import enum_watch as e
slot=w.resolve_active_slot(require_confirmation=False)
assert slot.path==D and not slot.claim.exists()
run_id=str(time.time_ns());commands=[];receipts={};fixtures={};counts={};runs=[]
def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def exclusive(path,value):
    with path.open('x') as f:json.dump(value,f,indent=2,sort_keys=True);f.write('\n')
def run(cmd,label,env=None):
    p=subprocess.run(cmd,capture_output=True,text=True,env=env)
    log=D/(label+'-'+run_id+'.log');log.write_text(p.stdout+p.stderr)
    commands.append(dict(command=cmd,exit_code=p.returncode,log=str(log)))
    (D/'prepare-commands.json').write_text(json.dumps(commands,indent=2)+'\n')
    assert p.returncode==0,(label,p.returncode,str(log))
    return p
normal=dict(os.environ);normal.pop('HERMES_SESSION_ID',None)
(D/'receipts').mkdir(exist_ok=True)
before_sources={str(p):sha(p) for p in [R/'parent_launch.py',*sorted((R/'tools').glob('*.py')),Path(__file__)]}
for name,pointer,expected in (('test_continuation.py','result.json',31),('test_recovery.py','recovery-result.json',15),('test_post_entry47.py','fresh-result.json',22),('test_fd_snapshot48.py',None,10),('test_active_slot49.py',None,17)):
    p=run(['/usr/bin/python3','-B',str(R/'tools'/name)],name.removesuffix('.py'),env=normal)
    if pointer:
        latest=json.loads((D/'tests'/pointer).read_text());root=Path(latest['evidence']);raw_path=root/pointer
    else:
        last=json.loads(p.stdout.splitlines()[-1]);root=Path(last.get('directory') or last['evidence']);raw_path=root/'result.json'
    result=json.loads(raw_path.read_text());count=result.get('tests_run',result.get('tests'))
    assert result['all_passed'] and count==expected,(name,result)
    receipt=D/'receipts'/(name.removesuffix('.py')+'-'+run_id+'.json')
    exclusive(receipt,dict(all_passed=True,exit_code=p.returncode,tests_run=count,fixture_only=True,raw_result=str(raw_path),raw_sha256=sha(raw_path),command=commands[-1],source_hashes=before_sources))
    receipts[str(receipt)]=sha(receipt);counts[name]=count;runs.append(root)
    if name=='test_continuation.py':base_run=root
    if name=='test_fd_snapshot48.py':
        churn=json.loads((root/'test_actual_local_fd_churn/local-churn-result.json').read_text())
        assert churn['child_exit']==0 and churn['reaped'] and churn['proc_absent'] and not Path('/proc',str(churn['identity']['pid'])).exists()
run(['/usr/bin/python3','-B','/home/roasted/.local/share/xemu-safety/guard.py','--health-check'],'guard-health')
run(['/usr/bin/python3','-B',str(R/'tools/live_preflight.py'),'--active-slot'],'actual-stopped-preflight')
pre=json.loads((D/'preflight.json').read_text())
assert pre['qcow_check']['check-errors']==0 and not pre['qcow_info'].get('backing-filename')
run(['/usr/bin/python3','-B',str(R/'parent_launch.py'),'--command'],'guarded-command-generation')
assert not slot.claim.exists()
for path,digest in before_sources.items():assert sha(path)==digest,('source changed during qualification',path)
# Reuse the prior known dependency closure, not its authority or preparation.
prior=json.loads((R/'post-entry-47/SOURCE-MANIFEST.json').read_text())
files={p:sha(p) for p in prior['files'] if not p.startswith(str(R/'post-entry-47')+'/')}
files.update(before_sources)
for p in (D/'PARENT-RUNTIME-LEASE.json',D/'PARENT-CLOSED-PREFLIGHT.json',R/'continuation-2/capture-abi/layout.json'):
    files[str(p)]=sha(p)
compiler=json.loads((base_run/'continuation-2/capture-abi/compiler.json').read_text())['command']
deps=run([x if x!='-S' else '-M' for x in compiler],'actual-ABI-dependency-closure').stdout
for name in deps.split(':',1)[1].replace('\\\n',' ').split():
    p=Path(name)
    if p.is_file():files[str(p.resolve())]=sha(p)
for root in runs:
    for p in sorted(root.rglob('*')):
        assert not p.is_symlink(),('fixture alias',p)
        if p.is_file():fixtures[str(p)]=sha(p)
assert str(Path(slot.lease['identities']['hdd_path']['path']).resolve()) not in files
baseline={}
for line in (D/'W48-SOURCE-BASELINE.sha256').read_text().splitlines():
    digest,name=line.split(None,1);p=Path(name.strip()).resolve();baseline[str(p)]=digest
changes={p:dict(before=h,after=sha(p)) for p,h in baseline.items() if sha(p)!=h}
source=(R/'tools/recovery.py').read_text();tree=ast.parse(source)
methods={n.name:hashlib.sha256(ast.get_source_segment(source,n).encode()).hexdigest() for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name in ('fds','guard','sudo_read')}
manifest=dict(schema=2,phase='PREPARE_ONLY',slot='post-entry-49',slot_path=str(D),lease_sha256=slot.digest,session=os.environ.get('HERMES_SESSION_ID'),files=files,fixture_files=fixtures,test_receipts=receipts,test_counts=counts,commands=commands,changes_from_W48=changes,new_sources=[p for p in before_sources if p not in baseline],collector_and_guard_function_hashes=methods,lease_input_bindings=slot.lease['identities'],frozen_input_bindings=slot.lease['frozen_inputs'],phase2_command=['/usr/bin/python3','-B',str(R/'tools/runtime_session.py')],no_phase1_spend=True,real_churn=churn,billing_note='primary included; auxiliary classification unknown')
manifest_path=D/'SOURCE-MANIFEST.json'
if manifest_path.exists():
    old_digest=sha(manifest_path);archive=D/('SOURCE-MANIFEST.'+old_digest+'.json')
    if not archive.exists():archive.write_bytes(manifest_path.read_bytes())
manifest_path.write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n')
required=dict(note='Requirement only, NOT worker-issued approval',binding_fields=dict(state='verified',new_launch_authorized=True),source_confirmation=dict(state='verified',lease_sha256=slot.digest,manifest_sha256=sha(manifest_path),session=manifest['session'],files=files,route_proof='Parent supplies actual current token-bearing session/model/provider/billing proof, not this string'))
(D/'PARENT-CONFIRMATION-REQUIREMENTS.json').write_text(json.dumps(required,indent=2)+'\n')
status=json.loads((D/'status.json').read_text());status.update(phase='READY-FOR-PARENT-SOURCE-CONFIRMATION',source_manifest=str(manifest_path),manifest_sha256=sha(manifest_path),lease_sha256=slot.digest,test_counts=counts,test_exits=[c['exit_code'] for c in commands[:5]],actual_stopped_preflight_exit=0,phase2_command=manifest['phase2_command'],real_claim_created=False,guest_commands=0,parent_confirmation='not written by worker')
(D/'status.json').write_text(json.dumps(status,indent=2)+'\n')
print(json.dumps(dict(phase=status['phase'],manifest_sha256=status['manifest_sha256'],source_files=len(files),fixture_files=len(fixtures),immutable_receipts=len(receipts),test_counts=counts,actual_stopped_preflight_exit=0,real_claim_created=False,churn=churn,changes_from_W48=changes),indent=2))
