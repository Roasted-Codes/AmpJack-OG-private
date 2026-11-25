#!/usr/bin/env python3
"""Changed W45 paths, synthetic external effects only; never touches G.

Runs real wrapper transaction, session state machine, entry adapter, ordered
observer and healthy recorder/decoder. Not game or physical-input evidence.
"""
import sys
sys.dont_write_bytecode=True
from pathlib import Path
import copy
import io
import json
import os
import struct
import subprocess
import time
import traceback
import unittest
from unittest.mock import patch
import contextlib
import live_adapter as a
import enum_watch as e
import live_preflight as p
import runtime_session as s
import runtime_effects as f
import capture_layout
sys.path.insert(0,str(a.ROOT))
import parent_launch as w
ROOT=a.ROOT
TESTS=ROOT/'post-entry-49/tests'
RUN=TESTS/('run-'+str(time.time_ns()))
RUN.mkdir(parents=True)
PLAN=e.prepare()
with patch.object(e,'ROOT',RUN):LAYOUT=capture_layout.prepare()
LEASE=w.receipt()
FIXTURE_SESSION='isolated-W45-test-session'
CANON=dict(owner_hold=False,resume_authorized=True,resume_authority_message=LEASE['authority'],
    scope_correction_message=LEASE['scope_correction'],runtime_card='t_af7623e9',
    runtime_owner='45-x11-runtime-capture exclusive conditional lease; no parent clients or competing writer',
    runtime_binding=dict(state='verified',card='t_af7623e9',owner=ROOT.name,provider='openai-codex',
        model='gpt-6.1-sol',route_verified=True,session=FIXTURE_SESSION,unused_commands=1,
        receipt_sha256=w.DIGEST,title_attestation_sha256=p.TITLE_DIGEST))
ENV={k:'fixture' for k in ('DISPLAY','WAYLAND_DISPLAY','SDL_VIDEO_DRIVER','XDG_RUNTIME_DIR','PYTHONDONTWRITEBYTECODE','TMPDIR','TMP','TEMP')}
ENV.update(DISPLAY=':2',SDL_VIDEO_DRIVER='x11')
IDENT=dict(pid=123,start_ticks=456,boot_id='fixture-only',base=0x83f00000,module=0x83f03978,elf_sha256=e.HASHES['elf'],layout_sha256=e.HASHES['layout'])

def completed(cmd,stdout='',returncode=0):return subprocess.CompletedProcess(cmd,returncode,stdout,'')
def isolated_save(name,obj):
    path=RUN/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(obj,indent=2)+'\n');return obj

class End:
    def __init__(self,events,name):self.events=events;self.name=name;self.closed=False
    def close(self):self.closed=True;self.events.append(self.name+'.close')
class Q:
    def __init__(self,events):self.events=events;self.f=End(events,'q.f');self.s=End(events,'q.s');self.closed=False
    def cmd(self,name,**kw):self.events.append('q.'+name);return dict(running=False)
    def close(self):self.closed=True;self.events.append('q.close')
class Command:
    def __init__(self,claim,events,fail=False):self.claim=claim;self.events=events;self.fail=fail
    def __call__(self,cmd,**kw):
        self.events.append(cmd[0])
        if cmd[0]=='systemd-run':
            assert self.claim.exists(), 'command before durable claim'
            assert json.loads(self.claim.read_text())['receipt_sha256']==w.DIGEST
            self.events.append('command_after_claim')
            if self.fail:raise OSError('fixture command interrupted')
            return completed(cmd)
        if cmd[0]=='systemctl':return completed(cmd,'InvocationID='+'a'*32+'\nControlGroup=/fixture\nRestart=no\n')
        if cmd[0]=='journalctl':return completed(cmd,json.dumps(dict(_SYSTEMD_USER_UNIT=LEASE['unit'],MESSAGE='fixture journal'))+'\n')
        raise AssertionError('unexpected external command '+repr(cmd))

def header():
    b=bytearray(e.XBE.read_bytes()[:0x178])
    for off,key in ((0x128,a.loader.RETAIL_EP_KEY),(0x158,a.loader.RETAIL_THUNK_KEY)):
        struct.pack_into('<I',b,off,struct.unpack_from('<I',b,off)[0]^key)
    return bytes(b)

