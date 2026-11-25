"""Finalize actual one-command diagnostic; retained files only, no runtime effects."""
from pathlib import Path
import hashlib,json
W=Path('/home/roasted/Desktop/Xbox/AmpJack-OG/ogxbox/work');R=W/'45-x11-runtime-capture';S=R/'post-entry-59';O=W/'59-sol-bounded-preparation';OUT=O/'live-run';RUN=OUT/'preissue-97zbuuox';L=S/'live'
def load(p):return json.loads(Path(p).read_text())
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
claim=load(S/'runtime-claim.json');handle=load(L/'launch-handle.json');result=load(L/'session-result.json');discovery=load(L/'first-native-discovery.json');entry=load(L/'entry-verified.json');hits=load(L/'entry-hits.json');install=load(L/'install-verified.json');hooks=load(RUN/'SEVEN-HOOK-READBACKS.json');usb=load(RUN/'USB-QUALIFICATION-SUMMARY.json');release=load(RUN/'INDEPENDENT-RELEASE.json');post=load(RUN/'POST-RUN-SOURCE-PROTECTED.json');pre=load(RUN/'PREISSUE-VERIFIED.json');lease=load(S/'PARENT-RUNTIME-LEASE.json');context=load(L/'final-context.json')
rows=[json.loads(s) for s in (L/'ordered-trace.jsonl').read_text().splitlines()]
holds=[r for r in rows if r.get('pre_fault_hold') or r.get('unclassified')]
assert len(holds)==1
held=holds[0];previous=rows[rows.index(held)-1]
assert held['seq']==228 and held['pre_fault_hold'] and held['regs']['eip']==context['regs']['eip']
assert held['current']==0 and held['regs']['esi']==0
assert handle['claim_sha256']==sha(S/'runtime-claim.json') and claim['receipt_sha256']==handle['receipt_sha256']==pre['lease_sha256']
assert result['command'] and handle['returncode']==0 and discovery['pin']['invocation']==handle['invocation_id']
assert len(hooks)==7 and all(h['bytes_match'] and h['target_match'] for h in hooks)
assert result['remaining_resources']['released'] and result['clients_closed'] and release['no_process_disk_listener_or_socket']
assert not any(k in result for k in ('quit_error','release_error','rsp_close_error','qmp_close_error'))
assert usb['qualification']['qualified'] and usb['request']['result']=={} and usb['same_physical_directory_instance']
assert not post['mismatches'] and not post['protected_mismatches']
commands_used=int(bool(result['command']) and handle['returncode']==0)
tu_entries=sum(h.get('decision',{}).get('kind')=='tu803' for h in hits)
code=bytes.fromhex(context['code']);pc=context['regs']['eip'];instruction=code[16:19].hex()
assert instruction=='8b7e0c'
evidence={str(p):sha(p) for p in sorted(L.iterdir()) if p.is_file()}
evidence.update({str(S/'runtime-claim.json'):sha(S/'runtime-claim.json'),str(S/'navigation-reviewed.json'):sha(S/'navigation-reviewed.json'),str(S/'PARENT-RUNTIME-LEASE.json'):sha(S/'PARENT-RUNTIME-LEASE.json'),str(S/'SOURCE-MANIFEST.json'):sha(S/'SOURCE-MANIFEST.json')})
summary=dict(state='DIAGNOSTIC_PARTIAL_PREFAULT_HOLD_RELEASED',runner=dict(argv=['/usr/bin/python3','-B',str(R/'parent_launch.py')],cwd=str(R),tracking_process='proc_b16c78b2ac78',runner_exit_code=1,systemd_run_returncode=handle['returncode'],stdout=str(RUN/'runner-stdout.txt'),stderr=str(RUN/'runner-stderr.txt')),worker_exit='parent intake; not inferred from runner exit',native_commands_this_continuation=commands_used,claim_spent=True,claim_sha256=sha(S/'runtime-claim.json'),cumulative_actual_native_commands=lease['historical_launch_commands']+commands_used,authenticated_TU_entries_this_continuation=tu_entries,cumulative_authenticated_TU_entries=lease['historical_authenticated_loaded_TU_boots']+tu_entries,remaining_commands=0,retry_authorized=False,invocation=handle['invocation_id'],native=discovery['identity'],launcher=discovery['launcher'],title_entry=dict(retail_then_tu=[h['decision']['kind'] for h in hits],eip=hex(entry['eip']),generic_hold_retired=entry['generic_hold_retired']),module=dict(base=hex(install['base']),module=hex(install['module']),installed_hooks=hex(install['result']['status']['installed_hooks']),install_failed=install['result']['status']['install_failed'],readbacks=hooks),usb=dict(qualified=True,request=usb['request'],target=usb['qualification']['structural']['target_node'],same_physical_directory_instance=True,host_reported_speed=usb['qualification']['host_reported_speed'],emulated_speed=usb['qualification']['emulated_speed'],open_at_add=usb['qualification']['open_at_add'],sampled_open_handle=False,future_health='unknown',game_input='untested'),trace=dict(rows=len(rows),sequence_contiguous=[r['seq'] for r in rows]==list(range(1,len(rows)+1)),local_qualified_rows=[r['seq'] for r in rows if r.get('local_observer_qualified')],last_nonheld_row=dict(seq=previous['seq'],eip=hex(previous['eip']),events=previous.get('events')),first_missing=dict(phase=result['first_failed_link'],seq=held['seq'],eip=hex(held['eip']),stop_reason=held['stop_reason'],event=held['events'],pre_fault_hold=True,current=held['current'],esi=held['regs']['esi'],stage=held['stage'],marker=held['marker'],pending=held['pending'],paired_instruction=instruction,decoded_instruction='mov edi,[esi+0xc]',inference='with ESI zero this read would address 0xc; instruction was held before executing, not an observed crash',semantic_cause='UNKNOWN'),cleanup_row=rows[-1]),responsive_capture_reached=False,physical_buttons='UNTESTED',gameplay='UNPROVEN',cleanup=dict(authenticated_qmp_quit='completed via retained run_session path; no quit_error; clients closed and release verified',runner_release=result['remaining_resources'],independent_release=release),tested_source_files=post['files_checked'],source_mismatches=post['mismatches'],protected_mismatches=post['protected_mismatches'],evidence=evidence,unknowns=['Why current became zero before this later timer callback','GIP ready, actual physical report, served state and responsive title action','Physical button/gameplay acceptance','Future device connectivity or health'])
with (RUN/'PHASE2-RESULT.json').open('x') as f:json.dump(summary,f,indent=2);f.write('\n')
for name in ('REPORT.md','PHASE2-RESULT.md'):
    p=OUT/name
    if p.exists():
        with (RUN/('PRIOR-'+name)).open('x') as f:f.write(p.read_text())
