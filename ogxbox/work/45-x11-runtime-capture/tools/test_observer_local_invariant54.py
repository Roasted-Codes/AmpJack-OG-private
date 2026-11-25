#!/usr/bin/env python3
"""Offline Astra54: captured seq2 + paired final code; synthetic preflight/future stops."""
import sys
sys.dont_write_bytecode=True
import copy
import json
import tempfile
import unittest
from unittest import mock
from pathlib import Path
O=Path(__file__).resolve().parents[2]/'54-observer-local-invariant'
O.mkdir(exist_ok=True)
RUN=Path(tempfile.mkdtemp(prefix='focused-',dir=O))
sys.pycache_prefix=str(RUN/'never-inherited-cache')
import enum_watch as e
R=e.ROOT
assert e.sha((R/'post-entry-49/live/ordered-trace.jsonl').read_bytes())=='aee479e41bf5a0d54693afe799518ac9af448248fbdcd5855b8fddd05f330c1b'
assert e.sha((R/'post-entry-49/live/final-context.json').read_bytes())=='08f866859576f52e027063a47df3d87aef73911c7b026bc714ef8a9030770db2'
ROWS=[json.loads(x) for x in (R/'post-entry-49/live/ordered-trace.jsonl').read_text().splitlines()]
FINAL=json.loads((R/'post-entry-49/live/final-context.json').read_text())
REAL=copy.deepcopy(ROWS[1]['raw_snapshot'])
assert len(ROWS)==3 and FINAL['regs']==REAL['regs']
assert bytes.fromhex(FINAL['stack'])[:64].hex()==REAL['memory'][1]['hex']
PAIRED=copy.deepcopy(REAL)
PAIRED['memory'].append(dict(address=FINAL['regs']['eip']-16,hex=FINAL['code']))
WHY=ROWS[1]['stop_reason']
PLAN=e.prepare()
IDENTITY=ROWS[0]['identity']

class Replay(e.Fixture):
    """No endpoint: preflight header/text/pins are synthetic frozen-reference scaffolding.
    Stopped code reads are ONLY paired captured bytes, never Fixture's DUMP fallback.
    Identity actual equality is synthetic; historical process is not queried.
    """
    def __init__(self,stops,step=None):
        super().__init__(dict(identity=IDENTITY,stops=stops),PLAN)
        self.next_step=step; self.continues=0; self.watch_receipts=[];self.code_reads=[]
    def read(self,a,n):
        if self.index>=0 and a==self.current['regs']['eip']-16:
            self.code_reads.append(dict(address=a,length=n,source='paired final-context.code only; failure if absent'))
            return e.read_snapshot(self.current,a,n)
        if self.index>=0:
            for b in self.current['memory']:
                if b['address']==a and len(bytes.fromhex(b['hex']))>=n:
                    return bytes.fromhex(b['hex'])[:n]
        return super().read(a,n)
    def continue_wait(self,timeout):
        self.continues+=1
        if self.index>=0:self.watch_receipts.append(sorted(self.active))
        return super().continue_wait(timeout)
    def step(self):
        if self.next_step:
            self.current=copy.deepcopy(self.next_step['snapshot'])
            self.watch_receipts.append(sorted(self.active))
            return self.next_step['why']
        return 'T05'

def stop(s,why=WHY):return dict(snapshot=copy.deepcopy(s),why=why)
def unknown():
    s=copy.deepcopy(REAL);s['regs']['eip']=0x413300
    return stop(s)