class EntryR:
    def __init__(self,wrong_header=False,wrong_target=False):
        self.pc=a.DISPATCH;self.calls=[];self.active=set();self.closed=False
        self.h=bytearray(header());self.wrong_target=wrong_target
        if wrong_header:self.h[0x110]^=1
    def regs(self):return dict(eip=self.pc,esp=0x700000,eax=0,ecx=0,edx=0,esi=0,ebp=0)
    def read(self,addr,n):
        self.calls.append(('read',addr,n))
        pin=a.kernel_dispatch_pin()
        if pin['address']<=addr and addr+n<=pin['address']+len(bytes.fromhex(pin['bytes'])):
            off=addr-pin['address'];return bytes.fromhex(pin['bytes'])[off:off+n]
        if 0x10000<=addr and addr+n<=0x10178:return bytes(self.h[addr-0x10000:addr-0x10000+n])
        out=a.loader.Pins().read(addr,n)
        if self.wrong_target and addr==next(iter(a.loader.HOOK_SITES.values()))[0]:return bytes([out[0]^1])+out[1:]
        return out
    def bp(self,addr,insert=True):
        self.calls.append(('bp',addr,insert))
        if insert:self.active.add(addr)
        else:self.active.discard(addr)
    def step(self):self.calls.append(('step',));self.pc=0x2da9de;return 'T05'
    def close(self):self.closed=True

def snapshot(pc,**regs):
    g=dict(eip=pc,esp=0x700000,eax=0,ecx=0x1234,edx=0,esi=0,ebp=0);g.update(regs)
    return dict(regs=g,memory=[dict(address=0x4908b0,hex=bytes(0x84).hex()),dict(address=0x700000,hex=bytes(64).hex())])

def observe_fixture(out,fault):
    stops=[dict(why='T05',snapshot=snapshot(0x416568))] if fault else []
    r=e.Fixture(dict(identity=IDENT,stops=stops),PLAN)
    with contextlib.closing(e.Journal(out)) as j:
        result=e.observe(r,PLAN,IDENT,IDENT,j,seconds=1,max_stops=4)
    assert not r.active
    return result,r

class Clock:
    def __init__(self):self.now=0
    def __call__(self):self.now+=.02;return self.now

