#!/usr/bin/env python3
"""Post-entry47 adapters: hermetic fixtures only, no real spend or guest."""
import sys
sys.dont_write_bytecode=True
import copy
import io
import json
import os
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch
import test_continuation as t
import recovery as rec
import live_adapter as a
import parent_launch as w
import enum_watch as e
LEASE=w.receipt47()

class Node:
    def __init__(self,path,data):self.path=path;self.data=data
    def __truediv__(self,key):return Node(self.path+'/'+str(key),self.data)
    def __str__(self):return self.path
    def read_text(self):return self.data[self.path]
    def read_bytes(self):return self.data[self.path].encode()

class FreshTests(t.ChangedPaths):
    def setUp(self):
        super().setUp();self.guards.enter_context(patch.object(a,'METADATA',None))
        self.lease=copy.deepcopy(LEASE);self.claim=self.out/'fixture-claim.json';self.lease['claim_path']=str(self.claim)
        self.payload=self.out/'fixture.py';self.payload.write_text('# isolated source fixture\n')
        self.green=self.out/'green.json';self.green.write_text(json.dumps(dict(all_passed=True,exit_code=0,fixture=True)))
        self.manifest=self.out/'SOURCE-MANIFEST.json'
        manifest=dict(lease_sha256=w.DIGEST47,files={str(self.payload):e.sha(self.payload.read_bytes())},
                      test_receipts={str(self.green):e.sha(self.green.read_bytes())})
        self.manifest.write_text(json.dumps(manifest))
        self.c=copy.deepcopy(t.CANON)
        self.c['runtime_binding'].update(state='verified',mode='post_entry47_fresh_bounded_launch',
            lease_path=str(w.FRESH/'PARENT-RUNTIME-LEASE.json'),lease_sha256=w.DIGEST47,
            claim_path=str(self.claim),unit=LEASE['unit'],historical_launch_commands=2,cumulative_ceiling=3,
            remaining_commands=1,new_launch_authorized=True,process='isolated-worker',pid=123,
            read_only_admin_metadata_allowed=True,
            source_confirmation=dict(state='verified',lease_sha256=w.DIGEST47,manifest_sha256=e.sha(self.manifest.read_bytes()),
              session=t.FIXTURE_SESSION,files=manifest['files'],route_proof=dict(session=t.FIXTURE_SESSION,provider='openai-codex',
                 model='gpt-6.1-sol',billing_mode='subscription_included',api_call_count=1,input_tokens=1)))
        source=w.source_confirmation47
        self.guards.enter_context(patch.object(w,'source_confirmation47',side_effect=lambda b:source(b,manifest_path=self.manifest)))
        self.events=[]
    def invoke(self):
        def run(cmd,**kw):
            self.events.append(cmd)
            if cmd[0]=='systemd-run':
                assert self.claim.exists();assert json.loads(self.claim.read_text())['receipt_sha256']==w.DIGEST47
                return t.completed(cmd)
            if cmd[0]=='systemctl':return t.completed(cmd,'InvocationID='+'a'*32+'\nControlGroup=/fixture/'+LEASE['unit']+'\nRestart=no\n')
            if cmd[0]=='journalctl':return t.completed(cmd)
            raise AssertionError('unsubstituted command')
        return w.launch(self.lease,t.ENV,gates=lambda l,x:dict(fixture=True),run=run,
            bind=lambda l:w.authority47(l,canonical=self.c),claim_path=self.claim,output=self.out,digest=w.DIGEST47)
    def assert_no_spend(self):self.assertFalse(self.claim.exists());self.assertFalse(self.events)
    def test_fresh_missing_parent_confirmation_no_claim_or_command(self):
        self.c['runtime_binding']['source_confirmation']=None
        with self.assertRaisesRegex(ValueError,'confirmation'):self.invoke()
        self.assert_no_spend()
    def test_fresh_wrong_confirmation_digest_no_claim_or_command(self):
        self.c['runtime_binding']['source_confirmation']['lease_sha256']=w.DIGEST
        with self.assertRaisesRegex(ValueError,'receipt'):self.invoke()
        self.assert_no_spend()
    def test_fresh_stale_source_no_claim_or_command(self):
        self.payload.write_text('# changed after parent confirmation\n')
        with self.assertRaisesRegex(ValueError,'changed'):self.invoke()
        self.assert_no_spend()
    def test_fresh_stale_manifest_no_claim_or_command(self):
        self.manifest.write_text(self.manifest.read_text()+'\n')
        with self.assertRaisesRegex(ValueError,'stale'):self.invoke()
        self.assert_no_spend()
    def test_fresh_wrong_confirmation_session_no_spend(self):
        self.c['runtime_binding']['source_confirmation']['session']='exited-session'
        with self.assertRaises(ValueError):self.invoke()
        self.assert_no_spend()
    def test_fresh_prepare_only_never_claims(self):
        self.c['runtime_binding'].update(state='verified_prepare_only',new_launch_authorized=False)
        w.authority47(self.lease,canonical=self.c,require_confirmation=False)
        with self.assertRaisesRegex(ValueError,'PREPARE_ONLY'):self.invoke()
        self.assert_no_spend()
    def test_fresh_actual_route_proof_required(self):
        self.c['runtime_binding']['source_confirmation']['route_proof']['api_call_count']=0
        with self.assertRaisesRegex(ValueError,'token-bearing'):self.invoke()
        self.assert_no_spend()
    def test_fresh_one_durable_claim_before_exact_command(self):
        result=self.invoke()
        self.assertEqual(result['receipt_sha256'],w.DIGEST47)
        self.assertEqual(result['unit'],'ampjack-parent47-devkit.service')
        self.assertEqual(result['command'],w.command(self.lease,t.ENV))
        self.assertEqual(sum(cmd[0]=='systemd-run' for cmd in self.events),1)
    def test_fresh_duplicate_claim_is_final(self):
        self.invoke();count=len(self.events)
        with self.assertRaises(FileExistsError):self.invoke()
        self.assertEqual(len(self.events),count)
    def test_fresh_ambiguous_empty_claim_is_final(self):
        self.claim.touch()
        with self.assertRaises(FileExistsError):self.invoke()
        self.assertFalse(self.events)
    def test_fresh_interrupted_durable_claim_is_final(self):
        with patch.object(w.os,'fsync',side_effect=OSError('fixture fsync interruption')):
            with self.assertRaisesRegex(OSError,'interruption'):self.invoke()
        self.assertTrue(self.claim.exists());self.assertFalse(self.events)
        with self.assertRaises(FileExistsError):self.invoke()
    def discovered(self):
        self.invoke()
        props=dict(Id=LEASE['unit'],InvocationID='a'*32,ControlGroup='/fixture/'+LEASE['unit'],Restart='no',MainPID='9100',ActiveState='active')
        native=dict(pid=9101,start_ticks=123456,boot_id='new-fixture-host-boot',cgroup='0::'+props['ControlGroup'],
           argv=[str(w.GUEST/'xemu'),'-config_path',str(w.GUEST/'xemu.toml'),'-qmp','unix:'+LEASE['socket']+',server=on,wait=off'])
        handle=dict(unit=LEASE['unit'],invocation_id='a'*32,claim_sha256=e.sha(self.claim.read_bytes()))
        return props,native,handle
    def test_fresh_candidate_wrong_unit_before_privilege(self):
        props,row,handle=self.discovered();props['Id']='old-unit.service'
        with self.assertRaisesRegex(e.Refusal,'unit'):rec.fresh_candidate(self.lease,handle,props,[row],row['boot_id'])
    def test_fresh_candidate_wrong_invocation_before_privilege(self):
        props,row,handle=self.discovered();props['InvocationID']='b'*32
        with self.assertRaisesRegex(e.Refusal,'invocation'):rec.fresh_candidate(self.lease,handle,props,[row],row['boot_id'])
    def test_fresh_candidate_stale_cgroup_before_privilege(self):
        props,row,handle=self.discovered();row['cgroup']='0::/old/ampjack-parent45-devkit.service'
        with self.assertRaisesRegex(e.Refusal,'cgroup'):rec.fresh_candidate(self.lease,handle,props,[row],row['boot_id'])
    def test_fresh_candidate_stale_host_before_privilege(self):
        props,row,handle=self.discovered()
        with self.assertRaisesRegex(e.Refusal,'boot'):rec.fresh_candidate(self.lease,handle,props,[row],'different-host-boot')
    def public_data(self,props,row):
        return {'/proc/sys/kernel/random/boot_id':row['boot_id'],
          '/sys/fs/cgroup'+props['ControlGroup']+'/cgroup.procs':'9100 9101',
          '/proc/9101/stat':'1 (xemu) '+' '.join(['0']*19+[str(row['start_ticks'])]),
          '/proc/9100/stat':'1 (python) '+' '.join(['0']*19+['123450']),
          '/proc/9101/cgroup':row['cgroup'],'/proc/9100/cgroup':row['cgroup'],
          '/proc/9101/cmdline':'\0'.join(row['argv'])+'\0',
          '/proc/9100/cmdline':'/usr/bin/python3\0-B\0'+str(w.GUEST/'.start-xemu.py')+'\0',
          '/proc/net/unix':'000: 00000002 00000000 00010000 0001 01 999100 '+LEASE['socket']}
    def process(self,props,root_reads):
        def run(cmd,**kw):
            if cmd[0]=='systemctl':return t.completed(cmd,'\n'.join(k+'='+v for k,v in props.items()))
            if cmd[:3]==['sudo','-n','--']:
                root_reads.append(cmd)
                if cmd[3]=='/usr/bin/readlink':return subprocess.CompletedProcess(cmd,0,(str(w.GUEST/'xemu')+'\n').encode(),b'')
                if cmd[3]=='/usr/bin/sha256sum':return subprocess.CompletedProcess(cmd,0,(LEASE['xemu_sha256']+'  /proc/9101/exe\n').encode(),b'')
                return subprocess.CompletedProcess(cmd,0,b'fixture metadata',b'')
            raise AssertionError('unexpected external effect '+repr(cmd))
        return run
    def test_fresh_production_first_discovery_then_privileged_reads(self):
        props,row,handle=self.discovered();data=self.public_data(props,row);root_reads=[]
        original_path=Path
        def path(value):
            value=str(value)
            return Node(value,data) if value.startswith(('/proc','/sys/fs/cgroup')) else original_path(value)
        fx=rec.FreshEffects.__new__(rec.FreshEffects);fx.lease=self.lease
        fx.slot=type('FixtureSlot',(),{'authority':lambda slot,lease,**kw:w.authority47(lease,**kw)})()
        with patch.object(rec,'Path',side_effect=path),patch.object(rec.f,'canonical',return_value=self.c),patch('subprocess.run',side_effect=self.process(props,root_reads)):
            ident=fx.discover(handle)
        self.assertEqual(ident['pid'],9101);self.assertEqual(ident['start_ticks'],123456)
        self.assertNotEqual(ident['pid'],rec.PIN['pid']);self.assertEqual(fx.pin['unit'],LEASE['unit'])
        self.assertEqual(len(root_reads),2)
        self.assertTrue(all('/proc/9101/exe'==cmd[-1] for cmd in root_reads))
    def guarded(self,mutate=None):
        props,row,handle=self.discovered();data=self.public_data(props,row);root_reads=[]
        pin=dict(pid=row['pid'],start_ticks=row['start_ticks'],boot_id=row['boot_id'],unit=LEASE['unit'],
                 cgroup=props['ControlGroup'],invocation=handle['invocation_id'],claim_sha256=handle['claim_sha256'])
        if mutate:mutate(props,row,data)
        meta=rec.ReadOnlyMetadata(pin,binding_check=lambda c,session,p:w.authority47(self.lease,canonical=c,session=session,consumed=True),claim_path=self.claim,lease=self.lease)
        self.guards.enter_context(patch.object(rec,'Path',side_effect=lambda value:Node(str(value),data)))
        self.guards.enter_context(patch.object(rec.f,'canonical',return_value=self.c))
        self.guards.enter_context(patch('subprocess.run',side_effect=self.process(props,root_reads)))
        return meta,root_reads
    def test_fresh_read_time_reused_pid_start_refuses_before_sudo(self):
        meta,root_reads=self.guarded(lambda props,row,data:data.update({'/proc/9101/stat':'1 (reused) '+' '.join(['0']*19+['999999'])}))
        with self.assertRaisesRegex(e.Refusal,'start changed'):meta.sudo_read(9101,['/usr/bin/cat','/proc/9101/maps'])
        self.assertFalse(root_reads)
    def test_fresh_read_time_wrong_unit_refuses_before_sudo(self):
        meta,root_reads=self.guarded(lambda props,row,data:props.update(InvocationID='b'*32))
        with self.assertRaisesRegex(e.Refusal,'invocation changed'):meta.sudo_read(9101,['/usr/bin/cat','/proc/9101/maps'])
        self.assertFalse(root_reads)
    def test_fresh_read_time_wrong_pid_refuses_before_sudo(self):
        meta,root_reads=self.guarded()
        with self.assertRaisesRegex(e.Refusal,'wrong PID'):meta.sudo_read(9102,['/usr/bin/cat','/proc/9102/maps'])
        self.assertFalse(root_reads)
    def test_fresh_default_session_selects_fresh_adapter(self):
        import runtime_session
        marker=object()
        with patch.object(sys,'argv',['runtime_session.py']),patch.object(rec,'FreshEffects',return_value=marker),patch.object(runtime_session,'run_session',return_value=dict(healthy=True)) as run:
            self.assertEqual(runtime_session.main(),0);self.assertIs(run.call_args.args[0],marker)
    def test_fresh_ui_cannot_overwrite_recovery_evidence(self):
        fx=rec.FreshEffects.__new__(rec.FreshEffects);fx.pin=dict(pid=9101);fx.evidence_root=w.FRESH
        fx.env=t.ENV;fx.window='fixture-window'
        class Metadata:
            def guard(self,pid):assert pid==9101
        fx.meta=Metadata()
        with patch.object(rec.f,'OUT','post-entry-47/live/'),patch('subprocess.check_output',return_value='9101'),patch('subprocess.run',return_value=t.completed([])) as run:
            fx.ui('shot','fresh-fixture.png')
        self.assertEqual(run.call_args.args[0][-1],str(w.FRESH/'live/fresh-fixture.png'))
    def test_fresh_dashboard_review_uses_new_evidence_only(self):
        fx=rec.FreshEffects.__new__(rec.FreshEffects);fx.evidence_root=self.out/'post-entry-47';fx.window='fixture'
        image=fx.evidence_root/'live/dashboard-before.png';image.parent.mkdir(parents=True);image.write_bytes(b'fixture screenshot')
        (fx.evidence_root/'navigation-reviewed.json').write_text(json.dumps(dict(sha256=e.sha(image.read_bytes()),native_pid=9101,start_ticks=123456,retail_parent_row_verified=True)))
        with patch.object(rec,'R',self.out),patch.object(rec.f,'OUT','post-entry-47/live/'),patch.object(a,'save') as save:
            fx.review_dashboard(dict(pid=9101,start_ticks=123456))
        self.assertEqual(save.call_args.args[0],'post-entry-47/live/dashboard-review-ready.json')

