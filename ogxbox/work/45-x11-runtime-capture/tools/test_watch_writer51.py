#!/usr/bin/env python3
"""Offline lane51 checker: real captured reads, no runtime or admission.

Writes fresh, atomically allocated run directories under W56 by default.
--red retains the historical attribution diagnostic: the unpaired raw row
must fail that old positive expectation, not indicate a production regression.
The downstream-loop test bypasses ONLY live pin preflight;
it exercises production snapshot/decode/hold/cleanup with an in-memory reader.
No bytes from the TU are supplied as captured memory. Code proof is separate.
"""
import copy
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from typing import Any
from unittest.mock import patch
sys.dont_write_bytecode = True
import enum_watch as e

O=e.WORK/'56-legacy-observer-test'
L=e.ROOT/'post-entry-49/live'

def save(name,value):
    (O/name).write_text(json.dumps(value,indent=2,sort_keys=True)+'\n')

def load():
    rows=[json.loads(line) for line in (L/'ordered-trace.jsonl').read_text().splitlines()]
    assert e.sha((L/'ordered-trace.jsonl').read_bytes())=='aee479e41bf5a0d54693afe799518ac9af448248fbdcd5855b8fddd05f330c1b'
    assert e.sha((L/'final-context.json').read_bytes())=='08f866859576f52e027063a47df3d87aef73911c7b026bc714ef8a9030770db2'
    return rows,json.loads((L/'final-context.json').read_text())

def proof(raw,context,identity,actual,why,plan):
    """Diagnostic mechanical proof only. Never enables production continuation."""
    try:
        e.validate_identity(identity,actual)
        g=raw['regs']; assert why=='T05thread:01;watch:490930;'
        assert g['eip']==0x4131e7 and g['esi']==0x4908b0 and g['ebx']==0
        assert g['esp']==g['ebp']-20
        assert context['regs']==g
        code=bytes.fromhex(context['code']);start=g['eip']-16
        assert code[0x4131e1-start:0x4131e7-start]==bytes.fromhex('899e80000000')
        assert e.read_snapshot(raw,g['esi']+0x80,4)==struct.pack('<I',g['ebx'])
        assert e.u32(e.read_snapshot(raw,g['ebp']+4,4))==0x412d9b
        # Independent mapped immutable TU entries/edges, not byte-scan boundaries.
        xb=e.XBE.read_bytes();assert e.sha(xb)==e.HASHES['xbe']
        table=e.u32(xb,0x120)-e.u32(xb,0x104)
        def mapped(a,n):
            for i in range(e.u32(xb,0x11c)):
                va,vs,off,rs=struct.unpack_from('<4I',xb,table+i*56+4)
                if va<=a and a+n<=va+rs:return xb[off+a-va:off+a-va+n]
            raise AssertionError('unmapped')
        assert mapped(start,len(code))==code
        assert mapped(0x4131bb,14).hex()=='558bec8a45085356578bf10fb6f8'
        assert mapped(0x412d91,10).hex()=='b9b0084900e820040000'
        assert 0x412d9b+struct.unpack('<i',mapped(0x412d97,4))[0]==0x4131bb
        assert mapped(0x4139a0,5).hex()=='e992f3ffff'
        assert mapped(0x412d37,11).hex()=='558d6c249081ecb4000000'
        return True
    except (AssertionError,e.Refusal,KeyError,ValueError,struct.error):return False

class Reader:
    def __init__(self,raw,why):self.raw=raw;self.why=why;self.stopped=False;self.commands=[]
    def regs(self):return self.raw['regs'] if self.stopped else {'eip':0x2da9de}
    def read(self,a,n):
        if a==0x10000 and n==0x178:return bytes.fromhex(PLAN['live_header']) # synthetic loop identity guard, not captured data
        return e.read_snapshot(self.raw,a,n)
    def continue_wait(self,timeout):
        assert not self.stopped,'must hold on first stop';self.stopped=True;return self.why
    def cmd(self,c):
        assert c.startswith(('Z','z')),'no guest control/write command';self.commands.append(c);return 'OK'

class Journal:
    def __init__(self):self.rows=[]
    def emit(self,event,**kw):self.rows.append(dict(event=event,**kw))

def replay(raw,why,actual=None) -> dict[str, Any]:
    r=Reader(raw,why);j=Journal();error=None;result=None
    # Preflight is deliberately out of scope: no captured complete module/pins.
    with patch.object(e,'verify_pins',return_value=None):
        try:result=e.observe(r,PLAN,IDENT,actual or IDENT,j,was_running=True)
        except e.Refusal as ex:error=str(ex)
    return dict(result=result,error=error,rows=j.rows,commands=r.commands,preflight='synthetic bypass; NOT live verification')