hooktext='\n'.join('  '+h['name']+': '+h['site']+' -> '+h['target']+'; readback '+h['readback']+' (matches)' for h in hooks)
text=f'''DIAGNOSTIC_PARTIAL_PREFAULT_HOLD_RELEASED — one cold command used, no retry

Publication barrier returned0 for the genuine session and parent wrapper proc_8322a47a92af/PID2752582. Exact existing preissue validator then returned0, independently validating parent tracking/live source confirmation, lease, final manifest, required79 sources and7976 fixtures. Previous path/binding refusals remain preserved; their prior root reports are archived here as PRIOR-REPORT.md/PRIOR-PHASE2-RESULT.md.

One exact runner command: /usr/bin/python3 -B {R/'parent_launch.py'}
Cwd: {R}
Tracked runner: proc_b16c78b2ac78, completed naturally, exit1. Actual systemd-run returned0. Worker exit is separate parent intake, not inferred. Runner stdout/stderr are under {RUN}. No new wrapper/client manager, second QMP/RSP pair, reset, restart, reconnect, blind recovery, experimental writes or source edit was used.

Durable claim: {S/'runtime-claim.json'}
Claim SHA256: {sha(S/'runtime-claim.json')}
Unit: {handle['unit']}, Restart=no
Invocation: {handle['invocation_id']}
Native PID/start: {discovery['identity']['pid']}/{discovery['identity']['start_ticks']}; launcher PID/start {discovery['launcher']}
Host boot: {discovery['identity']['boot_id']}
One new claimed/issued cold command; cumulative actual nativecommands={summary['cumulative_actual_native_commands']}; one new authenticated TU803 entry, cumulative={summary['cumulative_authenticated_TU_entries']}; remaining0. This receipt/claim is permanently spent. No retry authorized.

Navigation: actual new dashboard image was viewed. Audio Console App was highlighted; next top-level row was normal Halo2 parent above indented children. Image hash, current PID/start/hostboot/window and invocation/claim were authenticated before exclusive NEW navigation-reviewed.json was written. The existing runner performed its approved oneDown+A route. Raw load hits show retail_base then tu803, generic hold retired, entry {hex(entry['eip'])}; module addresses were used only after authenticated TU entry. This is entry identity, not responsive-title acceptance.

Module base {hex(install['base'])}, module {hex(install['module'])}. Frozen ELF/loader pins unchanged. Seven individual destination/readback comparisons matched, installed_hooks={hex(install['result']['status']['installed_hooks'])}, install_failed=0. Immediate pre-USB install status attached=0 is retained, not misrepresented as GIP-ready state.
{hooktext}

USB qualification actually PASSED. Same sole manager client issued exactly {json.dumps(usb['request']['arguments'],sort_keys=True)}, returned actual {{}}. Held physical directory identity device27/inode72279 and hostbus3/hostaddr7/speed12 remained identical across four physical samples. Unique joined pt_pad3 on OHCI00:02.0 / usb-bus.1 / port1.4 was attached at the sample, target speed12 matching host12. Native invocation and decoded entry were checked before/after. Exact raw receipt and deterministic revalidation retained. Source-implied synchronous open-at-add is not a sampled open handle; topology alone proves neither Xbox logical-port routing, GIP readiness, input, nor future health.

Ordered observation retained {len(rows)} contiguous raw rows, real hardware watches and paired stopped code. Seq2 was the accepted event-local known store at0x4131e1, postPC0x4131e7; it qualified only that event and did not excuse later failure. Progress includes real enqueue/current writes/timer activity and completion/removal boundaries, without assigning semantic success.

First missing link: ordered_observation; exact first safety hold seq{held['seq']} at {hex(pc)}, event pre_invalid_access, pre_fault_hold=true, current=0, ESI=0, marker={held['marker']}, stage={held['stage']}, pending={held['pending']}. Paired actual bytes at PC: {instruction}, mov edi,[esi+0xc]. INFERENCE from those bytes/registers: next read would address0xc. No faulting instruction was resumed and no actual crash is claimed. Last prior nonheld row seq{previous['seq']} at{hex(previous['eip'])}, stage0. Final row{rows[-1]['seq']} cleanup: hold=true, restore_running=false, cleanup_errors=[]. Raw regs/stack/code are in final-context.json. Cause/attribution remains UNKNOWN; no initialization/corruption/input diagnosis or patch is inferred.

Responsive title capture was NOT reached; no moving menu/lossless responsive capture, GIP-ready report, physical button press, served-state response or gameplay proof. Physical input remains UNTESTED. This is diagnosticpartial, not a fixed controller/product/dashboard package or healthy handoff.

Cleanup: retained run_session reauthenticated then issued QMPquit on its existing client; no quit_error/client-close error. Runner result says clients_closed=true, released=true, owned_alive_pids=[], unit inactive/dead MainPID0, no QMP/RSP listeners, owned disk/USB FDs released by verified process exit. Independent existing resources() read AFTER runner exit confirmed no native/launcher candidates, disk FDs, TCP/QMP listeners/socket, and transient unit LoadState=not-found. No remaining runner/client/native ownership is left by this continuation; no separate recovery action was taken.

All79 tested source hashes and protected47/49 receipts/manifests/raw captures still match. Lease/manifest pins unchanged. Normal authorized guest disk writes were not called source drift; no disk rewrite/restore or offline qcow operation occurred. S/status.json retains old staging keys plus factual phase2_finished/new_commands_used1/result; actual spending above derives immutable claim/handle and TU hits, not obsolete staging counters. No canonical/lease/manifest/confirmation/card changes by worker.

Evidence: {RUN/'PHASE2-RESULT.json'} with hashed raw artifacts, SEVEN-HOOK-READBACKS.json, USB-QUALIFICATION-SUMMARY.json, ORDERED-TRACE-SUMMARY.json, INDEPENDENT-RELEASE.json, POST-RUN-SOURCE-PROTECTED.json, fresh NAVIGATION-REVIEW.json; official raw evidence at {L}. Parent owns independent intake, budget/card/source-confirmation closure and any next diagnostic decision. No further native allowance implied.
'''
(OUT/'REPORT.md').write_text(text);(OUT/'PHASE2-RESULT.md').write_text(text)
(OUT/'status.json').write_text(json.dumps(summary,indent=2)+'\n')
with (RUN/'runner-exit-receipt.json').open('x') as f:json.dump(dict(tracked_process='proc_b16c78b2ac78',runner_exit_code=1,completion_reason='exited',observed_via='process_manage wait',systemd_run_returncode=handle['returncode'],worker_exit='separate parent intake'),f,indent=2);f.write('\n')
print(json.dumps(dict(state=summary['state'],runner_exit=1,actual_commands_this_run=commands_used,cumulative_commands=summary['cumulative_actual_native_commands'],cumulative_TU_entries=summary['cumulative_authenticated_TU_entries'],hooks=len(hooks),usb_qualified=True,trace_rows=len(rows),hold=summary['trace']['first_missing'],released=release['no_process_disk_listener_or_socket'],source_mismatches=post['mismatches'],protected_mismatches=post['protected_mismatches'],report=str(OUT/'REPORT.md')),indent=2))