if __name__=='__main__':
    names=[n for n in FreshTests.__dict__ if n.startswith('test_fresh_')]
    stream=io.StringIO();result=unittest.TextTestRunner(stream=stream,verbosity=2).run(unittest.TestSuite(FreshTests(n) for n in names))
    report=dict(all_passed=result.wasSuccessful(),tests_run=result.testsRun,exit_code=0 if result.wasSuccessful() else 1,fixture_only=True,
        failures=[dict(test=str(x),traceback=tb) for x,tb in result.failures],errors=[dict(test=str(x),traceback=tb) for x,tb in result.errors],
        production_hashes={str(p.relative_to(t.ROOT)):e.sha(p.read_bytes()) for p in (Path(__file__),t.ROOT/'parent_launch.py',t.ROOT/'tools/recovery.py',t.ROOT/'tools/live_preflight.py',t.ROOT/'tools/runtime_session.py')},evidence=str(t.RUN))
    (t.RUN/'fresh.log').write_text(stream.getvalue());(t.RUN/'fresh-result.json').write_text(json.dumps(report,indent=2)+'\n')
    (t.TESTS/'fresh-result.json').write_text(json.dumps(report,indent=2)+'\n')
    print(stream.getvalue());print(json.dumps(report,indent=2));raise SystemExit(report['exit_code'])
