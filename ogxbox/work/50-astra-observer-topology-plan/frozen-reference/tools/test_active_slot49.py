#!/usr/bin/env python3
"""Production active-slot selection/claim, isolated external effects only."""
import sys
sys.dont_write_bytecode=True
import contextlib
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import unittest
from typing import Any
from unittest.mock import patch
import test_continuation as t
import test_post_entry47 as old
import recovery as rec
import parent_launch as w
import live_adapter as a

REAL_ROOT=w.ROOT
RUN=REAL_ROOT/'post-entry-49/tests'/('slot-'+str(time.time_ns()))
RUN.mkdir(parents=True)
LEASE=json.loads((REAL_ROOT/'post-entry-49/PARENT-RUNTIME-LEASE.json').read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()

class SlotTests(unittest.TestCase):
    def setUp(self):
        self.out=RUN/self._testMethodName;self.root=self.out/REAL_ROOT.name;self.path=self.root/'post-entry-49';self.path.mkdir(parents=True)
        self.stack=contextlib.ExitStack();self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.dict(os.environ,HERMES_SESSION_ID=t.FIXTURE_SESSION))
        self.stack.enter_context(patch.object(w,'ROOT',self.root))
        self.stack.enter_context(patch('subprocess.run',side_effect=AssertionError('unsubstituted process')))
        self.stack.enter_context(patch('socket.socket',side_effect=AssertionError('unsubstituted socket')))
        self.previous=self.root/'post-entry-47';self.previous.mkdir()
        (self.previous/'runtime-claim.json').write_bytes(b'old spent immutable fixture claim')
        (self.previous/'PARENT-RUNTIME-LEASE.json').write_bytes(b'old fixture receipt')
        self.old_claim=(self.previous/'runtime-claim.json').read_bytes()
        self.lease=copy.deepcopy(LEASE)
        self.lease.update(work_root=str(self.root),slot_path=str(self.path),evidence_root=str(self.path),claim_path=str(self.path/'runtime-claim.json'))
        for key,name in (('previous_lease','PARENT-RUNTIME-LEASE.json'),('previous_claim','runtime-claim.json')):
            p=self.previous/name;self.lease[key]=dict(path=str(p),sha256=sha(p))
        self.receipt=self.path/'PARENT-RUNTIME-LEASE.json';self.receipt.write_text(json.dumps(self.lease));self.digest=sha(self.receipt)
        self.stack.enter_context(patch.object(w,'DIGEST49',self.digest))
        self.payload=self.path/'payload.py';self.payload.write_text('# isolated fixture only\n')
        self.green=self.path/'green.json';self.green.write_text(json.dumps(dict(all_passed=True,exit_code=0,fixture_only=True)))
        self.manifest=self.path/'SOURCE-MANIFEST.json';self.manifest.write_text(json.dumps(dict(lease_sha256=self.digest,files={str(self.payload):sha(self.payload)},test_receipts={str(self.green):sha(self.green)})))
        (self.path/'status.json').write_text('{}')
        self.c:dict[str,Any]=copy.deepcopy(t.CANON);self.b:dict[str,Any]=self.c['runtime_binding']
        self.b.update(state='verified',mode='post_entry49_fresh_bounded_launch',session=t.FIXTURE_SESSION,work_root=str(self.root),guest_root=str(w.GUEST),slot='post-entry-49',slot_path=str(self.path),evidence_root=str(self.path),lease_path=str(self.receipt),lease_sha256=self.digest,claim_path=str(self.path/'runtime-claim.json'),manifest_path=str(self.manifest),unit=self.lease['unit'],restart='no',historical_launch_commands=3,historical_authenticated_loaded_TU_boots=1,separately_granted_commands=1,cumulative_ceiling=4,remaining_commands=1,new_launch_authorized=True,process='isolated-fixture',pid=123,read_only_admin_metadata_allowed=True)
        self.b['source_confirmation']=dict(state='verified',lease_sha256=self.digest,manifest_sha256=sha(self.manifest),session=t.FIXTURE_SESSION,files={str(self.payload):sha(self.payload)},route_proof=dict(session=t.FIXTURE_SESSION,provider='openai-codex',model='gpt-6.1-sol',billing_mode='subscription_included',api_call_count=1,input_tokens=1,fixture_only=True))
        self.canonical=self.root.parent/'sol-audit/COORDINATOR_STATE.json';self.canonical.parent.mkdir();self.sync();self.commands=[]
    def sync(self):self.canonical.write_text(json.dumps(self.c))
    def resolve(self,**kw):return w.resolve_active_slot(canonical=self.c,session=t.FIXTURE_SESSION,**kw)
    def external_run(self,cmd,**kw):
        self.commands.append(cmd)
        if cmd[0]=='systemd-run':
            self.assertTrue((self.path/'runtime-claim.json').exists());self.assertIn('--unit=ampjack-parent49-devkit.service',cmd)
            return t.completed(cmd)
        if cmd[0]=='systemctl':return t.completed(cmd,'InvocationID='+'a'*32+'\nControlGroup=/fixture/ampjack-parent49-devkit.service\nRestart=no\n')
        if cmd[0]=='journalctl':return t.completed(cmd)
        raise AssertionError(cmd)
    def launch(self):
        self.sync();slot=self.resolve(require_confirmation=False)
        return slot.launch(t.ENV,gates=lambda l,e:dict(fixture_only=True),run=self.external_run)
    def no_spend(self):
        self.assertFalse((self.path/'runtime-claim.json').exists());self.assertFalse(self.commands)
        self.assertEqual((self.previous/'runtime-claim.json').read_bytes(),self.old_claim)
    def test_correct_slot_claims_once_only_new_paths(self):
        handle=self.launch();self.assertEqual(handle['receipt_sha256'],self.digest)
        self.assertTrue((self.path/'live/launch-handle.json').is_file())
        self.assertEqual(json.loads((self.path/'runtime-claim.json').read_text())['unit'],self.lease['unit'])
        self.assertEqual((self.previous/'runtime-claim.json').read_bytes(),self.old_claim)
        self.assertEqual(sum(c[0]=='systemd-run' for c in self.commands),1)
    def test_duplicate_claim_refuses_second_command(self):
        self.launch();count=len(self.commands)
        with self.assertRaises(FileExistsError):self.launch()
        self.assertEqual(len(self.commands),count)
    def test_ambiguous_empty_claim_is_spent(self):
        (self.path/'runtime-claim.json').write_bytes(b'')
        with self.assertRaises(FileExistsError):self.launch()
        self.assertFalse(self.commands);self.assertEqual((self.path/'runtime-claim.json').read_bytes(),b'')
    def test_interrupted_claim_is_final_without_command(self):
        with patch.object(w.os,'fsync',side_effect=OSError('fixture interrupted claim')):
            with self.assertRaisesRegex(OSError,'interrupted'):self.launch()
        self.assertTrue((self.path/'runtime-claim.json').exists());self.assertFalse(self.commands)
        with self.assertRaises(FileExistsError):self.launch()
        self.assertFalse(self.commands)
    def test_old_slot_and_spent_claim_cannot_authorize(self):
        self.b.update(slot='post-entry-47',slot_path=str(self.previous),claim_path=str(self.previous/'runtime-claim.json'))
        with self.assertRaises(ValueError):self.launch()
        self.no_spend()
    def test_stale_digest_owner_session_unit_and_budget_refuse(self):
        original=copy.deepcopy(self.b)
        for key,value in (('lease_sha256','0'*64),('owner','other'),('session','exited-session'),('unit','ampjack-parent47-devkit.service'),('remaining_commands',0),('guest_root','/other')):
            with self.subTest(field=key):
                self.b.clear();self.b.update(copy.deepcopy(original));self.b[key]=value
                with self.assertRaises(ValueError):self.launch()
                self.no_spend()
    def test_missing_parent_confirmation_no_claim(self):
        self.b['source_confirmation']=None
        with self.assertRaisesRegex(ValueError,'confirmation'):self.launch()
        self.no_spend()
    def test_prepare_only_is_not_launch_authority(self):
        self.b.update(state='verified_prepare_only',new_launch_authorized=False)
        self.assertEqual(self.resolve(require_confirmation=False).path,self.path)
        with self.assertRaisesRegex(ValueError,'PREPARE_ONLY'):self.launch()
        self.no_spend()
    def test_stale_manifest_source_and_confirmation_refuse(self):
        self.payload.write_text('# changed after confirmation\n')
        with self.assertRaisesRegex(ValueError,'changed'):self.launch()
        self.no_spend()
        self.payload.write_text('# isolated fixture only\n');self.b['source_confirmation']['lease_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'receipt'):self.launch()
        self.no_spend()
    def test_redirected_missing_and_escape_paths_refuse(self):
        original=copy.deepcopy(self.b)
        for key,value in (('manifest_path',None),('evidence_root',str(self.previous)),('claim_path',str(self.path/'../runtime-claim.json')),('lease_path',str(self.previous/'PARENT-RUNTIME-LEASE.json'))):
            with self.subTest(field=key):
                self.b.clear();self.b.update(copy.deepcopy(original));self.b[key]=value
                with self.assertRaises(ValueError):self.launch()
                self.no_spend()
    def test_symlink_claim_manifest_live_and_slot_refuse(self):
        for name in ('runtime-claim.json','SOURCE-MANIFEST.json','live'):
            with self.subTest(path=name):
                p=self.path/name;saved=p.read_bytes() if p.is_file() else None
                if p.exists():p.unlink()
                p.symlink_to(self.previous/name)
                try:
                    with self.assertRaises(ValueError):self.resolve()
                    self.assertFalse(self.commands)
                finally:
                    p.unlink()
                    if saved is not None:p.write_bytes(saved)
        moved=self.path.with_name('fixture-moved');self.path.rename(moved);self.path.symlink_to(moved,target_is_directory=True)
        try:
            with self.assertRaises(ValueError):self.resolve()
        finally:self.path.unlink();moved.rename(self.path)
        self.no_spend()
    def test_loose_environment_cannot_select_slot(self):
        with patch.dict(os.environ,AMPJACK_RUNTIME_SLOT='post-entry-49'):
            with self.assertRaisesRegex(ValueError,'environment'):self.launch()
        self.no_spend()
    def test_binding_change_after_gates_refuses_before_claim(self):
        slot=self.resolve()
        def gates(l,e):self.b['unit']='wrong';self.sync();return {}
        with self.assertRaises(ValueError):slot.launch(t.ENV,gates=gates,run=self.external_run)
        self.no_spend()
    def test_constructor_record_and_ui_use_same_slot(self):
        self.stack.enter_context(patch.object(a,'EVIDENCE_ROOT',None));self.stack.enter_context(patch.object(a,'EVIDENCE_PREFIX','continuation-2/'))
        self.stack.enter_context(patch.object(a,'METADATA',None));self.stack.enter_context(patch.object(a,'ROOT',self.root));self.stack.enter_context(patch.object(rec,'R',self.root));self.stack.enter_context(patch.object(rec.f,'OUT','continuation-2/live/'))
        layout=self.root/'continuation-2/capture-abi/layout.json';layout.parent.mkdir(parents=True);layout.write_text(json.dumps(dict(elf_sha256=rec.e.HASHES['elf'])))
        with patch.object(w,'environment',return_value=t.ENV),patch.object(rec.e,'prepare',return_value=t.PLAN):fx=rec.FreshEffects()
        self.assertEqual(fx.slot.path,self.path);self.assertEqual(rec.f.OUT,'post-entry-49/live/')
        fx.record(dict(fixture_only=True));self.assertTrue((self.path/'live/session-result.json').exists())
        self.assertFalse(json.loads((self.path/'status.json').read_text())['real_claim_created'])
        fx.pin=dict(pid=9101);fx.window='fixture';fx.meta=type('Metadata',(),{'guard':lambda s,p:None})()
        with patch('subprocess.check_output',return_value='9101'),patch('subprocess.run',return_value=t.completed([])) as run:fx.ui('shot','test.png')
        self.assertEqual(run.call_args.args[0][-1],str(self.path/'live/test.png'))
        with self.assertRaises(rec.e.Refusal):a.save('post-entry-47/forbidden.json',{})
    def test_new_unit_discovery_validates_before_privileged_reads(self):
        self.launch();slot=self.resolve();lease=slot.lease
        helper=old.FreshTests()
        props=dict(Id=lease['unit'],InvocationID='a'*32,ControlGroup='/fixture/'+lease['unit'],Restart='no',MainPID='9100',ActiveState='active')
        row=dict(pid=9101,start_ticks=123456,boot_id='new-fixture-host-boot',cgroup='0::'+props['ControlGroup'],argv=[str(w.GUEST/'xemu'),'-config_path',str(w.GUEST/'xemu.toml'),'-qmp','unix:'+lease['socket']+',server=on,wait=off'])
        handle=dict(unit=lease['unit'],invocation_id='a'*32,claim_sha256=sha(slot.claim))
        data=helper.public_data(props,row);data['/sys/fs/cgroup'+props['ControlGroup']+'/cgroup.procs']='9100 9101';data['/proc/9100/cgroup']=row['cgroup'];data['/proc/9101/cgroup']=row['cgroup']
        reads=[];real_path=Path
        def path(value):return old.Node(str(value),data) if str(value).startswith(('/proc','/sys/fs/cgroup')) else real_path(value)
        fx=rec.FreshEffects.__new__(rec.FreshEffects);fx.slot=slot;fx.lease=lease
        with patch.object(rec,'Path',side_effect=path),patch.object(rec.f,'canonical',return_value=self.c),patch.object(a,'save'),patch('subprocess.run',side_effect=helper.process(props,reads)),patch.object(a,'METADATA',None):
            ident=fx.discover(handle);self.assertEqual(ident['pid'],9101);self.assertEqual(fx.pin['unit'],lease['unit'])
            reads.clear();data['/proc/9101/stat']='1 (reused) '+' '.join(['0']*19+['999'])
            with self.assertRaisesRegex(rec.e.Refusal,'start changed'):fx.meta.sudo_read(9101,['/usr/bin/cat','/proc/9101/maps'])
            self.assertFalse(reads)
    def test_collector_fix_body_and_early_cleanup_are_unchanged(self):
        import ast
        source=(REAL_ROOT/'tools/recovery.py').read_text();module=ast.parse(source)
        fds=next(n for n in ast.walk(module) if isinstance(n,ast.FunctionDef) and n.name=='fds')
        body=ast.get_source_segment(source,fds)
        self.assertIn('except FileNotFoundError: pass',body)
        self.assertNotIn('except OSError',body)
        fx=rec.FreshEffects.__new__(rec.FreshEffects);fx.meta=None
        self.assertFalse(fx.cleanup_if_unopened()['attempted'])
    def test_release_verification_uses_active_claim_not_old_claim(self):
        self.launch();slot=self.resolve()
        fx=rec.FreshEffects.__new__(rec.FreshEffects);fx.slot=slot;fx.evidence_root=slot.path;fx.lease=slot.lease
        fx.pin=dict(pid=9101,start_ticks=123,unit=slot.lease['unit']);fx.launcher_pin=(9100,122)
        class Gone:
            def read_text(self):raise FileNotFoundError('owned fixture process gone')
        real_path=Path
        def path(value):return Gone() if str(value).startswith('/proc/') else real_path(value)
        def run(cmd,**kw):return t.completed(cmd,'ActiveState=inactive\nSubState=dead\nMainPID=0\nControlGroup=\n' if cmd[0]=='systemctl' else '')
        with patch.object(rec,'Path',side_effect=path),patch('subprocess.run',side_effect=run):result=fx.verify_release()
        self.assertTrue(result['released']);self.assertEqual(result['claim_sha256'],sha(slot.claim))
        self.assertEqual((self.previous/'runtime-claim.json').read_bytes(),self.old_claim)

if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(SlotTests))
    report=dict(all_passed=result.wasSuccessful(),exit_code=0 if result.wasSuccessful() else 1,tests_run=result.testsRun,evidence=str(RUN),fixture_only=True,guest_commands=0)
    (RUN/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report),flush=True);raise SystemExit(report['exit_code'])