class CaptureR(EntryR):
    """Synthetic external RSP memory/events, using real frozen instruction pins."""
    def __init__(self,**kw):
        super().__init__(**kw);self.mode='entry';self.index=0;self.sequence=0
        self.blob=bytearray(LAYOUT['values']['module_size']);self.commands=[]
        struct.pack_into('<4I',self.blob,LAYOUT['values']['vh'],0x4a414b31,1,1,1)
    def regs(self):
        return dict(eip=self.pc,esp=0x700000,eax=0,ecx=0x1234,edx=0,esi=0,ebp=0)
    def cmd(self,c):
        self.commands.append(c)
        if c[0]=='Z':self.active.add(c[1:])
        elif c[0]=='z':self.active.discard(c[1:])
        else:raise AssertionError('unexpected RSP operation '+c)
        return 'OK'
    def continue_wait(self,timeout):
        if self.mode=='fault':self.pc=0x416568;return 'T05'
        if self.mode=='observe':raise TimeoutError('synthetic paused timeout')
        self.index+=1;v=LAYOUT['values'];base=IDENT['base']
        if self.index==1:
            self.sequence+=1;head=self.sequence
            struct.pack_into('<I',self.blob,v['ring_head'],head)
            off=v['ring']+((head-1)%v['ring_cap'])*v['evt_size']
            struct.pack_into('<I',self.blob,off,8);struct.pack_into('<I',self.blob,off+20,3)
            self.blob[off+v['evt_data']:off+v['evt_data']+3]=b'\x20\x00\x01'
            struct.pack_into('<I',self.blob,v['gip_reports'],head)
            struct.pack_into('<I',self.blob,v['gip_valid'],1);self.blob[v['port_valid']]=1
            self.blob[v['gamepad']:v['gamepad']+18]=bytes(range(18))
            self.pc=base+0x3000;return 'T05watch:'+format(IDENT['module']+v['ring_head'],'x')+';'
        if self.index==2:self.pc=base+PLAN['symbols']['ogx_XInputGetState'];return 'T05'
        if self.index==3:
            struct.pack_into('<I',self.blob,v['served'],self.sequence)
            struct.pack_into('<I',self.blob,v['served_seq'],self.sequence)
            self.pc=base+self.return_offset;return 'T05'
        self.pc=0x2da9de+self.sequence
        raise TimeoutError('synthetic paused timeout')
    @property
    def return_offset(self):return next(k for k in PLAN['module'] if k>PLAN['symbols']['ogx_XInputGetState']+32)
    def read(self,addr,n):
        v=LAYOUT['values'];base=IDENT['base'];module=IDENT['module']
        if self.mode in ('observe','fault'):
            if base<=addr and addr+n<=base+len(bytes.fromhex(PLAN['text'])):return bytes.fromhex(PLAN['text'])[addr-base:addr-base+n]
            if 0x412000<=addr and addr+n<=0x41c000:return e.DUMP.read_bytes()[addr-0x412000:addr-0x412000+n]
            if addr==0x4908b0:return bytes(n)
            if addr==0x700000:return bytes(n)
        if self.mode=='capture':
            if module<=addr and addr+n<=module+len(self.blob):return bytes(self.blob[addr-module:addr-module+n])
            if addr==0x700000:return struct.pack('<4I',base+self.return_offset,module+v['present'],module+v['vh'],0x710000)[:n]
            if addr==module+v['vh']:return struct.pack('<4I',0x4a414b31,1,1,1)[:n]
            if addr==0x710000:return (struct.pack('<I',self.sequence)+bytes(range(18)))[:n]
            if base<=addr and addr+n<=base+len(bytes.fromhex(PLAN['text'])):return bytes.fromhex(PLAN['text'])[addr-base:addr-base+n]
            if 0x2da900<=addr<=0x2daa00:return b'\x90'*n
        return super().read(addr,n)
    def step(self):
        if self.mode=='entry':return super().step()
        self.pc+=1;return 'T05'
    def raw_regs(self):
        names='eax ecx edx ebx esp ebp esi edi eip eflags cs ss ds es fs gs'.split()
        g=self.regs();return struct.pack('<16I',*(g.get(k,0) for k in names)).hex()
    def target_xml(self,annex='target.xml'):
        names='eax ecx edx ebx esp ebp esi edi eip eflags cs ss ds es fs gs'.split()
        return '<target><feature>'+''.join('<reg name="'+k+'" bitsize="32"/>' for k in names)+'</feature></target>'

