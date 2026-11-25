#!/usr/bin/env python3
"""Final recovery evidence, without privileged reads or guest/disk access."""
import sys
sys.dont_write_bytecode=True
from pathlib import Path
import hashlib
import json
import subprocess
import time
R=Path(__file__).resolve().parents[2]
D=R/'continuation-2/recovery'
sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
base=json.loads((D/'tests/result.json').read_text());recovery=json.loads((D/'tests/recovery-result.json').read_text())
assert base['all_passed'] and base['tests_run']==31
assert recovery['all_passed'] and recovery['tests_run']==15
for receipt in (base,recovery):
    for name,digest in receipt['production_hashes'].items():assert sha(R/name)==digest,(name,'source changed since offline tests')
assert sha(R/'runtime-claim.json')=='f54e2b26b1284e0316939b6b752f6d48926e8b169cf8e45e75a3bf17660684db'
assert sha(R/'PARENT-RUNTIME-LEASE.json')=='a23591fa85600dad6868f8fb4c0d8a4c56c2a0dc09d40f9f6abd205d1d94d6d9'
result=json.loads((D/'live/session-result.json').read_text())
entry=json.loads((D/'live/entry-verified.json').read_text())
context=json.loads((D/'live/final-context.json').read_text())
assert entry['eip']==0x2da9de and context['regs']['eip']==0x2da9de
assert result['attach_existing'] and not result['command'] and not result['new_boot'] and result['remaining_resources']['released']
commands=[['systemctl','--user','show','ampjack-parent45-devkit.service','--no-pager','--property=ActiveState,SubState,MainPID,ControlGroup'],['ss','-xlpnH'],['ss','-ltnpH','sport = :1242']]
observed=[]
for cmd in commands:
    p=subprocess.run(cmd,capture_output=True,text=True)
    if cmd==commands[1]:p.stdout='\n'.join(line for line in p.stdout.splitlines() if str(R.parent/'42-enum-observer/parent-prepared-guest/runtime/qmp.sock') in line)
    observed.append(dict(command=cmd,returncode=p.returncode,stdout=p.stdout,stderr=p.stderr))
assert 'MainPID=0' in observed[0]['stdout'] and 'ActiveState=inactive' in observed[0]['stdout']
assert not observed[1]['stdout'] and not observed[2]['stdout']
assert not Path('/proc/2615613').exists() and not Path('/proc/2615602').exists()
jcmd=['journalctl','--user','_SYSTEMD_INVOCATION_ID=47eda205a040482c8114303de677cd11','--no-pager','-o','json']
j=subprocess.run(jcmd,capture_output=True,text=True)
(D/'live/final-invocation-journal.json').write_text(json.dumps(dict(command=jcmd,returncode=j.returncode,stdout=j.stdout,stderr=j.stderr),indent=2)+'\n')
proof=dict(epoch=time.time(),card='t_af7623e9',attach_existing=True,new_boot=False,new_launch_commands=0,
    original_claim_unchanged=True,immutable_receipt_unchanged=True,base_tests=31,recovery_tests=15,
    base_test_evidence=base['evidence'],recovery_test_evidence=recovery['evidence'],
    privileged_metadata_actual_parity='passed on original PID/start/invocation',
    observed_authenticated_tu_boots=1,entry_eip=hex(entry['eip']),final_eip=hex(context['regs']['eip']),
    live_first_failed_link='generic_load_hold finalizer; duplicate z0 for consumed kernel hold -> E22',
    live_title_method_completed=False,module_attempted=False,usb_attached=False,physical_input='untested',
    cleanup=dict(method='authenticated QMP quit on retained pair',owned_native_absent=True,owned_launcher_absent=True,
      qmp_and_rsp_listeners_absent=True,unit_inactive_mainpid_zero=True,all_owned_native_disk_usb_fds_released_by_exit=True,
      rsp_closed=True,qmp_file_and_socket_closed=True),
    cleanup_commands=observed,final_production_hashes={**base['production_hashes'],**recovery['production_hashes']},
    post_live_fix='generic-hold removal is ownership-tracked/idempotent; strict E22 regression RED then GREEN; NOT re-run live because guest was gracefully exited and no new allowance exists')
(D/'final-verification.json').write_text(json.dumps(proof,indent=2)+'\n')
status=json.loads((D/'status.json').read_text())
status.update(phase='same_boot_diagnostic_finished_clean',observed_authenticated_tu_boots=1,module_attempted=False,
    cleanup_complete=True,tests=dict(base=31,recovery=15,all_passed=True),final_verification='final-verification.json',
    title_flag_explanation='session-result.title=false means load_title did not return because its finalizer failed; entry-hits/entry-verified/final-context prove exact TU reached first instruction')
(D/'status.json').write_text(json.dumps(status,indent=2)+'\n')
print(json.dumps(proof,indent=2))
