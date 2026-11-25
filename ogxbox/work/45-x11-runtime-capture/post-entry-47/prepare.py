#!/usr/bin/env python3
"""PREPARE_ONLY artifact checkpoint. Runs tests/stopped reads, never launches."""
import sys
sys.dont_write_bytecode=True
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
R=Path(__file__).resolve().parents[1]
D=R/'post-entry-47'
sys.path.insert(0,str(R));sys.path.insert(0,str(R/'tools'))
import parent_launch as w
import enum_watch as e
lease=w.receipt47()
assert not Path(lease['claim_path']).exists(),'real fresh claim already exists'
commands=[]
run_id=str(time.time_ns())
def sha(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
def run(cmd,*,env=None,label):
    p=subprocess.run(cmd,capture_output=True,text=True,env=env)
    out=D/(label+'-'+run_id+'.log');out.write_text(p.stdout+p.stderr)
    commands.append(dict(command=cmd,returncode=p.returncode,evidence=str(out)))
    (D/'prepare-commands.json').write_text(json.dumps(commands,indent=2)+'\n')
    assert p.returncode==0,(cmd,p.returncode,str(out))
    return p
normal=dict(os.environ);normal.pop('HERMES_SESSION_ID',None)
for name in ('test_continuation.py','test_recovery.py','test_post_entry47.py'):
    run(['/usr/bin/python3','-B',str(R/'tools'/name)],env=normal,label=name.removesuffix('.py'))
receipts=[]
for pointer,result_name,expected in (('result.json','result.json',31),('recovery-result.json','recovery-result.json',15),('fresh-result.json','fresh-result.json',None)):
    result=json.loads((D/'tests'/pointer).read_text())
    assert result['all_passed'] and result['exit_code']==0
    if expected is not None:assert result['tests_run']==expected
    for name,digest in result['production_hashes'].items():assert sha(R/name)==digest,('tested source changed',name)
    immutable=Path(result['evidence'])/result_name
    assert json.loads(immutable.read_text())['all_passed']
    receipts.append((immutable,result))
run(['/usr/bin/python3','-B',str(R/'tools/live_preflight.py'),'--post-entry-47'],label='actual-stopped-preflight')
assert not Path(lease['claim_path']).exists(),'PREPARE_ONLY may not claim'
pre=json.loads((D/'preflight.json').read_text())
assert pre['qcow_check']['check-errors']==0 and not pre['qcow_info'].get('backing-filename')
# Retained tool directory is hashed as a conservative superset; no new tree.
files={str(p.resolve()):sha(p) for p in sorted((R/'tools').glob('*.py'))}
for p in (R/'parent_launch.py',Path(__file__),
    R.parent/'27-title-runtime/ogx_title_loader.py',
    Path('/home/roasted/Desktop/Xbox/LAN_Stats/tools/xemu/gdbrsp.py'),
    Path('/home/roasted/Desktop/Xbox/LAN_Stats/tools/xemu/qmp.py'),
    Path('/home/roasted/.hermes/skills/xemu-development-workflow/scripts/roqfatx.py'),
    Path('/home/roasted/.local/share/xemu-safety/guard.py'),
    R/'continuation-2/capture-abi/layout.json',R/'PARENT-TITLE-IDENTITIES.json',R/'PARENT-RESULT-INTAKE.json',
    e.ELF,e.LAYOUT,e.XBE,e.DUMP,
    Path(lease['identities']['launcher']['path'])):
    files[str(p.resolve())]=sha(p)
# All actual OS tools used by tests/preflight and the retained phase2 path.
for name in ('/usr/bin/python3','clang','objdump','llvm-objdump','llvm-nm','qemu-img','ldd','systemctl','systemd-run','journalctl','ss','sudo','readlink','sha256sum','cat','import','/home/roasted/.local/bin/xdotool','/usr/local/bin/xemu-network'):
    found=shutil.which(name) if not name.startswith('/') else name
    assert found and Path(found).is_file(),('missing executed dependency',name)
    p=Path(found).resolve();files[str(p)]=sha(p)
# Compiler-derived ABI dependency closure (no product rebuild or execution).
compiler=next(iter(receipts))[0].parent/'continuation-2/capture-abi/compiler.json'
c=json.loads(compiler.read_text())['command'];dep_cmd=[x if x!='-S' else '-M' for x in c]
deps=run(dep_cmd,label='capture-ABI-header-dependencies').stdout
for value in deps.split(':',1)[1].replace('\\\n',' ').split():
    p=Path(value)
    if p.is_file():files[str(p.resolve())]=sha(p)
fixture_files={}
for receipt,_ in receipts:
    for p in sorted(receipt.parent.rglob('*')):
        if p.is_file() and p.suffix in ('.py','.c','.json','.jsonl'):
            fixture_files[str(p.resolve())]=sha(p)
# No HDD appears in repeatedly checked source files: phase2 metadata must never
# re-read it offline. Current disk/config/eeprom/etc remain sealed lease pins.
assert str(Path(lease['identities']['hdd_path']['path']).resolve()) not in files
recovery_baseline=json.loads((R/'continuation-2/recovery/final-verification.json').read_text())['final_production_hashes']
protected=json.loads((R.parent/'47-astra-post-entry-admission/PARENT-PROTECTED-INPUTS.json').read_text())
protected_differences={name:dict(baseline=digest,current=sha(R.parent/name)) for name,digest in protected.items() if sha(R.parent/name)!=digest}
differences={name:dict(baseline=digest,current=sha(R/name)) for name,digest in recovery_baseline.items() if sha(R/name)!=digest}
unchanged={name:digest for name,digest in recovery_baseline.items() if sha(R/name)==digest}
for name in ('previous_claim','previous_lease'):
    assert sha(lease[name]['path'])==lease[name]['sha256']
manifest=dict(schema=1,phase='PREPARE_ONLY',lease_sha256=w.DIGEST47,
    session=os.environ.get('HERMES_SESSION_ID'),files=files,fixture_files=fixture_files,
    test_receipts={str(p.resolve()):sha(p) for p,_ in receipts},
    test_counts={p.name:result['tests_run'] for p,result in receipts},
    lease_input_bindings=lease['identities'],frozen_input_bindings=lease['frozen_inputs'],
    protected_manifest_sha256=sha(R.parent/'47-astra-post-entry-admission/PARENT-PROTECTED-INPUTS.json'),
    differences_from_recovery=differences,unchanged_recovery_sources=unchanged,
    differences_from_parent_protected=protected_differences,
    new_owned_sources=[name for name in files if name.startswith(str(R)) and name.endswith('.py') and str(Path(name).relative_to(R.parent)) not in protected],
    phase2_command=['/usr/bin/python3','-B',str(R/'tools/runtime_session.py')],
    no_phase1_spend=True,commands=commands)
manifest_path=D/'SOURCE-MANIFEST.json'
if manifest_path.exists():
    archive=D/('SOURCE-MANIFEST.'+sha(manifest_path)+'.json')
    if not archive.exists():archive.write_bytes(manifest_path.read_bytes())
manifest_path.write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n')
# Only a requirement specification is emitted. This is NOT canonical approval.
required=dict(binding_fields=dict(state='verified',new_launch_authorized=True),source_confirmation=dict(
    state='verified',lease_sha256=w.DIGEST47,manifest_sha256=sha(manifest_path),session=manifest['session'],files=files,
    route_proof='PARENT must supply current token-bearing session/provider/model/billing_mode/api_call_count/input_tokens evidence'))
(D/'PARENT-CONFIRMATION-REQUIREMENTS.json').write_text(json.dumps(required,indent=2)+'\n')
status=json.loads((D/'status.json').read_text())
status.update(phase='READY-FOR-PARENT-SOURCE-CONFIRMATION',source_manifest=str(manifest_path),source_manifest_sha256=sha(manifest_path),
    test_counts=manifest['test_counts'],test_exits=[0,0,0],actual_stopped_preflight_exit=0,
    real_claim_created=False,new_commands_used=0,phase2_command=manifest['phase2_command'],
    parent_source_confirmation='not written by worker; canonical exact confirmation and phase2 authorization required')
(D/'status.json').write_text(json.dumps(status,indent=2)+'\n')
print(json.dumps(dict(phase=status['phase'],manifest_sha256=sha(manifest_path),test_counts=manifest['test_counts'],
    executed_source_count=len(files),fixture_count=len(fixture_files),changed_paths=list(differences),
    phase2_command=manifest['phase2_command'],real_claim_created=False),indent=2))