class Effects:
    """External lifecycle fixture; production adapter/decoder remain real."""
    def __init__(self,out,mode='fault'):
        self.out=out;out.mkdir();self.mode=mode;self.events=[];self.q=None;self.r=None;self.result=None
        self.claim=out/'fixture-claim.json'
    def launch(self):
        return w.launch(LEASE,ENV,gates=lambda l,x:dict(fixture=True),
            bind=lambda l:w.authority(l,canonical=CANON),run=Command(self.claim,self.events),claim_path=self.claim,output=self.out)
    def discover(self,handle):
        if self.mode=='early_exit':return None
        return dict(IDENT)
    def authenticate(self,ident,handle):
        if self.mode=='unidentified':raise RuntimeError('surviving unidentified process')
    def open_q(self):self.q=Q(self.events);return self.q
    def parity(self,ident,handle):
        if self.mode=='parity':raise RuntimeError('unknown hardware parity')
    def open_r(self,q,ident):
        if self.mode=='rsp_open':raise OSError('second client failed')
        self.r=CaptureR(wrong_header=self.mode=='wrong_title');return self.r
    def load_title(self,q,r,ident):a.arm_load_hold(r);a.dispatch_entry(r,'not TU')
    def install(self,q,r,ident):self.events.append('external_module_install')
    def observe(self,q,r,ident):
        r.mode='fault' if self.mode=='fault' else 'observe'
        with contextlib.closing(e.Journal(self.out/'trace.jsonl')) as journal:
            result=e.observe(r,PLAN,ident,ident,journal,seconds=1,max_stops=4)
        assert not r.active
        return result
    def capture(self,q,r,ident,handle):
        self.live=f.LiveEffects.__new__(f.LiveEffects)
        live=self.live;live.layout=LAYOUT;live.plan=PLAN;live.lease=LEASE
        cap=self.out/f.OUT;cap.mkdir(parents=True);ui_events=[]
        def ui(*args):
            ui_events.append(args)
            if args[0]=='shot':(cap/args[1]).write_bytes(b'FIXTURE-PIXELS-'+str(len(ui_events)).encode())
        live.ui=ui;r.mode='capture'
        original=live.capture_interval
        def interval(seconds):
            r.index=0
            return original(seconds)
        live.capture_interval=interval
        with patch.object(f,'R',self.out),patch.object(a,'check_native',return_value=ident),patch.object(f.time,'monotonic',new=Clock()):
            offer=live.capture(q,r,ident,handle)
        rows=[json.loads(x) for x in (cap/'capture.jsonl').read_text().splitlines()]
        decoded=[event for row in rows for event in row.get('decoded',{}).get('events',[])]
        assert len([x for x in decoded if x['event']=='raw_report'])==3,'first interval raw report lost'
        assert len([x for x in decoded if x['event']=='served_slot'])==3,'actual returned virtual packets absent'
        assert ('key','Down','Up') in ui_events,'visible-action exercise absent'
        return offer
    def accept(self,offer):
        if self.mode=='refused':return None
        accepted=dict(offer,offer_sha256=e.sha(json.dumps(offer,sort_keys=True).encode()),accepted=True,exclusive=True,
                      responsive_menu_confirmed=True)
        if self.mode=='stale_takeover':accepted['identity']=dict(offer['identity'],start_ticks=999)
        return accepted
    def seal(self,offer):self.live.seal(offer);self.events.append('capture.seal')
    def release(self,offer):
        assert self.r.closed and self.q.closed and self.q.f.closed and self.q.s.closed
        def save(name,obj):
            path=self.out/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(obj)+'\n');return obj
        with patch.object(a,'save',side_effect=save):self.live.release(offer)
        self.events.append('release')
    def confirm(self,offer):
        digest=e.sha(json.dumps(offer,sort_keys=True).encode());checkpoint=self.live.checkpoint
        q2=Q(self.events);r2=CaptureR();r2.mode='capture';r2.blob=bytearray(self.r.blob);r2.sequence=self.r.sequence
        parent=f.LiveEffects.__new__(f.LiveEffects);parent.lease=LEASE;parent.layout=LAYOUT;parent.plan=PLAN
        parent.endpoint=lambda *args,**kw:'external fixture endpoint authenticated'
        state=dict(owner_hold=False,runtime_binding=dict(takeover=self.accept(offer),capture_continuity=dict(offer_sha256=digest,identity=offer['identity'],exclusive=True)))
        try:
            with patch.object(f,'R',self.out),patch.object(f,'canonical',return_value=state),patch.object(a,'check_native',return_value=offer['identity']),patch.object(f.time,'monotonic',new=Clock()):
                parent.continue_after_takeover(offer,checkpoint,q2,r2)
                self.live.confirm(offer)
            rows=[json.loads(x) for x in (self.out/f.OUT/'capture.jsonl').read_text().splitlines()]
            self.assert_continuity=any(ev['event']=='raw_report' and ev['ring_index']==checkpoint['last_ring_head']
                for row in rows if row['seq']>checkpoint['seq'] for ev in row.get('decoded',{}).get('events',[]))
            assert self.assert_continuity,'parent did not continue raw decoder at exact outgoing cursor'
        finally:
            if getattr(parent,'capture_j',None) is not None:parent.capture_j.close()
            r2.close();a.close_q(q2)
        self.events.append('parent.continuity')
    def reauthenticate(self,ident):self.events.append('reauthenticate')
    def context(self,r):self.events.append('context')
    def verify_release(self):return dict(released=self.mode!='unidentified',processes=[dict(pid=123)] if self.mode=='unidentified' else [])
    def record(self,result):
        if hasattr(self,'live') and self.live.capture_j is not None:self.live.capture_j.close()
        self.result=result;isolated_save(str(self.out.relative_to(RUN))+'/result.json',dict(result,events=self.events))

