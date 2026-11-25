#!/usr/bin/env python3
"""Verify bounded W45 stop and write derived status; never boot."""
import sys
sys.dont_write_bytecode = True
import hashlib
import json
from pathlib import Path
import subprocess
import time
from parent_launch import ROOT, receipt, DIGEST

def load(path):
    return json.loads((ROOT/path).read_text())

def main():
    lease=receipt()
    p=subprocess.run(['/usr/bin/python3','-B',str(ROOT/'parent_launch.py'),'--check'],capture_output=True,text=True)
    (ROOT/'guarded-check.json').write_text(json.dumps({'command':p.args,'returncode':p.returncode,'stdout':p.stdout,'stderr':p.stderr},indent=2)+'\n')
    assert p.returncode==0
    p=subprocess.run(['/usr/bin/python3','-B',str(ROOT/'collect_boundary.py')],capture_output=True,text=True)
    assert p.returncode==0,p.stderr
    f=load('fixture-result.json');window=json.loads(f['stdout'])
    assert f['returncode']==0 and window['passed'] and window['driver']=='x11' and not window['xauthority_present']
    c=load('contract-tests.json');assert c['cases']==13 and c['real_commands_used']==0
    b=load('boundary-cleanup.json')
    assert b['fixture_pid_absent'] and not b['qmp_path_exists'] and not b['guest_disk_fds']
    assert not [p for p in b['processes'] if Path(p['exe']).name in ('xemu','xemu-network')]
    unit=load('new-unit.json')['stdout']
    assert 'LoadState=not-found' in unit and 'MainPID=0' in unit
    assert ':1242 ' not in load('tcp-listeners.json')['stdout']
    assert not (ROOT/'runtime-claim.json').exists()
    assert hashlib.sha256((ROOT/'PARENT-RUNTIME-LEASE.json').read_bytes()).hexdigest()==DIGEST
    q=load('qualification.json');assert q['runtime_authorized'] is False
    assert len(load('evidence/pins.json')['pins'])==46
    status={'state':'STOPPED_UNSPENT_TITLE_IDENTITY_MISMATCH','finished_epoch':time.time(),'scope_completed':False,'bounded_stop_verified':True,'owner':lease['owner'],'receipt_sha256':DIGEST,'receipt_unchanged':True,'route':{'provider':'openai-codex','model':'gpt-6.1-sol','session':'local-b08abd23a4af4ffd190a931df57415c94e83552a001575633a0fd96cbd14e51f','fallback':False},'fixture':{'passed':True,'backend':'x11','display':':2','xid':window['x11_window_id'],'pid':window['pid'],'process_exited':True,'sdl_version':window['sdl_version']},'path_parity':'static comparison only; actual guarded native privileges/environment/backend/GPU not exercised','first_unsupported_boundary':q['first_unsupported_boundary'],'expected_title_sha256':q['expected_title_sha256'],'mismatches':q['mismatches'],'launch_commands':{'historical':1,'W45_attempted':0,'W45_remaining':1,'cumulative_used':1,'cumulative_ceiling':2},'authenticated_title_boots':0,'real_claim_exists':False,'observer_offline_cases':13,'pins':46,'contract_cases':13,'legacy_RED':'preserved','runtime_session':'staged incomplete and wrapper-disabled; not live qualified','physical_input':'UNTESTED','qmp_clients_opened':0,'rsp_clients_opened':0,'module_installed':False,'passthrough_attached':False,'cleanup':'no guest launched; fixture exited, unit absent, endpoints absent, no guest process or readable disk FD','inaccessible_proc_fd_directory_count':len(b['inaccessible_proc_fd_dirs']),'parent_takeover':'none needed; no live guest','parent_required_check':'Clarify whether mandated 21b207... SHA covers only TU and qualify measured base retail SHA; no substitution or retry by worker','evidence':['REPORT.md','HANDOFF.md','fixture-result.json','qualification.json','continuation/preflight.json','contract-tests.json','boundary-cleanup.json','guarded-check.json']}
    (ROOT/'status.json').write_text(json.dumps(status,indent=2)+'\n')
    verification={'acceptance':'bounded prelaunch stop verified; full runtime assignment incomplete','receipt_sha256':DIGEST,'checks_passed':True,'real_launch_attempts':0,'real_claim_absent':True,'unit':unit,'fixture_process_absent':b['fixture_pid_absent'],'qmp_absent':not b['qmp_path_exists'],'tcp1242_listener_absent':True,'observed_title_boots':0,'written_epoch':time.time()}
    (ROOT/'final-verification.json').write_text(json.dumps(verification,indent=2)+'\n')
    print(json.dumps(verification,indent=2))

if __name__=='__main__':
    main()
