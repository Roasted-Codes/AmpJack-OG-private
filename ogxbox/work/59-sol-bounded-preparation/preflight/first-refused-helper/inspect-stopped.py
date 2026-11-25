"""Read-only official CLI orchestration and evidence; no launch path."""
from pathlib import Path
import hashlib,json,os,subprocess,sys,tempfile,traceback
sys.dont_write_bytecode=True
P=Path(__file__).resolve().parent
O=P.parent;W=O.parent;R=W/'45-x11-runtime-capture';S=R/'post-entry-59'
RUN=Path(tempfile.mkdtemp(prefix='stopped-',dir=P))
EXPECTED_SESSION='local-635e2c531363e9492f00a53001b2887e2550e0fc659b9d6fa50eb1770cfb2a43'
EXPECTED_LEASE='1e01a781bb4ad097320cd30797484282e705ad5a72a58ceada03b5c4bab57165'
CANON=W/'sol-audit/COORDINATOR_STATE.json'
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def save(name,obj):
    with (RUN/name).open('x') as f:json.dump(obj,f,indent=2);f.write('\n')
def need(value,message):
    if not value:raise ValueError(message)
env=dict(os.environ)
for key in ('TMPDIR','TEMP','TMP','XDG_CACHE_HOME','PYTHONPYCACHEPREFIX'):
    d=RUN/key;d.mkdir();env[key]=str(d)
env['PYTHONDONTWRITEBYTECODE']='1'
# Genuine inherited session is not set, replaced or synthesized.
commands=[];first_missing=None;phase='authentication';before_sources={};binding=None
status_before=sha(S/'status.json')
protected=json.loads((O/'PROTECTED-INPUTS-AFTER.json').read_text())
protected_before={p:sha(p) for p in protected}
closure=json.loads((S/'preparation/TESTED-SOURCES.json').read_text())
accept=json.loads((O/'PARENT-INDEPENDENT-ACCEPTANCE.json').read_text())
tracking=json.loads((O/'PARENT-PREFLIGHT-TRACKING.json').read_text())

def verify_binding():
    c=json.loads(CANON.read_text());b=c.get('runtime_binding',{})
    actual=os.environ.get('HERMES_SESSION_ID')
    need(actual==EXPECTED_SESSION and b.get('session')==actual,'genuine session mismatch')
    need(b.get('state')=='verified_prepare_only' and b.get('slot')=='post-entry-59','not staged slot59 prepare-only')
    need(b.get('new_launch_authorized') is False and not b.get('source_confirmation'),'live authorization/source confirmation must remain absent')
    need(b.get('read_only_preflight') is True and b.get('native_live') is False,'read-only stopped binding absent')
    need((b.get('model'),b.get('provider'),b.get('billing_mode'),b.get('reasoning'))==('gpt-6.1-sol','openai-codex','subscription_included','medium') and b.get('route_verified') is True,'route mismatch')
    need(b.get('baseline_api_calls')==34 and b.get('route_api_calls',0)>34,'no positive new usage delta')
    proof=b.get('route_proof_new',[])
    need(any(x.get('model')=='gpt-6.1-sol' and x.get('billing_provider')=='openai-codex' and x.get('billing_mode')=='subscription_included' and x.get('api_call_count',0)>34 and x.get('input_tokens',0)>0 for x in proof),'new token-bearing route proof missing')
    need(b.get('process')==tracking.get('process')==c.get('worker_process') and b.get('pid')==tracking.get('pid'),'new wrapper identity not independently bound')
    need(b.get('lease_sha256')==EXPECTED_LEASE and sha(S/'PARENT-RUNTIME-LEASE.json')==EXPECTED_LEASE,'staged immutable lease digest mismatch')
    need(b.get('lease_path')==str(S/'PARENT-RUNTIME-LEASE.json'),'staged lease path mismatch')
    # Verify actual wrapper PID is in this running command's own ancestry.
    ancestors=[];pid=os.getpid()
    while pid>1:
        raw=Path(f'/proc/{pid}/stat').read_text();fields=raw.rsplit(')',1)[1].split()
        ancestors.append(dict(pid=pid,ppid=int(fields[1]),start_ticks=int(fields[19])))
        pid=int(fields[1])
    need(any(x['pid']==b['pid'] for x in ancestors),'bound new wrapper PID is not actual command ancestry')
    need(not (S/'runtime-claim.json').exists() and not (S/'runtime-claim.json').is_symlink() and not (S/'live').exists(),'claim/live already exists')
    if binding is not None:need(b==binding,'canonical binding changed during stopped continuation')
    return b,ancestors