class ChangedPaths(unittest.TestCase):
    def setUp(self):
        self.out=RUN/self._testMethodName;self.out.mkdir()
        self.guards=contextlib.ExitStack()
        self.guards.enter_context(patch.dict(os.environ,HERMES_SESSION_ID=FIXTURE_SESSION))
        # No real subprocess/socket/guest operation can slip through a fixture.
        self.guards.enter_context(patch('subprocess.run',side_effect=AssertionError('unexpected real process')))
        self.guards.enter_context(patch('socket.socket',side_effect=AssertionError('unexpected real socket')))
        self.guards.enter_context(patch.object(a,'save',side_effect=isolated_save))
        self.addCleanup(self.guards.close)
    def tx(self,**kw):
        claim=self.out/'claim.json';events=[]
        opts=dict(gates=lambda l,x:dict(fixture=True),bind=lambda l:w.authority(l,canonical=CANON),
                  run=Command(claim,events),claim_path=claim,output=self.out)
        opts.update(kw);return w.launch(LEASE,ENV,**opts),events
    def test_independent_base_wrong(self):
        pins=p.title_attestation();bad=copy.deepcopy(pins);path=next(iter(pins));bad[path]['sha256']='0'*64
        with self.assertRaisesRegex(e.Refusal,'path-specific'):p.verify_titles(bad,pins)
    def test_independent_tu_wrong(self):
        pins=p.title_attestation();bad=copy.deepcopy(pins);path=list(pins)[1];bad[path]['certificate_version']=3
        with self.assertRaisesRegex(e.Refusal,'path-specific'):p.verify_titles(bad,pins)
    def test_swapped_paths(self):
        pins=p.title_attestation();keys=list(pins);bad={keys[0]:pins[keys[1]],keys[1]:pins[keys[0]]}
        with self.assertRaisesRegex(e.Refusal,'path-specific'):p.verify_titles(bad,pins)
    def test_distinct_title_positive(self):p.verify_titles(p.title_attestation(),p.title_attestation())
    def test_stale_ownership_no_claim(self):
        stale=copy.deepcopy(CANON);stale['runtime_binding']['session']='exited-session'
        with self.assertRaises(ValueError):self.tx(bind=lambda l:w.authority(l,canonical=stale))
        self.assertFalse((self.out/'claim.json').exists())
    def test_hold_no_claim(self):
        stale=copy.deepcopy(CANON);stale['owner_hold']=True
        with self.assertRaises(ValueError):self.tx(bind=lambda l:w.authority(l,canonical=stale))
        self.assertFalse((self.out/'claim.json').exists())
    def test_fresh_rebind_after_gates(self):
        calls=[]
        def bind(l):
            calls.append('bind')
            if len(calls)>1:raise ValueError('owner changed during gates')
            return w.authority(l,canonical=CANON)
        with self.assertRaisesRegex(ValueError,'owner changed'):self.tx(bind=bind)
        self.assertFalse((self.out/'claim.json').exists())
    def test_claim_before_exact_one_command(self):
        handle,events=self.tx()
        self.assertEqual(events.count('systemd-run'),1);self.assertIn('command_after_claim',events)
        self.assertEqual(handle['command'],w.command(LEASE,ENV));self.assertEqual(handle['invocation_id'],'a'*32)
        self.assertFalse(handle['native_ready'])
    def test_duplicate_claim(self):
        self.tx()
        with self.assertRaises(FileExistsError):self.tx()
    def test_interrupted_empty_claim(self):
        (self.out/'claim.json').touch()
        with self.assertRaises(FileExistsError):self.tx()
        self.assertEqual((self.out/'claim.json').stat().st_size,0)
    def test_interrupted_command_recorded_spent(self):
        claim=self.out/'claim.json';events=[]
        with self.assertRaisesRegex(OSError,'interrupted'):self.tx(run=Command(claim,events,fail=True))
        outcome=json.loads((self.out/'launch-handle.json').read_text())
        self.assertIn('error',outcome);self.assertTrue(claim.exists())
        with self.assertRaises(FileExistsError):self.tx()
    def test_bad_live_header_before_addresses(self):
        r=EntryR(wrong_header=True);a.arm_load_hold(r)
        with self.assertRaises(Exception):a.dispatch_entry(r,'base')
        self.assertFalse(any(x[0]=='read' and 0x20000<=x[1]<0x80000000 for x in r.calls))
        self.assertFalse(any(x[0]=='step' for x in r.calls))
    def test_bad_original_bytes_before_step(self):
        r=EntryR(wrong_target=True);a.arm_load_hold(r)
        with self.assertRaisesRegex(e.Refusal,'original target'):a.dispatch_entry(r,'base')
        self.assertFalse(any(x[0]=='step' for x in r.calls))
    def test_generic_hold_then_authenticated_entry(self):
        r=EntryR();a.arm_load_hold(r);decision=a.dispatch_entry(r,'base')
        self.assertEqual(decision['kind'],'tu803');self.assertEqual(r.pc,0x2da9de)
        self.assertEqual([x[1] for x in r.calls if x[0]=='bp' and x[2]],[a.DISPATCH])
    def session(self,mode):
        fx=Effects(self.out/'effects',mode);result=s.run_session(fx)
        if fx.q:self.assertTrue(fx.q.closed and fx.q.f.closed and fx.q.s.closed)
        if fx.r:self.assertTrue(fx.r.closed)
        return fx,result
    def test_early_exit_cleanup(self):
        fx,result=self.session('early_exit');self.assertEqual(result['first_failed_link'],'native_discovery')
        self.assertTrue(result['remaining_resources']['released']);self.assertNotIn('q.quit',fx.events)
    def test_unidentified_survivor_no_blind_quit(self):
        fx,result=self.session('unidentified');self.assertFalse(result['remaining_resources']['released'])
        self.assertNotIn('q.quit',fx.events);self.assertFalse(result['title'])
    def test_parity_failure_closes_qmp_file_and_socket(self):
        fx,result=self.session('parity');self.assertEqual(result['first_failed_link'],'guarded_native_parity')
        self.assertIn('q.quit',fx.events)
    def test_second_client_failure_cleanup(self):
        fx,result=self.session('rsp_open');self.assertEqual(result['first_failed_link'],'rsp_open')
        self.assertIn('q.quit',fx.events)
    def test_wrong_live_title_session_cleanup(self):
        fx,result=self.session('wrong_title');self.assertEqual(result['first_failed_link'],'generic_load_hold')
        self.assertFalse(result['module']);self.assertIn('q.quit',fx.events)
    def test_decoded_bounded_fault(self):
        fx,result=self.session('fault');self.assertEqual(result['first_failed_link'],'ordered_observation')
        rows=[json.loads(x) for x in (fx.out/'trace.jsonl').read_text().splitlines()]
        self.assertTrue(any(x.get('pre_fault_hold') for x in rows));self.assertIn('q.quit',fx.events)
        self.assertNotIn('release',fx.events);self.assertFalse(result['healthy'])
    def test_responsive_capture_accepted_takeover(self):
        fx,result=self.session('accepted');self.assertIsNone(result['first_failed_link'])
        self.assertTrue(result['healthy']);self.assertNotIn('q.quit',fx.events)
        self.assertLess(fx.events.index('q.close'),fx.events.index('release'))
        self.assertLess(fx.events.index('release'),fx.events.index('parent.continuity'))
    def test_refused_takeover_not_healthy_accepted(self):
        fx,result=self.session('refused');self.assertIn('q.quit',fx.events)
        self.assertIsNone(result['first_failed_link']);self.assertTrue(result['capture_ready'])
        self.assertFalse(result['healthy']);self.assertNotIn('release',fx.events)
    def test_stale_takeover_not_healthy_accepted(self):
        fx,result=self.session('stale_takeover');self.assertEqual(result['first_failed_link'],'parent_takeover')
        self.assertFalse(result['healthy']);self.assertIn('q.quit',fx.events)
    def test_discovery_inactive_survivor_not_early_exit(self):
        fx=f.LiveEffects.__new__(f.LiveEffects);fx.lease=LEASE
        with patch.object(s,'owned_pid',return_value=None),patch.object(f,'run',return_value=completed([], 'ActiveState=inactive\n')),patch.object(p,'resources',return_value=dict(processes=[dict(pid=123)])):
            with self.assertRaisesRegex(e.Refusal,'unidentified'):fx.discover({})
    def test_constructor_partial_qmp_cleanup(self):
        refs=[]
        class Broken:
            def __init__(self,*args):
                self.f=End(refs,'file');self.s=End(refs,'socket');raise OSError('partial greeting')
        with patch.object(a,'QMP',Broken):
            with self.assertRaises(OSError):a.open_qmp('fixture')
        self.assertEqual(refs,['file.close','socket.close'])
    def test_constructor_partial_rsp_cleanup(self):
        refs=[]
        class Broken:
            def __init__(self,*args,**kw):self.s=End(refs,'socket');raise OSError('partial RSP')
        with patch.object(a,'RSP',Broken):
            with self.assertRaises(OSError):a.open_rsp(1242)
        self.assertEqual(refs,['socket.close'])
    def test_continuity_stale_seq_rejected(self):
        fx=f.LiveEffects.__new__(f.LiveEffects)
        offer=dict(identity=IDENT);digest=e.sha(json.dumps(offer,sort_keys=True).encode())
        cap=self.out/f.OUT/'capture.jsonl';cap.parent.mkdir(parents=True)
        cap.write_text(json.dumps(dict(seq=1,event='parent_continuity',identity=IDENT))+'\n')
        response=dict(owner_hold=False,runtime_binding=dict(capture_continuity=dict(offer_sha256=digest,identity=IDENT,exclusive=True)))
        with patch.object(f,'R',self.out),patch.object(f,'canonical',return_value=response):
            with self.assertRaisesRegex(e.Refusal,'continuity'):fx.confirm(offer)
    def test_observer_bad_full_header_no_address_use(self):
        r=CaptureR(wrong_header=True);r.mode='observe';r.pc=0x2da9de
        with contextlib.closing(e.Journal(self.out/'trace.jsonl')) as journal:
            with self.assertRaisesRegex(e.Refusal,'header'):e.observe(r,PLAN,IDENT,IDENT,journal)
        self.assertFalse(r.commands)
    def test_check_does_not_claim(self):
        with patch.object(w,'resolve_active_slot',return_value=type('FixtureSlot',(),{'lease':LEASE})()),patch.object(w,'environment',return_value=ENV),patch.object(w,'atomic_claim',side_effect=AssertionError('check claimed')),patch.object(sys,'argv',['parent_launch.py','--check']),patch('subprocess.run',return_value=completed([])):
            self.assertEqual(w.main(),0)
    def test_recorder_second_writer_refused(self):
        path=self.out/'capture.jsonl';journal=e.Journal(path,max_events=None)
        try:
            checkpoint=journal.emit('outgoing_checkpoint',last_ring_head=0)
            with self.assertRaises(BlockingIOError):e.Journal.resume(path,checkpoint)
        finally:journal.close()
    def test_decoder_ring_gap_refused(self):
        v=LAYOUT['values'];blob=bytearray(v['module_size']);struct.pack_into('<I',blob,v['ring_head'],v['ring_cap']+1)
        with self.assertRaisesRegex(e.Refusal,'overwritten'):e.CaptureDecoder(LAYOUT,head=0).decode(blob)

if __name__=='__main__':
    stream=io.StringIO();suite=unittest.defaultTestLoader.loadTestsFromTestCase(ChangedPaths)
    result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
    paths=['parent_launch.py']+['tools/'+n for n in ('runtime_session.py','runtime_effects.py','live_adapter.py','live_preflight.py','enum_watch.py','capture_layout.py','ui.py','test_continuation.py')]
    report=dict(session=os.environ.get('HERMES_SESSION_ID'),all_passed=result.wasSuccessful(),tests_run=result.testsRun,
        failures=[dict(test=str(t),traceback=tb) for t,tb in result.failures],errors=[dict(test=str(t),traceback=tb) for t,tb in result.errors],
        command=[sys.executable,'-B',str(Path(__file__).resolve())],exit_code=0 if result.wasSuccessful() else 1,
        production_hashes={n:e.sha((ROOT/n).read_bytes()) for n in paths},fixture_only=True,real_claim_used=False,evidence=str(RUN))
    (RUN/'unittest.log').write_text(stream.getvalue());(RUN/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    (TESTS/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    print(stream.getvalue());print(json.dumps(report,indent=2));raise SystemExit(report['exit_code'])
