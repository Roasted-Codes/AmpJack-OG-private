#!/usr/bin/env python3
"""Host-only CLI regression. Writes exclusively below W45; no guest access."""
import copy
import sys
sys.dont_write_bytecode=True
import json
import os
import struct
import subprocess
import sys
from pathlib import Path
import enum_watch as e

R=e.ROOT
F=R/'fixtures'; F.mkdir(exist_ok=True)
testroot=R/'evidence/tests'; testroot.mkdir(parents=True,exist_ok=True)
run=1
while (testroot/f'run-{run:03d}').exists(): run+=1
O=testroot/f'run-{run:03d}'; O.mkdir()
P=e.prepare()
# Only test addresses, never journals from a previous boot. Not a live allocation.
B=0x83000000
identity=dict(boot_id='SYNTHETIC-NOT-A-BOOT',pid=42,start_ticks=4242,base=B,module=B+0x3978,elf_sha256=e.HASHES['elf'],layout_sha256=e.HASHES['layout'])

def snap(pc,*,cur=0,pending=0,stage=0,marker=0,ecx=0,esi=0,eax=0,edx=0,words=(),frame_ret=0):
    state=bytearray(0x84); state[3]=marker; state[0x78]=stage
    struct.pack_into('<II',state,0x7c,pending,cur)
    regs=dict(eip=pc,esp=0x81001000,ebp=0x81002000,ecx=ecx,esi=esi,eax=eax,edx=edx)
    stack=bytearray(64)
    for i,w in enumerate(words): struct.pack_into('<I',stack,4*i,w)
    frame=struct.pack('<4I',0,frame_ret,0,0)
    return dict(regs=regs,memory=[dict(address=0x4908b0,hex=state.hex()),dict(address=regs['esp'],hex=stack.hex()),dict(address=regs['ebp'],hex=frame.hex())])

def stop(pc,why='T05',**kw): return dict(snapshot=snap(pc,**kw),why=why)

