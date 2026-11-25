#!/usr/bin/env python3
"""Hermetic existing-boot recovery tests, no guest/privilege effects."""
import sys
sys.dont_write_bytecode=True
import copy
import io
import json
import os
from pathlib import Path
import struct
import subprocess
import unittest
from unittest.mock import patch
import test_continuation as t
import recovery as rec
import live_adapter as a
import runtime_session as s
import enum_watch as e

STATE=copy.deepcopy(t.CANON)
STATE['runtime_binding'].update(mode='existing_invocation_recovery_only',new_launch_authorized=False,remaining_commands=0,
    read_only_admin_metadata_allowed=True,native_pid=rec.PIN['pid'],native_start_ticks=rec.PIN['start_ticks'],
    invocation=rec.PIN['invocation'],host_boot=rec.PIN['boot_id'],claim_sha256=rec.PIN['claim_sha256'])

class Node:
    def __init__(self,path,data):self.path=path;self.data=data
    def __truediv__(self,name):return Node(self.path+'/'+str(name),self.data)
    def __str__(self):return self.path
    def read_text(self):return self.data[self.path]
    def read_bytes(self):raise PermissionError(13,'synthetic EACCES')

class RecoveryTests(t.ChangedPaths):
    # Only these additional methods are loaded below, not inherited repetitions.
    def guard_fixture(self,*,start=None,invocation=None):
        meta=rec.ReadOnlyMetadata();pid=rec.PIN['pid']
        data={'/proc/sys/kernel/random/boot_id':rec.PIN['boot_id'],
          f'/proc/{pid}/stat':'1 (xemu) '+' '.join(['0']*19+[str(start or rec.PIN['start_ticks'])]),
          f'/proc/{pid}/cgroup':'0::'+rec.PIN['cgroup']}
        cmdout='InvocationID='+(invocation or rec.PIN['invocation'])+'\nControlGroup='+rec.PIN['cgroup']+'\nRestart=no\n'
        stack=self.guards
        stack.enter_context(patch.object(rec.f,'canonical',return_value=copy.deepcopy(STATE)))
        stack.enter_context(patch.object(rec,'Path',side_effect=lambda x:Node(str(x),data)))
        stack.enter_context(patch('subprocess.run',return_value=t.completed([],cmdout)))
        return meta
    def test_recovery_binding_wrong_pid(self):
        bad=copy.deepcopy(STATE);bad['runtime_binding']['native_pid']+=1
        with self.assertRaisesRegex(e.Refusal,'binding'):rec.authorize(bad,t.FIXTURE_SESSION)
    def test_recovery_binding_wrong_invocation(self):
        bad=copy.deepcopy(STATE);bad['runtime_binding']['invocation']='b'*32
        with self.assertRaisesRegex(e.Refusal,'binding'):rec.authorize(bad,t.FIXTURE_SESSION)
    def test_recovery_guard_wrong_start_no_sudo(self):
        meta=self.guard_fixture(start=999)
        with self.assertRaisesRegex(e.Refusal,'start changed'):meta.sudo_read(rec.PIN['pid'],['/usr/bin/cat','never'])
    def test_recovery_guard_wrong_unit_no_sudo(self):
        meta=self.guard_fixture(invocation='b'*32)
        with self.assertRaisesRegex(e.Refusal,'invocation changed'):meta.sudo_read(rec.PIN['pid'],['/usr/bin/cat','never'])
    def test_recovery_guard_valid_public_rechecks(self):
        meta=self.guard_fixture();self.assertEqual(str(meta.guard(rec.PIN['pid'])),f"/proc/{rec.PIN['pid']}")
    def test_recovery_eacces_uses_exact_readonly_cat(self):
        meta=rec.ReadOnlyMetadata();calls=[]
        def process(cmd,**kwargs):calls.append(cmd);return subprocess.CompletedProcess(cmd,0,b'mapped SDL fixture',b'')
        with patch.object(meta,'guard',return_value=Node('/proc/'+str(rec.PIN['pid']),{})) as guard,patch('subprocess.run',side_effect=process):
            self.assertEqual(meta.read(rec.PIN['pid'],'maps'),b'mapped SDL fixture')
            self.assertEqual(calls,[['sudo','-n','--','/usr/bin/cat',f"/proc/{rec.PIN['pid']}/maps"]])
            self.assertEqual(guard.call_count,3)
    def test_recovery_environment_filtered_no_secret_output(self):
        meta=rec.ReadOnlyMetadata()
        with patch.object(meta,'guard',return_value=Node('/proc/'+str(rec.PIN['pid']),{})),patch.object(meta,'sudo_read',return_value=b'SECRET_TOKEN=must_not_escape\0DISPLAY=:2\0SDL_VIDEO_DRIVER=x11\0'):
            self.assertEqual(meta.read(rec.PIN['pid'],'environ'),b'DISPLAY=:2\0SDL_VIDEO_DRIVER=x11\0')
    def test_recovery_forbidden_proc_path_refused(self):
        with self.assertRaisesRegex(e.Refusal,'allowlist'):rec.ReadOnlyMetadata().read(rec.PIN['pid'],'mem')
    def test_recovery_monitor_peer_rejected_before_protocol(self):
        events=[]
        class Sock:
            def settimeout(self,x):pass
            def connect(self,x):events.append('connect')
            def getsockopt(self,*x):return struct.pack('3i',999,1000,1000)
            def makefile(self,*x,**kw):raise AssertionError('peer mismatch reached protocol')
            def close(self):events.append('close')
        with patch.object(a.socket,'socket',return_value=Sock()):
            with self.assertRaisesRegex(e.Refusal,'SO_PEERCRED'):a.open_qmp('fixture',expected_peer=(rec.PIN['pid'],1000,1000))
        self.assertEqual(events,['connect','close'])
    def test_recovery_existing_state_machine_never_launches_or_preflights(self):
        for mode in ('unidentified','parity','rsp_open','wrong_title','fault','refused','accepted'):
            with self.subTest(mode=mode):
                fx=t.Effects(self.out/mode,mode)
                fx.existing=lambda:(dict(invocation_id='a'*32),dict(t.IDENT))
                fx.launch=lambda:(_ for _ in ()).throw(AssertionError('existing mode launched'))
                with patch.object(t.w,'atomic_claim',side_effect=AssertionError('existing claimed')),patch.object(t.p,'stopped_gates',side_effect=AssertionError('offline disk preflight')):
                    result=s.run_session(fx,existing=True)
                self.assertFalse(result['command']);self.assertFalse(result['new_boot']);self.assertTrue(result['attach_existing'])
                self.assertFalse(fx.claim.exists())
                if mode=='accepted':self.assertTrue(result['healthy'])
                elif mode=='refused':self.assertIsNone(result['first_failed_link']);self.assertIn('q.quit',fx.events)
                else:self.assertIsNotNone(result['first_failed_link'])
                if fx.q:self.assertTrue(fx.q.f.closed and fx.q.s.closed)
    def test_recovery_production_entry_uses_sealed_preflight_no_disk(self):
        root=self.out/rec.R.name;root.mkdir();(root/'continuation-2/live').mkdir(parents=True)
        pre=dict(live_headers={'E:/TDATA/4d530064/$u/default.xbe':t.PLAN['live_header']})
        claim=dict(receipt_sha256=t.w.DIGEST,binding=dict(session=t.FIXTURE_SESSION),stopped_proof=pre)
        raw=json.dumps(claim).encode();digest=e.sha(raw);pin=dict(rec.PIN,claim_sha256=digest)
        (root/'runtime-claim.json').write_bytes(raw);(root/'continuation-2/preflight.json').write_text(json.dumps(pre))
        handle=dict(invocation_id=pin['invocation'],unit=pin['unit'],claim_sha256=digest)
        (root/'continuation-2/live/launch-handle.json').write_text(json.dumps(handle))
        state=copy.deepcopy(STATE);state['runtime_binding']['claim_sha256']=digest
        fx=rec.RecoveryEffects.__new__(rec.RecoveryEffects);fx.plan=t.PLAN
        class Metadata:
            def native(self,pid):return dict(t.IDENT)
        fx.meta=Metadata()
        with patch.object(rec,'R',root),patch.object(rec,'PIN',pin),patch.object(rec.f,'canonical',return_value=state),patch.object(rec,'authorize',side_effect=lambda c,x:rec.authorize_original(c,x,pin)),patch.object(t.p,'stopped_gates',side_effect=AssertionError('offline disk read')),patch.object(t.w,'launch',side_effect=AssertionError('relaunch')):
            got,ident=fx.existing()
        self.assertEqual(got,handle);self.assertEqual(fx.pre,pre)
    def test_recovery_cleanup_before_pair_open_authenticates_then_quits(self):
        fx=rec.RecoveryEffects.__new__(rec.RecoveryEffects);fx.q_attempted=False;fx.lease=t.LEASE
        events=[];q=t.Q(events)
        class Metadata:
            def native(self,pid):events.append('native_authenticated');return dict(t.IDENT)
        fx.meta=Metadata();fx.endpoint=lambda *args,**kw:events.append('endpoint_authenticated')
        fx.open_q=lambda:q;fx.reauthenticate=lambda ident:events.append('reauthenticated')
        result=fx.cleanup_if_unopened()
        self.assertTrue(result['authenticated']);self.assertLess(events.index('endpoint_authenticated'),events.index('q.quit'))
        self.assertTrue(q.f.closed and q.s.closed)
    def test_recovery_cleanup_does_not_retry_opened_pair(self):
        fx=rec.RecoveryEffects.__new__(rec.RecoveryEffects);fx.q_attempted=True
        fx.open_q=lambda:(_ for _ in ()).throw(AssertionError('second connection'))
        self.assertFalse(fx.cleanup_if_unopened()['attempted'])
    def test_recovery_native_metadata_integrates_with_adapter(self):
        class Metadata:
            def native(self,pid):return dict(t.IDENT,native_sha256=t.LEASE['xemu_sha256'],argv=['xemu','-config_path',t.LEASE['fresh_clone']+'/xemu.toml'])
        expected=Metadata().native(t.IDENT['pid'])
        with patch.object(a,'METADATA',Metadata()):self.assertEqual(a.check_native(expected,t.LEASE),expected)
    def test_recovery_successful_entry_removes_generic_breakpoint_once(self):
        class StrictRSP(t.EntryR):
            def bp(self,addr,insert=True):
                if not insert and addr not in self.active:raise RuntimeError('RSP z0 duplicate -> E22')
                return super().bp(addr,insert)
            def cont(self):pass
            def stop(self):return 'T05'
            def continue_wait(self,timeout):self.pc=a.DISPATCH;return 'T05'
        r=StrictRSP();fx=rec.f.LiveEffects.__new__(rec.f.LiveEffects)
        fx.pre=dict(live_headers={'E:/DEVKIT/Tools/Halo2/default.xbe':'not TU'})
        fx.ui=lambda *args:None
        with patch.object(rec.f.time,'sleep',return_value=None):fx.load_title(None,r,t.IDENT)
        self.assertEqual(r.pc,0x2da9de);self.assertFalse(r.active)
        self.assertEqual(len([x for x in r.calls if x[0]=='bp' and not x[2]]),1)