def run_case(name,first,*,step=False,actual=None,plan=None,max_stops=2048):
    lead=copy.deepcopy(REAL);lead['regs']['eip']=0x416375
    r=Replay([stop(lead,'T05thread:01;'),unknown()] if step else [first,unknown()],first if step else None)
    j=e.Journal(RUN/(name+'.jsonl'))
    error=None;result=None
    try:result=e.observe(r,PLAN if plan is None else plan,IDENTITY,IDENTITY if actual is None else actual,j,was_running=True,max_stops=max_stops)
    except e.Refusal as ex:error=str(ex)
    finally:j.close()
    rows=[json.loads(x) for x in (RUN/(name+'.jsonl')).read_text().splitlines()]
    # Separate provenance keeps production raw state unmodified. In successful
    # real replays, the final watch is explicitly synthetic, not captured seq3.
    (RUN/(name+'.sources.json')).write_text(json.dumps(dict(
        journal=name+'.jsonl',first_input='captured seq2 + paired final-context.code or explicitly named one-factor variant',
        lead_in='synthetic breakpoint' if step else None,
        next_input='SYNTHETIC unfamiliar current write at 0x413300, NOT historical seq3',
        actual_identity='synthetic equality to captured arming identity; no process lookup',
        code_reads=r.code_reads,continues=r.continues,watch_receipts=r.watch_receipts),indent=2)+'\n')
    return r,rows,result,error