def case(name,data,expect,check=None):
    path=F/(name+'.json'); path.write_text(json.dumps(data,indent=2)+'\n')
    log=O/(name+'.jsonl')
    # Files are append-only per run via a fresh numbered directory on reruns.
    cmd=[sys.executable,'-B',str(R/'tools/enum_watch.py'),'--fixture',str(path),'--log',str(log)]
    if name=='positive': cmd+=['--pins-out',str(R/'evidence/pins.json')]
    p=subprocess.run(cmd,text=True,capture_output=True,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','TMPDIR':str(R/'tmp')})
    res=json.loads(log.with_suffix('.result.json').read_text())
    rows=[json.loads(l) for l in log.read_text().splitlines()]
    assert p.returncode==expect,(name,p.stdout,p.stderr)
    assert res['active_after_cleanup']==[],(name,res)
    assert res['restored_state']['clients_closed']
    if check: check(res,rows)
    return dict(name=name,exit_code=p.returncode,command=cmd,stdout=p.stdout,stderr=p.stderr,result=res,rows=len(rows))

def no_arm(res,rows): assert res['arm_commands']==0,(res,rows)
base: dict = dict(identity=identity,actual=copy.deepcopy(identity),stops=[])
results=[]
# W35 exact pin is not merely wrong bytes: byte 0x00 is INSIDE push imm32.
legacy=P['legacy_red']; dump=e.DUMP.read_bytes()
legacy.update(actual_five=dump[0x41672e-0x412000:0x41672e-0x412000+5].hex(),w35_expected='ff15f8b64100',refused_before_arm=True)
(R/'evidence/legacy-red.json').write_text(json.dumps(legacy,indent=2)+'\n')
assert legacy['actual_five']!=legacy['w35_expected']
positive=copy.deepcopy(base)
positive['stops']=[
 stop(0x416412,cur=0,esi=0x8000056c),
 stop(0x416418,'T05watch:490930;',cur=0x8000056c),
 stop(0x41642d,cur=0x8000056c,words=(0x490900,0xfff0bdc0,0xffffffff,0x4908e4)),
 stop(0x416433,cur=0x8000056c,eax=0),
 stop(B+0xa0a,cur=0x8000056c,words=(0x416b40,0x8000056c)),
 stop(B+0xab1,cur=0x8000056c,words=(0x8000056c,0xc0000001)),
 stop(0x416992,cur=0x8000056c,ecx=0x8000056c,words=(B+0xf08,0xc0000001),frame_ret=B+0xab7),
 stop(0x4168c0,cur=0x8000056c,words=(0x416b17,0,0x8000056c)),
 stop(0x4167f9,cur=0x8000056c,ecx=0x8000056c,words=(0x416929,)),
 stop(0x41668e,cur=0x8000056c,marker=10,words=(0x416875,0,0x8000056c)),
 stop(0x4166bb,'T05watch:490930;',cur=0,marker=10),
 stop(0x417078,cur=0,marker=10),
 stop(0x416568,cur=0,marker=10,esi=0)]

def check_positive(res,rows):
    stops=[r for r in rows if r['event']=='stop']
    assert res['hold'] and stops[-1]['pre_fault_hold']
    assert stops[6]['caller']=='module_refused_attach_transport_c_202'
    assert stops[6]['device']==0x8000056c and stops[6]['status']==-1073741823
    assert stops[10]['writer']==0x4166b5
    assert stops[11]['expiry_arm_device']['device']==0x8000056c
    assert all(x['fixture'] for x in stops)
results.append(case('positive',positive,0,check_positive))
for key in ('pid','start_ticks','elf_sha256','layout_sha256','boot_id'):
    d=copy.deepcopy(base); d['actual'][key]='STALE'
    results.append(case('stale-'+key,d,2,no_arm))
d=copy.deepcopy(base); d['mutate_pin']=0x416732
results.append(case('mutated-pin',d,2,no_arm))
for flag in ('legacy_pin','mutate_expected_pin'):
    d=copy.deepcopy(base); d[flag]=True
    results.append(case(flag,d,2,no_arm))
d=copy.deepcopy(base); d['fail_arm_after']=3
results.append(case('partial-arm',d,2))
for running in (False,True):
    d=copy.deepcopy(base); d['was_running']=running
    def check_timeout(res,rows):
        assert res['restore_running']==running and not res['hold']
        assert res['restored_state']['running']==running
        assert res['qmp_commands']==['cont' if running else 'stop','query-status']
        assert any(x['event']=='timeout_paused' for x in rows)
    results.append(case('timeout-'+str(running),d,0,check_timeout))
d=copy.deepcopy(base); d['stops']=[stop(0x123456)]
results.append(case('unknown-stop',d,0,lambda res,rows: (None if res['hold'] else (_ for _ in ()).throw(AssertionError('must hold')))))
# Shared decoder direct cases cover success, real stock callers, tail and cancellation.
D=e.Decoder(P,B)
x=D.decode(snap(0x416992,ecx=123,words=(B+0xf08,0),frame_ret=B+0x2bbe),'T05')
assert x['caller']=='module_signal_add_complete' and x['status']==0
x=D.decode(snap(0x416992,ecx=456,words=(0x416b4e,0x80000400)),'T05')
assert x['caller']=='stock_call' and x['device']==456
x=D.decode(snap(0x416992,ecx=456,words=(0x80123456,0)),'T05')
assert x['caller']=='unknown'
D.decode(snap(B+0xf4f,ecx=123,eax=0x4165c6,words=(0x80123456,)),'T05')
x=D.decode(snap(0x4165c6,ecx=123,words=(0x80123456,)),'T05')
assert x['caller']=='module_remove_tail'
D.decode(snap(0x416732,cur=123,words=(0x490900,1,2,0x4908e4)),'T05')
D.decode(snap(0x416738,cur=123),'T05')
x=D.decode(snap(0x416938,eax=1),'T05'); assert D.arm is None and x['cancel_result']
x=D.decode(snap(0x999999),'T05watch:490930;'); assert x['writer'] is None
# Actual archived final state: no fabricated pre-fault chronology.
saved=R.parent/'35-loading-stop/probe3'
raw=(saved/'mem_00490000_1000.bin').read_bytes()
assert e.sha(raw)=='657ef96f85f11e6db9985e653e3b04d21d41bd50542d4b646b42d47748b8a891'
archive=json.loads((saved/'probe-1795588560.json').read_text())
s={'regs':archive['regs'],'memory':[dict(address=0x4908b0,hex=raw[0x8b0:0x934].hex())]}
# Stack is unavailable in this probe; decoder must mark it unavailable, not zero-fill.
x=D.decode(s,'ARCHIVE_POST_HALT_STACK_UNAVAILABLE')
x['provenance']='W35 saved final state; unavailable stack excluded; NOT a pre-fault event'
assert x['current']==0 and x['marker']==10 and x['stage']==0
(R/'evidence/archived-state-decoded.json').write_text(json.dumps(x,indent=2)+'\n')
(R/'evidence/test-results.json').write_text(json.dumps(dict(cli_cases=results,decoder_checks='passed',legacy_red=legacy,live_evidence=False),indent=2)+'\n')
print(json.dumps(dict(cli_cases=len(results),decoder_checks='passed',legacy_red='reproduced',live_evidence=False)))