rec.authorize_original=rec.authorize
if __name__=='__main__':
    names=[n for n in RecoveryTests.__dict__ if n.startswith('test_recovery_')]
    suite=unittest.TestSuite(RecoveryTests(n) for n in names)
    stream=io.StringIO();result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
    report=dict(fixture_only=True,tests_run=result.testsRun,all_passed=result.wasSuccessful(),exit_code=0 if result.wasSuccessful() else 1,
        errors=[dict(test=str(x),traceback=tb) for x,tb in result.errors],failures=[dict(test=str(x),traceback=tb) for x,tb in result.failures],
        production_hashes={str(p.relative_to(t.ROOT)):e.sha(p.read_bytes()) for p in (Path(__file__),t.ROOT/'tools/recovery.py',t.ROOT/'tools/runtime_session.py',t.ROOT/'tools/live_adapter.py',t.ROOT/'tools/runtime_effects.py')})
    (t.RUN/'recovery-tests.log').write_text(stream.getvalue());(t.RUN/'recovery-result.json').write_text(json.dumps(report,indent=2)+'\n')
    (t.TESTS/'recovery-result.json').write_text(json.dumps(dict(report,evidence=str(t.RUN)),indent=2)+'\n')
    print(stream.getvalue());print(json.dumps(report,indent=2));raise SystemExit(report['exit_code'])