class LocalInvariant(unittest.TestCase):
    def test_00_real_normal_and_step(self):
        for stepping in (False,True):
            with self.subTest(step=stepping):
                r,rows,res,err=run_case('real-step' if stepping else 'real-normal',stop(PAIRED),step=stepping)
                self.assertIsNone(err)
                events=[x for x in rows if x['event'] in ('stop','step_watch')]
                first=next(x for x in events if x['eip']==0x4131e7)
                self.assertEqual(first.get('writer'),0x4131e1,'real seq2 writer attribution')
                self.assertFalse(first.get('unclassified',False),'full local predicate policy')
                self.assertEqual(first['writer_kind'],'stock_object_80_store_pre_alloc')
                self.assertEqual(first['writer_width'],4)
                self.assertEqual(first['writer_ea'],0x490930)
                self.assertEqual(first['stored_value'],0)
                self.assertEqual(first['direct_caller'],0x412d96)
                self.assertEqual(first['regs'],REAL['regs'])
                self.assertEqual(rows[0]['pins'],ROWS[0]['pins'])
                self.assertEqual(r.code_reads,[dict(address=0x4131d7,length=64,source='paired final-context.code only; failure if absent')])
                self.assertEqual(first['stop_reason'],WHY)
                self.assertEqual(first['raw_snapshot']['memory'][:3],REAL['memory'])
                for key in ('device','status','timer_arm_device'):self.assertIsNone(first[key])
                self.assertEqual(first['attribution'],'unknown')
                self.assertEqual(first['timer_raw'],ROWS[1]['timer_raw'])
                self.assertEqual(sum(x['eip']==0x4131e7 for x in events),1)
                self.assertEqual(events[-1]['eip'],0x413300)
                self.assertEqual([x['eip'] for x in events],
                                 [0x416375,0x4131e7,0x413300] if stepping else [0x4131e7,0x413300])
                self.assertTrue(events[-1]['unclassified'])
                self.assertTrue(res['hold']);self.assertFalse(res['restore_running'])
                self.assertEqual(r.continues,2)
                for active in r.watch_receipts:
                    self.assertIn('2,490930,4',active);self.assertIn('2,490928,1',active)
                self.assertFalse(r.active)
    def test_historical_without_code_holds(self):
        r,rows,res,err=run_case('unpaired-history',stop(REAL))
        self.assertTrue(res['hold']);self.assertFalse(res['restore_running']);self.assertEqual(r.continues,1)
    def test_stale_identity_before_arm(self):
        actual=copy.deepcopy(IDENTITY);actual['start_ticks']+=1
        r,rows,res,err=run_case('stale',stop(PAIRED),actual=actual)
        self.assertIn('stale start_ticks',err);self.assertFalse(r.calls)

    def test_one_factor_matrix(self):
        cases=[]
        def reg(name,value):
            s=copy.deepcopy(PAIRED);s['regs'][name]=value
            cases.append((name,stop(s)))
        for name,value in (('eip',0x4131e8),('esi',0x4908b4),('ecx',0x4908b4),
                           ('ebx',1),('esp',REAL['regs']['esp']+4),('ebp',REAL['regs']['ebp']+4),
                           ('edi',28),('eax',0x380)):
            reg(name,value)
        # Change one logical memory field consistently in all overlapping spans.
        def mem(name,address,value):
            s=copy.deepcopy(PAIRED)
            for b in s['memory']:
                data=bytearray.fromhex(b['hex'])
                for i,v in enumerate(value):
                    offset=address+i-b['address']
                    if 0<=offset<len(data):data[offset]=v
                b['hex']=data.hex()
            cases.append((name,stop(s)))
        mem('post-value',0x490930,b'\x01')
        mem('object-byte',0x49092a,b'\x1c')
        mem('caller',REAL['regs']['ebp']+4,b'\x9c')
        mem('arg1',REAL['regs']['ebp']+8,b'\x1c')
        mem('arg2',REAL['regs']['ebp']+12,b'\x03')
        mem('size',REAL['regs']['esp'],b'\x80')
        mem('tag',REAL['regs']['esp']+4,b'\x54')
        mem('opcode',0x4131e1,b'\x90')
        mem('width',0x4131e1,b'\x88')
        for name,why in (
            ('trap','T05'),('thread','T05thread:02;watch:490930;'),
            ('signal','T04thread:01;watch:490930;'),('stage','T05thread:01;watch:490928;'),
            ('wrong-watch','T05thread:01;watch:490934;'),
            ('mixed-watch','T05thread:01;watch:490930;watch:490928;'),
            ('mixed-read','T05thread:01;watch:490930;rwatch:490930;'),
            ('mixed-break','T05thread:01;watch:490930;swbreak:;')):
            cases.append((name,stop(PAIRED,why)))
        for name,index in (('missing-window',3),('missing-object',0),('missing-stack',1)):
            s=copy.deepcopy(PAIRED);s['memory'].pop(index)
            cases.append((name,stop(s)))
        s=copy.deepcopy(PAIRED)
        s['memory'][1]['hex']=s['memory'][1]['hex'][:40]
        s['memory'].pop(2)
        cases.append(('missing-frame-span',stop(s)))
        s=copy.deepcopy(PAIRED)
        s['memory'][2]['hex']='59'+s['memory'][2]['hex'][2:]
        cases.append(('conflicting-frame-overlap',stop(s)))
        s=copy.deepcopy(PAIRED);s['memory'][3]['hex']=s['memory'][3]['hex'][:-2]
        cases.append(('short-code-window',stop(s)))
        s=copy.deepcopy(PAIRED);s['regs']['eip']=0x414000
        cases.append(('unrelated-zero-writer',stop(s)))
        receipts=[]
        for name,first in cases:
            for stepping in (False,True):
                with self.subTest(name=name,step=stepping):
                    # Wrong-PC case is still an explicit hardware watch stop.
                    r,rows,res,err=run_case(name+('-step' if stepping else '-normal'),first,step=stepping)
                    cleanup=rows[-1]
                    self.assertEqual(cleanup['event'],'cleanup')
                    self.assertTrue(cleanup['hold']);self.assertFalse(cleanup['restore_running'])
                    self.assertEqual(r.continues,1,'must not continue past refusing candidate')
                    self.assertFalse(r.active)
                    refused=[x for x in rows if x['event'] in ('stop','step_watch') and x.get('unclassified')]
                    self.assertTrue(err or refused)
                    receipts.append(dict(name=name,step=stepping,layer='exception_hold' if err else 'decoded_hold',
                                         error=err,hold=cleanup['hold'],restore_running=cleanup['restore_running'],continues=r.continues))
        (RUN/'negative-matrix.json').write_text(json.dumps(receipts,indent=2)+'\n')

    def test_descriptor_refusals(self):
        # Real prepare() rejects each malformed static edge against unchanged,
        # hash-authenticated XBE. No altered file or weakened hash gate.
        receipts=[]
        for address in (0x1273f4,0x4139a0,0x412d37,0x412d91,0x412d96,0x4131bb,0x4131e1,0x4131e7):
            bad=tuple((a,'90' if a==address else b) for a,b in e.LOCAL_INSTRUCTIONS)
            with self.subTest(address=hex(address)),mock.patch.object(e,'LOCAL_INSTRUCTIONS',bad):
                with self.assertRaisesRegex(e.Refusal,'local descriptor static edge mismatch'):
                    e.prepare()
            receipts.append(dict(address=hex(address),layer='prepare static edge refusal'))
        plan=copy.deepcopy(PLAN);plan['local_observer']['width']=1
        r,rows,res,err=run_case('mutated-descriptor',stop(PAIRED),plan=plan)
        self.assertIn('mutated local observer descriptor',err);self.assertFalse(r.calls)
        plan=copy.deepcopy(PLAN);plan.pop('local_observer')
        r,rows,res,err=run_case('missing-descriptor',stop(PAIRED),plan=plan)
        self.assertTrue(res['hold']);self.assertEqual(r.continues,1)
        (RUN/'static-refusals.json').write_text(json.dumps(receipts,indent=2)+'\n')

    def test_ordinary_prefault_bound_controls(self):
        # Existing absolute writer recognition remains independent of this case.
        s=copy.deepcopy(REAL);pc=next(iter(PLAN['writers']));s['regs']['eip']=pc
        r,rows,res,err=run_case('known-ordinary',stop(s))
        first=next(x for x in rows if x['event']=='stop')
        self.assertEqual(first['writer'],PLAN['writers'][pc]);self.assertNotIn('unclassified',first)
        self.assertEqual(r.continues,2);self.assertTrue(res['hold'])
        s=copy.deepcopy(REAL);s['regs'].update(eip=0x416568,esi=0)
        r,rows,res,err=run_case('pre-fault',stop(s,'T05thread:01;'))
        self.assertTrue(rows[1]['pre_fault_hold']);self.assertEqual(r.continues,1)
        self.assertTrue(res['hold']);self.assertFalse(res['restore_running'])
        r,rows,res,err=run_case('stop-bound',stop(PAIRED),max_stops=1)
        self.assertTrue(res['hold']);self.assertFalse(res['restore_running'])
        self.assertIn('stop_bound_unknown',[x['event'] for x in rows]);self.assertFalse(r.active)

    def test_diagnostic_writer_is_not_policy(self):
        s=copy.deepcopy(PAIRED)
        # Mechanically attributable code/value but wrong argument/tag must hold.
        b=s['memory'][1];b['hex']=b['hex'][:8]+'54534244'+b['hex'][16:]
        r,rows,res,err=run_case('mechanical-not-qualified',stop(s))
        first=rows[1]
        self.assertEqual(first['writer'],0x4131e1);self.assertTrue(first['unclassified'])
        self.assertTrue(res['hold']);self.assertFalse(res['restore_running']);self.assertEqual(r.continues,1)

if __name__=='__main__':
    for name in ('ordered-trace.jsonl','final-context.json'):
        (RUN/('original-'+name)).write_bytes((R/'post-entry-49/live'/name).read_bytes())
    (RUN/'sources.json').write_text(json.dumps(dict(
        raw=str(R/'post-entry-49/live/ordered-trace.jsonl'),raw_row=2,
        captured_code=str(R/'post-entry-49/live/final-context.json'),code_start='EIP-16',
        static_reference=str(e.XBE),synthetic=['preflight frozen-reference header/text/pins','actual identity equality','breakpoint lead-in','next unfamiliar write at 0x413300'],
        missing=['historical live preflight reads','observed upper stack','prior current value','semantic/async/global alias proof']),indent=2)+'\n')
    print('OUTPUT_DIRECTORY='+str(RUN),flush=True)
    unittest.main(verbosity=2)
