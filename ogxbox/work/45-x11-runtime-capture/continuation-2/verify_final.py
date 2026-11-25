#!/usr/bin/env python3
"""Final read-only W45 verification; no disk/guest/endpoint interaction."""
import sys
sys.dont_write_bytecode=True
import hashlib
import json
from pathlib import Path
import subprocess
import time
R=Path(__file__).resolve().parents[1]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
tests=json.loads((R/'continuation-2/tests/result.json').read_text())
assert tests['all_passed'] and tests['tests_run']==31
changed={n:sha(R/n) for n,digest in tests['production_hashes'].items() if sha(R/n)!=digest}
assert not changed,changed
assert sha(R/'PARENT-RUNTIME-LEASE.json')=='a23591fa85600dad6868f8fb4c0d8a4c56c2a0dc09d40f9f6abd205d1d94d6d9'
assert sha(R/'runtime-claim.json')=='f54e2b26b1284e0316939b6b752f6d48926e8b169cf8e45e75a3bf17660684db'
handle=json.loads((R/'continuation-2/live/launch-handle.json').read_text())
cmd=['systemctl','--user','show',handle['unit'],'--no-pager','--property=InvocationID,ActiveState,SubState,MainPID,ControlGroup,Restart']
p=subprocess.run(cmd,capture_output=True,text=True)
props=dict(line.split('=',1) for line in p.stdout.splitlines() if '=' in line)
assert p.returncode==0 and props['InvocationID']==handle['invocation_id'] and props['Restart']=='no'
procs=[]
for pid in (2615602,2615613):
    try:
        start=int(Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split()[19])
        procs.append(dict(pid=pid,start_ticks=start,present=True))
    except FileNotFoundError:procs.append(dict(pid=pid,present=False))
result=dict(epoch=time.time(),source_hashes_match_tested_invocation=True,changed_test_count=31,changed_test_exit=0,
            production_hashes=tests['production_hashes'],receipt_unchanged=True,claim_unchanged=True,
            commands_consumed=dict(historical=1,w45=1,cumulative=2,remaining=0),
            unit_state=dict(command=cmd,returncode=p.returncode,properties=props),processes=procs,
            cleanup_complete=False,guest_clients_opened=0,physical_input='untested',
            live_authenticated_title_boots=0,canonical_state_or_card_edited=False)
(R/'continuation-2/final-verification.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