class Tests(unittest.TestCase):
    def test_real_row(self):
        raw=ROWS[1]['raw_snapshot'];why=ROWS[1]['stop_reason']
        row=e.Decoder(PLAN,IDENT['base']).decode(raw,why)
        expected={k:v for k,v in ROWS[1].items() if k not in ('seq','monotonic_ns','event','fixture')}
        extension={'local_observer_failure':'missing snapshot bytes 0x4131d7+64'}
        # Historical expectations stay intact; only this exact extension is allowed.
        self.assertEqual(set(row),set(expected)|set(extension))
        self.assertEqual({k:row[k] for k in expected},expected)
        self.assertEqual({k:v for k,v in row.items() if k not in expected},extension)
        self.assertIsNone(row['writer']);self.assertIs(row['unclassified'],True)
        with self.assertRaisesRegex(e.Refusal,r'^missing snapshot bytes 0x4131d7\+64$'):
            e.read_snapshot(raw,0x4131d7,64)
        save('legacy-schema-difference.json',dict(
            added={k:v for k,v in row.items() if k not in expected},
            missing=sorted(set(expected)-set(row)),
            changed=[k for k in expected if row[k]!=expected[k]]))
        self.assertTrue(proof(raw,FINAL,IDENT,IDENT,why,PLAN))
        result=replay(raw,why);self.assertTrue(result['result']['hold']);self.assertFalse(result['result']['restore_running'])
        save('final-seq2-decoded.json',row);save('real-row-replay.json',result)
    def test_one_at_a_time_negatives(self):
        outcomes=[]
        for name in ('wrong_pc','wrong_bytes','wrong_ea','wrong_width','wrong_frame','wrong_caller','wrong_identity','missing_memory','unrelated_writer'):
            raw=copy.deepcopy(ROWS[1]['raw_snapshot']);context=copy.deepcopy(FINAL);actual=copy.deepcopy(IDENT);why=ROWS[1]['stop_reason']
            if name=='wrong_pc':raw['regs']['eip']+=1
            if name=='wrong_bytes':
                b=bytearray.fromhex(context['code']);b[10]^=1;context['code']=b.hex()
            if name=='wrong_ea':raw['regs']['esi']+=4
            if name=='wrong_width':
                b=bytearray.fromhex(context['code']);b[10:16]=bytes.fromhex('66899e800000');context['code']=b.hex()
            if name=='wrong_frame':raw['regs']['ebp']+=4
            if name=='wrong_caller':
                for m in raw['memory']:
                    b=bytearray.fromhex(m['hex']);a=raw['regs']['ebp']+4
                    if m['address']<=a and a+4<=m['address']+len(b):struct.pack_into('<I',b,a-m['address'],0x412d9c);m['hex']=b.hex()
            if name=='wrong_identity':actual['boot_id']='not-the-captured-boot'
            if name=='missing_memory':raw['memory']=[m for m in raw['memory'] if m['address']!=0x4908b0]
            if name=='unrelated_writer':raw['regs']['eip']=0x4131de
            self.assertFalse(proof(raw,context,IDENT,actual,why,PLAN),name)
            try:
                decoded=e.Decoder(PLAN,IDENT['base']).decode(raw,why)
                self.assertTrue(decoded.get('unclassified'),name)
            except e.Refusal:decoded={'refused':True} # missing memory fails closed, never invented
            outcome=replay(raw,why,actual)
            if name=='wrong_identity':self.assertIsNotNone(outcome['error']);self.assertEqual(outcome['commands'],[])
            else:
                cleanup=[r for r in outcome['rows'] if r['event']=='cleanup'][-1]
                self.assertTrue(cleanup['hold'],name);self.assertFalse(cleanup['restore_running'],name)
            outcomes.append(dict(name=name,proof=False,decoded=decoded,downstream=outcome))
        save('negative-results.json',outcomes)
    def test_historical_unknown_separate(self):
        raw=copy.deepcopy(ROWS[1]['raw_snapshot']);raw['regs']['eip']=0x999999
        row=e.Decoder(PLAN,IDENT['base']).decode(raw,'T05watch:490930;')
        self.assertTrue(row['unclassified']);self.assertIsNone(row['writer'])
        save('historical-unknown-control.json',dict(synthetic=True,row=row))

if __name__=='__main__':
    O.mkdir(parents=True,exist_ok=True)
    O=Path(tempfile.mkdtemp(prefix='run-',dir=O))
    print(f'output_dir={O}',flush=True)
    ROWS,FINAL=load();IDENT=ROWS[0]['identity'];PLAN=e.prepare()
    if '--red' in sys.argv:
        row=e.Decoder(PLAN,IDENT['base']).decode(ROWS[1]['raw_snapshot'],ROWS[1]['stop_reason'])
        save('baseline-seq2-decoded.json',row)
        assert row.get('writer')==0x4131e1,'RED historical diagnostic: unpaired captured row lacks code; unknown/hold is correct, not a production regression'
    else:
        suite=unittest.defaultTestLoader.loadTestsFromTestCase(Tests)
        result=unittest.TextTestRunner(verbosity=2).run(suite)
        save('focused-result.json',dict(passed=result.wasSuccessful(),tests=result.testsRun,production_changed=False,runtime=False))
        raise SystemExit(0 if result.wasSuccessful() else 1)
