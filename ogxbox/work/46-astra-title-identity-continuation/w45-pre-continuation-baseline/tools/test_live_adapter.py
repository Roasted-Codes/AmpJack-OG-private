#!/usr/bin/env python3
"""Minimal preboot adapter regressions using archived real XML, no guest."""
import copy
import sys
sys.dont_write_bytecode=True
import json
import os
import struct
from pathlib import Path
import live_adapter as a
import enum_watch as e
R=a.ROOT; archive=R.parent/'35-loading-stop/probe3'
class XML:
    def target_xml(self,name='target.xml'):return (archive/name).read_text()
    def raw_regs(self):return (archive/'g.hex').read_text().strip()
schema=a.register_schema(XML());a.save('continuation/schema-offline.json',schema)
# Pins.verify_header is from the exact selected, already repaired W27 loader.
b=bytearray(e.XBE.read_bytes()[:0x178])
for off,key in ((0x128,0xa8fc57ab),(0x158,0x5b6d40b6)):struct.pack_into('<I',b,off,e.u32(b,off)^key)
class Mem:
    def read(self,addr,n):assert addr==0x10000;return bytes(b[:n])
pins=a.loader.Pins();pins.verify_header(Mem())
b[0x120]^=1
try:pins.verify_header(Mem());raise AssertionError('header mutation accepted')
except a.loader.LoaderError:pass
identity=a.native(os.getpid()); bad=copy.deepcopy(identity);bad['start_ticks']+=1
try:a.check_native(bad,{'xemu_sha256':identity['native_sha256']});raise AssertionError('identity mutation accepted')
except e.Refusal as ex: assert 'start_ticks' in str(ex)
p=e.prepare(); fixture=json.loads((R/'fixtures/positive.json').read_text()); fixture['stops']=[];fixture['fail_arm_after']=3
r=e.Fixture(fixture,p);j=e.Journal(R/'continuation/partial-arm-offline.jsonl')
try:
    try:e.observe(r,p,fixture['identity'],fixture['actual'],j);raise AssertionError('partial arm accepted')
    except e.Refusal:pass
finally:j.close()
assert not r.active
q=e.FixtureQMP(True);res=e.finish_clients(q,r,prior_running=True,hold=True)
assert res['running'] is False and q.f.closed and q.s.closed and q.closed
m=a.loader.Module(e.ELF.read_bytes(),json.loads(e.LAYOUT.read_text()));assert m.required==0x9000
result=dict(archived_xml_registers=len(schema['widths']),packet_bytes=len(bytes.fromhex(schema['raw_g'])),
            header_decoded_pass=True,other_header_byte_refused=True,stale_native_start_refused=True,
            partial_arm_removed=True,safety_hold_paused_and_both_qmp_objects_closed=True,
            selected_loader=str(a.LOADER_PATH),loader_sha256=e.sha(a.LOADER_PATH.read_bytes()),module_required=m.required,
            live_evidence=False)
a.save('continuation/adapter-tests.json',result);print(json.dumps(result,indent=2))
