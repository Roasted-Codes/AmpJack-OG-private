"""Pre-issue evidence validation only. Does not launch or claim."""
from pathlib import Path
import hashlib,json,os,sys,traceback,tempfile
sys.dont_write_bytecode=True
O=Path(__file__).resolve().parents[1];W=O.parent;R=W/'45-x11-runtime-capture';S=R/'post-entry-59';OUT=O/'live-run'
RUN=Path(tempfile.mkdtemp(prefix='preissue-',dir=OUT))
for name in ('TMPDIR','TMP','TEMP','XDG_CACHE_HOME','PYTHONPYCACHEPREFIX'):(RUN/name).mkdir()
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def need(ok,msg):
    if not ok:raise ValueError(msg)
def save(name,obj):
    with (RUN/name).open('x') as f:json.dump(obj,f,indent=2);f.write('\n')
try:
    tracking=json.loads((S/'PARENT-LIVE-TRACKING.json').read_text())
    baseline=tracking['baseline_api_calls']
    c=json.loads((W/'sol-audit/COORDINATOR_STATE.json').read_text());b=c['runtime_binding']
    need(os.environ.get('HERMES_SESSION_ID')=='local-635e2c531363e9492f00a53001b2887e2550e0fc659b9d6fa50eb1770cfb2a43'==b.get('session')==tracking.get('session'),'genuine session mismatch')
    need(b.get('process')==tracking.get('process')==c.get('worker_process') and b.get('process') and type(b.get('pid')) is int and b['pid']>0 and b['pid']==tracking.get('pid'),'parent tracked actual wrapper mismatch')
    need((b.get('state'),b.get('slot'),b.get('model'),b.get('provider'),b.get('billing_mode'),b.get('reasoning'))==('verified','post-entry-59','gpt-6.1-sol','openai-codex','subscription_included','medium'),'live slot/state/route mismatch')
    need(b.get('new_launch_authorized') is True and b.get('remaining_commands')==1 and b.get('cumulative_ceiling')==5 and b.get('historical_launch_commands')==4 and b.get('historical_authenticated_loaded_TU_boots')==2,'live grant/budget missing')
    need(b.get('baseline_api_calls')==baseline and b.get('route_api_calls',0)>baseline,'new positive route usage missing')
    need(any(p.get('model')=='gpt-6.1-sol' and p.get('billing_provider')=='openai-codex' and p.get('billing_mode')=='subscription_included' and p.get('api_call_count',0)>baseline and p.get('input_tokens',0)>0 for p in b.get('route_proof_new',[])),'new token-bearing route proof missing')
    need(b.get('takeover',{}).get('accepted') is False,'default finite authenticated quit not preselected')
    need(sha(S/'PARENT-RUNTIME-LEASE.json')==b.get('lease_sha256')=='1e01a781bb4ad097320cd30797484282e705ad5a72a58ceada03b5c4bab57165','immutable lease mismatch')
    need(sha(S/'SOURCE-MANIFEST.json')=='899ca7a57d4824cca4cf175cd5f49c628d47eed9391fca38e4e4e10ba84806d3','final manifest mismatch')
    parent=json.loads((O/'PARENT-FINAL-MANIFEST-VERIFIED.json').read_text());need(parent['all_passed'] and parent['exit_code']==0,'parent final validation absent')
    sys.path.insert(0,str(R));import parent_launch as w
    slot=w.resolve_active_slot()
    need(slot.path==S and slot.binding==b,'production exact authority mismatch')
    manifest=json.loads((S/'SOURCE-MANIFEST.json').read_text())
    need(len(manifest['files'])==79 and len(manifest['fixture_files'])==7976,'final source/fixture count mismatch')
    need(not (S/'runtime-claim.json').exists() and not (S/'live').exists() and not (S/'navigation-reviewed.json').exists(),'not fresh for one cold diagnostic')
    save('PREISSUE-VERIFIED.json',dict(state='verified_for_one_tested_normal_entry',actual_session=os.environ['HERMES_SESSION_ID'],tracking=tracking,binding=b,parent_validator=parent,files=manifest['files'],source_files=79,fixture_files=7976,lease_sha256=sha(S/'PARENT-RUNTIME-LEASE.json'),manifest_sha256=sha(S/'SOURCE-MANIFEST.json'),status_preimage_sha256=sha(S/'status.json'),native_commands_issued_by_validator=0,cleanup='authenticated QMP quit and verified release; no takeover'))
    final=dict(state='preissue_verified',runner_started=False,run_root=str(RUN),prior_native_commands=4,prior_authenticated_TU_entries=2,native_commands_observed=0)
    print(json.dumps(final,indent=2))
except BaseException as error:
    final=dict(state='UNSPENT_GATE_REFUSAL',runner_started=False,native_commands_observed=0,error=str(error),traceback=traceback.format_exc(),run_root=str(RUN))
    save('PREISSUE-REFUSAL.json',final);print(json.dumps(final,indent=2))
(OUT/'status.json').write_text(json.dumps(final,indent=2)+'\n')
sys.exit(0 if final['state']=='preissue_verified' else 2)