try:
    binding,ancestors=verify_binding()
    save('authentication.json',dict(actual_session=os.environ.get('HERMES_SESSION_ID'),canonical_sha256=sha(CANON),binding=binding,actual_ancestry=ancestors,tracking=tracking,parent_acceptance=accept))
    phase='source_closure_before'
    need(accept.get('state')=='parent_accepted_offline_slot59_preparation','parent offline acceptance absent')
    need(len(closure['files'])==accept['source_closure_files']==79,'source closure count mismatch')
    for p,h in closure['files'].items():
        before_sources[p]=sha(p);need(before_sources[p]==h,'source closure drift: '+p)
    need(before_sources[str(R/'parent_launch.py')]==accept['source_sha'],'accepted launcher mismatch')
    save('source-closure-before.json',dict(files=before_sources,closure_sha256=sha(S/'preparation/TESTED-SOURCES.json'),all_match=True))
    # The following whitelist contains only official no-native CLI branches.
    argv_list=[['/usr/bin/python3','-B',str(R/'parent_launch.py'),'--check'],['/usr/bin/python3','-B',str(R/'parent_launch.py'),'--command'],['/usr/bin/python3','-B',str(R/'tools/live_preflight.py'),'--active-slot']]
    for index,argv in enumerate(argv_list,1):
        phase='official_'+argv[-1];verify_binding()
        result=subprocess.run(argv,cwd=R,env=env,capture_output=True,text=True)
        (RUN/f'{index}-stdout.txt').write_text(result.stdout);(RUN/f'{index}-stderr.txt').write_text(result.stderr)
        record=dict(argv=argv,cwd=str(R),environment={k:env.get(k) for k in ('HERMES_SESSION_ID','PYTHONDONTWRITEBYTECODE','PYTHONPYCACHEPREFIX','TMPDIR','TEMP','TMP','XDG_CACHE_HOME')},exit_code=result.returncode,stdout=str(RUN/f'{index}-stdout.txt'),stderr=str(RUN/f'{index}-stderr.txt'))
        commands.append(record);save(f'{index}-command.json',record)
        need(result.returncode==0,'official path failed '+argv[-1]+': '+result.stderr.strip())
        if argv[-1]=='--command':
            generated=json.loads(result.stdout)
            need(generated[0]=='systemd-run' and '--unit=ampjack-parent59-devkit.service' in generated,'generated command mismatch')
            save('generated-command-DATA-ONLY.json',dict(argv=generated,executed=False))
    phase='official_result_inspection'
    result=json.loads((S/'preflight.json').read_text())
    need(result['qcow_check']['check-errors']==0 and not result['qcow_info'].get('backing-filename'),'qcow check/backing mismatch')
    need(len(result['usb'])==1 and result['usb'][0]['readable'] and result['usb'][0]['writable'],'USB uniqueness/access gate failed')
    need('not found' not in result['dependencies'],'missing native dependencies')
    need('No emulator started' in result['guard'],'guard check not positively recorded')
    resource=result['resources']
    need(not any(resource[k] for k in ('processes','disk_fds','tcp','qmp_listeners','qmp_path_exists')) and 'LoadState=not-found' in resource['unit'],'stopped resource proof failed')
    expected=json.loads((R/'PARENT-TITLE-IDENTITIES.json').read_text())['per_path']
    need(result['hashes']==expected,'per-path title identities differ')
    need(len({v['sha256'] for v in result['hashes'].values()})>=2,'distinct base/TU hashes absent')
    save('official-output-inspection.json',dict(qcow_errors=0,no_backing=True,exact_per_path_titles=result['hashes'],current_artifact_identities=result['identities'],usb_accessibility_only=result['usb'],guard=result['guard'],resources=resource,kernel_dispatch=result['kernel_dispatch'],official_output_sha256=sha(S/'preflight.json'),attachment='NOT TESTED',native_commands=0))
except BaseException as error:
    first_missing=dict(phase=phase,error=str(error),traceback=traceback.format_exc())
    save('gate-refusal.json',first_missing)
finally:
    after_sources={p:sha(p) for p in closure['files']}
    protected_after={p:sha(p) for p in protected}
    unchanged=after_sources==closure['files'] and protected_after==protected_before
    zero_effects=not (S/'runtime-claim.json').exists() and not (S/'live').exists() and sha(S/'status.json')==status_before
    save('post-check-invariants.json',dict(source_files=after_sources,source_closure_match=after_sources==closure['files'],protected_before=protected_before,protected_after=protected_after,protected_unchanged=protected_after==protected_before,slot_status_before=status_before,slot_status_after=sha(S/'status.json'),no_claim=not (S/'runtime-claim.json').exists(),no_live_directory=not (S/'live').exists(),native_commands=0))
    if not unchanged or not zero_effects:
        first_missing=first_missing or dict(phase='post_check_invariants',error='source/protected/status/claim/live invariant failed')
    state='PARTIAL_GATE_REFUSED' if first_missing else 'READY_FOR_PARENT_CONFIRMATION_ONLY'
    final=dict(state=state,run_root=str(RUN),commands=commands,first_missing_gate=first_missing,source_files_verified=len(before_sources),source_and_protected_unchanged=unchanged,zero_claim_live_status_effects=zero_effects,native_commands=0,total_native_commands_spent=4,authenticated_TU_entries=2,live_authorized=False)
    save('result.json',final)
    (P/'status.json').write_text(json.dumps(final,indent=2)+'\n')
    report=state+'\n\nRead-only continuation. No native issue, claim, unit creation, QMP/RSP connection or USB device requests. The generated systemd-run argv, if present, is DATA ONLY.\n\nRun root: '+str(RUN)+'\n\n'
    for c in commands:report+='argv='+json.dumps(c['argv'])+'\ncwd='+c['cwd']+'\nexit='+str(c['exit_code'])+'\nstdout='+c['stdout']+'\nstderr='+c['stderr']+'\n\n'
    report+='First missing gate: '+(json.dumps(first_missing,indent=2) if first_missing else 'none in authorized stopped checks; final parent source manifest/confirmation and DISTINCT explicit live continuation remain required')+'\n'
    report+='\nSource/protected unchanged: '+str(unchanged)+'; status/claim/live invariants: '+str(zero_effects)+'. USB accessibility is not attachment or input evidence. Navigation remains future fresh screenshot/PID/start review; default future cleanup authenticated QMP quit and verified release. No runtime/card closure claimed.\n'
    (P/'REPORT.md').write_text(report)
    (P/'shortsummary.txt').write_text(state+'; commands/exits='+json.dumps([(c['argv'][-1],c['exit_code']) for c in commands])+'; first_missing_gate='+(first_missing['phase']+': '+first_missing['error'] if first_missing else 'parent final confirmation and distinct live authorization')+'; native_commands=0; run='+str(RUN)+'\n')
    print(json.dumps(final,indent=2))
sys.exit(2 if first_missing else 0)
