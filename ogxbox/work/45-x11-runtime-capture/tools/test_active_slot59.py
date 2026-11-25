"""Synthetic slot59 production-chain fixtures; no native/device evidence."""
import sys
sys.dont_write_bytecode = True
import contextlib
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import runpy
import struct
from types import SimpleNamespace
from typing import Any
import unittest
from unittest.mock import patch

REAL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REAL))
import parent_launch as w
import recovery as rec
import runtime_session as session
import live_adapter as a

O = REAL.parent/'59-sol-bounded-preparation'
RUN = Path(tempfile.mkdtemp(prefix='fixtures-', dir=os.environ['TMPDIR']))
assert RUN.is_relative_to(O) or RUN.is_relative_to(REAL/'post-entry-59/preparation')
SESSION = 'synthetic-slot59-independent-session'
OWNER = '45-x11-runtime-capture exclusive conditional lease; no parent clients or competing writer'
STOPPED = rec.f.preflight.stopped_gates
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()

def required(root, guest):
    old = json.loads((REAL/'post-entry-49/SOURCE-MANIFEST.json').read_text())['files']
    paths = {Path(p) for p in old if '/post-entry-49/' not in p}
    paths |= {REAL/'tools'/n for n in ('usb_target57.py', 'test_usb_target57.py', 'test_active_slot59.py','test_observer_local_invariant54.py')}
    paths.add(root.parent/'52-usb-topology/topology_check.py')
    paths.update(root.parent/'astra-emu-fix/source/hw/usb'/n for n in ('host-libusb.c','bus.c'))
    return {str(root/p.relative_to(REAL)) if p.is_relative_to(REAL) else str(guest/p.relative_to(w.GUEST)) if p.is_relative_to(w.GUEST) else str(p) for p in paths}

class Slot59(unittest.TestCase):
    real_subprocess=staticmethod(subprocess.run)
    def setUp(self):
        self.out = RUN/self._testMethodName
        self.root = self.out/REAL.name
        self.path = self.root/'post-entry-59'
        self.path.mkdir(parents=True)
        self.guest = self.out/'42-enum-observer/parent-prepared-guest'
        self.guest.mkdir(parents=True)
        self.stack = contextlib.ExitStack(); self.addCleanup(self.stack.close)
        self.commands = []; self.gate_hook = None
        # Independent invented authority, never copied from the real owner.
        self.c = dict(owner_hold=False, resume_authorized=True, runtime_card='t_af7623e9', runtime_owner=OWNER,
                      resume_authority_message='1575044307038109747', scope_correction_message='1575048626248486923', synthetic=True)
        self.b = dict(state='verified', slot='post-entry-59', mode='post_entry59_fresh_bounded_launch', session=SESSION,
                      owner=REAL.name, card='t_af7623e9', provider='openai-codex', model='gpt-6.1-sol', route_verified=True,
                      billing_mode='subscription_included', reasoning='medium', process='synthetic-worker59', pid=590059,
                      unit='ampjack-parent59-devkit.service', restart='no', historical_launch_commands=4,
                      historical_authenticated_loaded_TU_boots=2, separately_granted_commands=1, cumulative_ceiling=5,
                      old_allowance_remaining=0, remaining_commands=1, new_launch_authorized=True,
                      work_root=str(self.root), guest_root=str(self.guest), slot_path=str(self.path), evidence_root=str(self.path),
                      lease_path=str(self.path/'PARENT-RUNTIME-LEASE.json'), claim_path=str(self.path/'runtime-claim.json'),
                      manifest_path=str(self.path/'SOURCE-MANIFEST.json'))
        self.c['runtime_binding'] = self.b
        self.lease: dict[str,Any] = dict(status='PROVIDED', owner=REAL.name, work_root=str(self.root), fresh_clone=str(self.guest),
                          active_slot='post-entry-59', slot_path=str(self.path), evidence_root=str(self.path),
                          claim_path=self.b['claim_path'], unit=self.b['unit'], restart='no', owner_hold=False,
                          historical_launch_commands=4, historical_authenticated_loaded_TU_boots=2, old_allowance_remaining=0,
                          new_launch_commands_allowed=1, boot_launch_commands=0, cumulative_command_ceiling=5,
                          authority=self.c['resume_authority_message'], scope_correction=self.c['scope_correction_message'],
                          synthetic=True)
        prev = self.root/'post-entry-49'; prev.mkdir()
        (prev/'SOURCE-MANIFEST.json').write_bytes((REAL/'post-entry-49/SOURCE-MANIFEST.json').read_bytes())
        # Raw predecessor bytes are immutable pins; no old suite executes.
        for key, name in [('previous_lease','PARENT-RUNTIME-LEASE.json'),('previous_claim','runtime-claim.json')]:
            p = prev/name; p.write_bytes((REAL/'post-entry-49'/name).read_bytes())
            self.lease[key] = dict(path=str(p), sha256=sha(p))
        self.private = dict(DISPLAY=':59', WAYLAND_DISPLAY=f'/run/user/{os.getuid()}/synthetic59/wayland-0', SDL_VIDEO_DRIVER='x11', XDG_RUNTIME_DIR=f'/run/user/{os.getuid()}')
        envfile = self.path/'private-environment.json'; envfile.write_text(json.dumps(self.private))
        self.lease.update(environment_file=str(envfile), environment_file_identity=dict(sha256=sha(envfile)), private_environment=self.private)
        self.b['private_environment'] = copy.deepcopy(self.private)
        self.files = {}
        for name in required(self.root, self.guest):
            p = Path(name)
            if p.is_relative_to(self.out):
                orig = REAL/p.relative_to(self.root) if p.is_relative_to(self.root) else w.GUEST/p.relative_to(self.guest) if p.is_relative_to(self.guest) else REAL.parent/p.relative_to(self.root.parent)
                p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(orig.read_bytes())
            self.files[name] = sha(p)
        green = self.out/'synthetic-green.json'; green.write_text(json.dumps(dict(all_passed=True, exit_code=0, synthetic=True)))
        self.manifest = dict(files=self.files, test_receipts={str(green):sha(green)}, fixture_files={}, synthetic=True)
        self.seal()
        (self.path/'status.json').write_text('{}')
        layout = self.root/'continuation-2/capture-abi/layout.json'; layout.parent.mkdir(parents=True, exist_ok=True)
        self.assertEqual(json.loads(layout.read_text())['elf_sha256'],rec.e.HASHES['elf'])
        self.canonical = self.root.parent/'sol-audit/COORDINATOR_STATE.json'; self.canonical.parent.mkdir()
        self.sync()
        for obj, key, val in [(w,'ROOT',self.root),(w,'GUEST',self.guest),(a,'ROOT',self.root),(rec,'R',self.root),(session,'R',self.root),(rec.f,'R',self.root),(rec.f.preflight,'R',self.root),(a,'EVIDENCE_ROOT',None),(a,'METADATA',None),(rec.f,'OUT','continuation-2/live/')]:
            self.stack.enter_context(patch.object(obj,key,val))
        self.stack.enter_context(patch.dict(os.environ,HERMES_SESSION_ID=SESSION))
        self.stack.enter_context(patch('subprocess.run',side_effect=AssertionError('unsubstituted external process')))
        self.stack.enter_context(patch('socket.socket',side_effect=AssertionError('unsubstituted external socket')))
        self.stack.enter_context(patch.object(rec.e,'prepare',return_value=dict(synthetic=True)))
        # Only socket filesystem observations are synthetic; environment validation is real.
        original_stat = Path.stat
        self.sockets = {'/tmp/.X11-unix/X59', self.private['WAYLAND_DISPLAY']}
        original_resolve = Path.resolve
        def resolve(p,*args,**kw):
            if str(p) in self.sockets or str(p).startswith('/run/user/'):
                return p
            return original_resolve(p,*args,**kw)
        self.stack.enter_context(patch.object(Path,'resolve',resolve))
        def stat(p,*args,**kw):
            if str(p) in self.sockets:return type('SocketStat',(),dict(st_uid=os.getuid(),st_mode=0o140600))()
            return original_stat(p,*args,**kw)
        self.stack.enter_context(patch.object(Path,'stat',stat))
        self.stack.enter_context(patch.object(rec.f.preflight,'resources',return_value=dict(processes=[],disk_fds=[],tcp='',qmp_listeners=[],qmp_path_exists=False,unit='LoadState=not-found')))
        # Real stopped-gates uses a synthetic block reader and synthetic USB
        # tree, never host /sys, /dev, disk tools, guard or real title data.
        raw=bytearray(0x300);raw[:4]=b'XBEH'
        struct.pack_into('<I',raw,0x104,0x10000);struct.pack_into('<I',raw,0x118,0x10180)
        self.xbe=bytes(raw)
        pre=rec.f.preflight
        expected={'E:/synthetic/default.xbe':pre.xbe_identity('E:/synthetic/default.xbe',self.xbe)}
        self.stack.enter_context(patch.object(pre,'title_attestation',return_value=expected))
        self.stack.enter_context(patch.object(a,'kernel_dispatch_pin',return_value=dict(synthetic=True)))
        test=self
        class Device:
            def __init__(self,path):self.f=SimpleNamespace(close=lambda:None)
        class Fs:
            def __init__(self,*args):pass
            def read(self,path):return test.xbe
        self.stack.enter_context(patch.object(a,'load_file',return_value=SimpleNamespace(Qcow2=Device,Fatx=Fs,PARTS={'E':(0,0)})))
        class Usb:
            def __init__(self,key=None):self.key=key
            def __truediv__(self,key):return Usb(key)
            def iterdir(self):return [Usb()]
            def read_text(self):
                assert isinstance(self.key,str)
                return {'idVendor':'045e','idProduct':'0b12','busnum':'3','devnum':'7','speed':'12'}[self.key]
            def __str__(self):return str(test.out/'synthetic-usb-directory')
        self.stack.enter_context(patch.object(pre,'Path',side_effect=lambda p:Usb() if str(p)=='/sys/bus/usb/devices' else Path(p)))
        self.stack.enter_context(patch.object(pre.os,'access',return_value=True))
        self.lease.update(identities={},frozen_inputs={});self.seal();self.sync()

    def seal(self):
        receipt = self.path/'PARENT-RUNTIME-LEASE.json'; receipt.write_text(json.dumps(self.lease))
        self.b['lease_sha256'] = sha(receipt)
        self.manifest['lease_sha256'] = sha(receipt)
        p = self.path/'SOURCE-MANIFEST.json'; p.write_text(json.dumps(self.manifest))
        self.b['source_confirmation'] = dict(state='verified',lease_sha256=sha(receipt),manifest_sha256=sha(p),session=SESSION,files=self.manifest['files'],
            route_proof=dict(session=SESSION,provider='openai-codex',model='gpt-6.1-sol',billing_mode='subscription_included',api_call_count=1,input_tokens=1,synthetic=True))
    def sync(self):self.canonical.write_text(json.dumps(self.c))
    def external_run(self,cmd,**kw):
        if cmd[0] in ('systemd-run','systemctl','journalctl'):self.commands.append(cmd)
        if cmd[0]=='systemd-run':
            self.assertTrue((self.path/'runtime-claim.json').is_file())
            self.assertIn('--unit=ampjack-parent59-devkit.service',cmd)
            return subprocess.CompletedProcess(cmd,0,'','')
        if cmd[0]=='systemctl':return subprocess.CompletedProcess(cmd,0,'InvocationID='+'a'*32+'\nRestart=no\n','')
        if cmd[0]=='journalctl':return subprocess.CompletedProcess(cmd,0,'','')
        if cmd[0]=='qemu-img':return subprocess.CompletedProcess(cmd,0,'{"check-errors":0}','')
        if cmd[0]=='ldd':return subprocess.CompletedProcess(cmd,0,'synthetic resolved dependency','')
        if cmd[-1]=='--check':return subprocess.CompletedProcess(cmd,0,'synthetic guard check','')
        raise AssertionError(cmd)
    def gates(self,lease,env,**kw):
        self.assertEqual(kw['claim_path'],self.path/'runtime-claim.json')
        self.assertEqual(kw['evidence'],'post-entry-59')
        with patch('subprocess.run',side_effect=self.external_run):
            proof=STOPPED(lease,env,**kw)
        if self.gate_hook:self.gate_hook()
        return proof
    def normal(self):
        self.sync()
        with patch.object(sys,'argv',['parent_launch.py']), patch.object(rec.f.preflight,'stopped_gates',side_effect=self.gates), patch.object(w.ActiveSlot.launch,'__kwdefaults__',dict(run=self.external_run)),patch.object(w,'resolve_active_slot',wraps=w.resolve_active_slot) as reads:
            try:return w.main()
            finally:
                selected=[call for call in reads.call_args_list if call.kwargs.get('_selected') is None]
                self.assertEqual(len(selected),1,'normal chain must select exactly once')
                for call in reads.call_args_list:
                    if call.kwargs.get('_selected') is not None:self.assertEqual(call.kwargs['_selected'].path,self.path)
    def no_claim(self):
        self.assertFalse((self.path/'runtime-claim.json').exists()); self.assertFalse(self.commands)
    def test_recipe59_staged_command(self):
        self.b.update(new_launch_authorized=False); self.b.pop('source_confirmation'); self.sync()
        with patch.object(sys,'argv',['parent_launch.py','--command']), contextlib.redirect_stdout(__import__('io').StringIO()) as out:
            self.assertEqual(w.main(),0)
        self.assertIn('ampjack-parent59-devkit.service',out.getvalue()); self.no_claim()

    def test_staged_check(self):
        self.b.update(new_launch_authorized=False);self.b.pop('source_confirmation');self.sync()
        with patch.object(sys,'argv',['parent_launch.py','--check']),patch('subprocess.run',side_effect=self.external_run):
            self.assertEqual(w.main(),0)
        self.assertFalse((self.path/'runtime-claim.json').exists())

    def test_staged_active_slot_preflight(self):
        self.b.update(new_launch_authorized=False);self.b.pop('source_confirmation');self.sync()
        pre=rec.f.preflight
        def trace(frame,event,arg):
            if frame.f_code.co_filename==str(REAL/'tools/live_preflight.py') and event=='line' and frame.f_lineno==136:
                frame.f_globals.update(resources=pre.resources,Path=pre.Path,title_attestation=pre.title_attestation)
            return trace
        try:
            sys.settrace(trace)
            with patch.object(sys,'argv',['live_preflight.py','--active-slot']),patch('subprocess.run',side_effect=self.external_run),contextlib.redirect_stdout(__import__('io').StringIO()):
                runpy.run_path(str(REAL/'tools/live_preflight.py'),run_name='__main__')
        finally:sys.settrace(None)
        self.assertTrue((self.path/'preflight.json').exists());self.assertFalse((self.path/'runtime-claim.json').exists())

    def test_normal_positive_claim_cleanup_same_slot(self):
        self.install_external_session()
        self.assertEqual(self.normal(),1)  # refusal of takeover is NOT healthy
        result=json.loads((self.path/'live/session-result.json').read_text())
        self.assertIsNone(result['first_failed_link']);self.assertTrue(result['remaining_resources']['released'])
        self.assertTrue(result['module']);self.assertEqual(self.q_calls,['quit'])
        self.assertEqual(sum(c[0]=='systemd-run' for c in self.commands),1)
        self.assertTrue(json.loads((self.path/'status.json').read_text())['real_claim_created'])
        self.assertEqual(a.EVIDENCE_ROOT,self.path)

    def install_external_session(self, capture_error=False, quit_error=False):
        self.q_calls=[]
        test=self
        class Q:
            def cmd(self,name):
                test.q_calls.append(name)
                if quit_error:raise RuntimeError('synthetic quit error')
            def close(self):pass
        class R:
            def close(self):pass
        def capture(*args):
            if capture_error:raise RuntimeError('synthetic capture error')
            return dict(synthetic=True)
        for name,fun in dict(discover=lambda fx,h:dict(pid=59001),authenticate=lambda *x:None,
                open_q=lambda fx:Q(),parity=lambda *x:None,open_r=lambda *x:R(),load_title=lambda *x:None,
                observe=lambda *x:dict(hold=False,synthetic=True),capture=capture,accept=lambda *x:None,
                reauthenticate=lambda *x:None,context=lambda *x:None,verify_release=lambda *x:dict(released=True)).items():
            self.stack.enter_context(patch.object(rec.FreshEffects,name,fun))
        # Exercise inherited install orchestration, stubbing only RAM/protocol
        # effects and USB device boundary, not replacing LiveEffects.install.
        for name,fun in dict(allocate=lambda *x:dict(base=0x100000),install=lambda *x:dict(module=0x100000),check_native=lambda *x:{},check_entry=lambda *x:{}).items():
            self.stack.enter_context(patch.object(a,name,fun))
        self.stack.enter_context(patch.object(rec.f.usb_target57,'qualify',return_value=dict(synthetic=True)))
        self.stack.enter_context(patch.object(a,'close_q',side_effect=lambda q:q.close()))


    def test_capture_and_quit_errors_preserved(self):
        self.install_external_session(capture_error=True,quit_error=True)
        self.assertEqual(self.normal(),1)
        result=json.loads((self.path/'live/session-result.json').read_text())
        self.assertEqual(result['first_failed_link'],'responsive_capture')
        self.assertIn('synthetic capture error',result['error']);self.assertIn('synthetic quit error',result['quit_error'])
        self.assertTrue((self.path/'runtime-claim.json').exists())

    def test_unset_fixture_session_before_environment(self):
        os.environ.pop('HERMES_SESSION_ID',None)
        with patch.object(w,'environment',side_effect=AssertionError('environment reached')):
            with self.assertRaises(ValueError):self.normal()
        self.no_claim()

    def test_actual_current_coordinator_unset_normal_cli(self):
        env=dict(os.environ);env.pop('HERMES_SESSION_ID',None)
        # Only the real negative command executes; cannot qualify current owner.
        with patch('subprocess.run',self.real_subprocess):
            p=self.real_subprocess(['/usr/bin/python3','-B',str(REAL/'parent_launch.py')],cwd=REAL,env=env,capture_output=True,text=True)
        (self.out/'actual-negative.stdout').write_text(p.stdout);(self.out/'actual-negative.stderr').write_text(p.stderr)
        self.assertNotEqual(p.returncode,0);self.assertIn('authority/session/route/budget mismatch',p.stderr)
        self.no_claim()

    def test_mid_gate_rebind(self):
        self.gate_hook=lambda:(self.b.update(process='different-synthetic-worker'),self.sync())
        self.install_external_session();self.assertEqual(self.normal(),1);self.no_claim()
        result=json.loads((self.path/'live/session-result.json').read_text())
        self.assertIn('binding changed',result['error'])

    def test_post_claim_authority_and_handle(self):
        self.install_external_session();self.normal()
        fxslot=w.resolve_active_slot(consumed=True)
        fxslot.authority(fxslot.lease,consumed=True)
        handle=self.path/'live/launch-handle.json';d=json.loads(handle.read_text());d['claim_sha256']='0'*64;handle.write_text(json.dumps(d))
        with self.assertRaisesRegex(ValueError,'handle'):fxslot.authority(fxslot.lease,consumed=True)

    def test_ambiguous_issue_permanently_spent(self):
        self.install_external_session()
        original=self.external_run
        def run(cmd,**kw):
            if cmd[0]=='systemd-run':self.commands.append(cmd);raise OSError('synthetic ambiguous issue')
            return original(cmd,**kw)
        self.external_run=run
        self.assertEqual(self.normal(),1)
        self.assertTrue((self.path/'runtime-claim.json').exists())
        self.assertIn('ambiguous issue',(self.path/'live/launch-handle.json').read_text())
        count=len(self.commands)
        with self.assertRaises(FileExistsError):self.normal()
        self.assertEqual(len(self.commands),count)

    def test_interrupted_claim_spent(self):
        self.install_external_session()
        with patch.object(w.os,'fsync',side_effect=OSError('synthetic fsync interruption')):self.normal()
        self.assertTrue((self.path/'runtime-claim.json').exists());self.assertFalse(self.commands)
        with self.assertRaises(FileExistsError):self.normal()

    def test_rebind_after_claim_refuses_issue_and_stays_spent(self):
        self.install_external_session();original=w.atomic_claim
        def claim(*args,**kw):
            original(*args,**kw);self.b['process']='synthetic-rebound-after-claim';self.sync()
        with patch.object(w,'atomic_claim',side_effect=claim):self.assertEqual(self.normal(),1)
        self.assertTrue((self.path/'runtime-claim.json').exists())
        self.assertFalse(any(c[0]=='systemd-run' for c in self.commands))
        self.assertIn('binding changed',(self.path/'live/launch-handle.json').read_text())
        with self.assertRaises(FileExistsError):self.normal()

    def test_consumed_cleanup_allows_zero_but_not_new_launch(self):
        self.install_external_session();self.normal()
        selected=w.resolve_active_slot(consumed=True)
        self.b.update(remaining_commands=0,new_launch_authorized=False);self.sync()
        selected.authority(selected.lease,consumed=True)
        with self.assertRaises(ValueError):w.resolve_active_slot()


def refusal_case(label, mutate, expected=(ValueError,OSError,KeyError)):
    def test(self):
        mutate(self);self.sync()
        self.install_external_session()
        evidence: dict[str,Any]=dict(synthetic=True,case=label)
        try:
            result=self.normal()
        except expected as error:
            evidence.update(boundary='constructor_before_environment_or_effects',error=str(error))
        else:
            self.assertEqual(result,1)
            result=json.loads((self.path/'live/session-result.json').read_text())
            self.assertEqual(result['first_failed_link'],'stopped_gates_and_claim')
            evidence.update(boundary=result['first_failed_link'],error=result['error'])
        self.assertFalse(self.commands)
        (self.out/'failure-receipt.json').write_text(json.dumps(evidence,indent=2))
        if label not in ('duplicate_claim','empty_claim'):
            self.assertFalse((self.path/'runtime-claim.json').exists())
    test.__name__='test_refuse_'+label
    setattr(Slot59,test.__name__,test)

for field,value in [('slot','post-entry-49'),('mode','post_entry49_fresh_bounded_launch'),('session','synthetic-other'),('owner','wrong'),('unit','old.service'),('pid',0),('process',''),('provider','nous'),('model','wrong'),('route_verified',False),('billing_mode','api'),('reasoning','high'),('historical_launch_commands',3),('historical_authenticated_loaded_TU_boots',1),('remaining_commands',0),('cumulative_ceiling',6),('old_allowance_remaining',1),('lease_sha256',None),('lease_sha256','0'*64),('lease_sha256','a1'*32),('new_launch_authorized',False),('source_confirmation',None)]:
    refusal_case(field+'_'+str(value).replace('/','_'),lambda s,f=field,v=value:s.b.update({f:v}))
for field in ('work_root','guest_root','slot_path','evidence_root','lease_path','claim_path','manifest_path'):
    refusal_case('redirect_'+field,lambda s,f=field:s.b.update({f:str(s.path/'../escape')}))
for label,name in [('duplicate_claim','runtime-claim.json'),('empty_claim','runtime-claim.json'),('stale_handle','live/launch-handle.json'),('stale_descendant','live/nested/capture.json')]:
    def stale(s,n=name):
        p=s.path/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'')
    refusal_case(label,stale)
for name in ('runtime-claim.json','SOURCE-MANIFEST.json','live','status.json','navigation-reviewed.json','PARENT-RUNTIME-LEASE.json'):
    def alias(s,n=name):
        p=s.path/n
        if p.exists():p.rename(p.with_name(p.name+'.retained'))
        p.symlink_to(s.out/'synthetic-dangling')
    refusal_case('dangling_'+name,alias)
for name in ('usb_target57.py','enum_watch.py','runtime_session.py'):
    def changed(s,n=name):
        (s.root/'tools'/n).write_text('# synthetic changed source\n')
    refusal_case('changed_'+name,changed)
def omit(s):
    s.manifest['files'].pop(str(s.root.parent/'52-usb-topology/topology_check.py'));s.seal()
refusal_case('omitted_topology_dependency',omit)
def predecessor(s):
    (s.root/'post-entry-49/runtime-claim.json').write_text('synthetic altered predecessor')
refusal_case('altered_predecessor',predecessor)
for key in ('AMPJACK_RUNTIME_SLOT','W45_RUNTIME_SLOT','RUNTIME_SLOT'):
    refusal_case('env_'+key,lambda s,k=key:s.stack.enter_context(patch.dict(os.environ,{k:'post-entry-59'})))
for display in (':0',':1',':059','localhost:59',':59.0'):
    refusal_case('display_'+display,lambda s,d=display:s.b['private_environment'].update(DISPLAY=d))

for key in ('runtime_owner','runtime_card','resume_authority_message','scope_correction_message'):
    refusal_case('canonical_'+key,lambda s,k=key:s.c.update({k:'synthetic-wrong'}))
for field,value in [('unit','old.service'),('historical_launch_commands',3),('historical_authenticated_loaded_TU_boots',1),('old_allowance_remaining',1),('new_launch_commands_allowed',2),('cumulative_command_ceiling',6),('authority','wrong')]:
    def lease_change(s,f=field,v=value):s.lease[f]=v;s.seal()
    refusal_case('receipt_'+field,lease_change)
for name in ('PARENT-RUNTIME-LEASE.json','SOURCE-MANIFEST.json'):
    refusal_case('missing_'+name,lambda s,n=name:(s.path/n).rename(s.out/(n+'.retained')))
for field,value in [('manifest_sha256','0'*64),('lease_sha256','0'*64),('session','synthetic-exited'),('files',{}),('state','unverified')]:
    refusal_case('confirmation_'+field,lambda s,f=field,v=value:s.b['source_confirmation'].update({f:v}))
for field,value in [('input_tokens',0),('api_call_count',0),('session','exited'),('provider','nous'),('model','wrong'),('billing_mode','api')]:
    refusal_case('proof_'+field,lambda s,f=field,v=value:s.b['source_confirmation']['route_proof'].update({f:v}))
for n in ('parent_launch.py','tools/runtime_effects.py','tools/recovery.py','tools/runtime_session.py','tools/live_adapter.py','tools/live_preflight.py','tools/usb_target57.py','tools/enum_watch.py','tools/test_active_slot59.py'):
    def omitted(s,name=n):s.manifest['files'].pop(str(s.root/name));s.seal()
    refusal_case('membership_'+n.replace('/','_'),omitted)
def changed_topology(s):
    (s.root.parent/'52-usb-topology/topology_check.py').write_text('# synthetic changed dependency\n')
refusal_case('changed_external_topology',changed_topology)
def predecessor_path(s):
    pin=s.lease['previous_claim'];p=s.out/'copied-spent-claim.json';p.write_bytes(Path(pin['path']).read_bytes());pin['path']=str(p);s.seal()
refusal_case('predecessor_alias_same_bytes',predecessor_path)
def slot_alias(s):
    moved=s.path.with_name('retained-slot');s.path.rename(moved);s.path.symlink_to(moved,target_is_directory=True)
refusal_case('slot_symlink',slot_alias)
def nested_alias(s):
    p=s.path/'live';p.mkdir();(p/'nested-output').symlink_to(s.out/'absent')
refusal_case('nested_output_symlink',nested_alias)
def software(s):s.b['private_environment']['LIBGL_ALWAYS_SOFTWARE']='1'
refusal_case('attested_software_graphics',software)

def tearDownModule():
    files={}
    for name,module in tuple(sys.modules.items()):
        filename=getattr(module,'__file__',None)
        if filename and str(filename).startswith('/home/roasted/'):
            p=Path(filename)
            if p.is_file():files[name]=dict(path=str(p),sha256=sha(p))
    (RUN/'actual-imports.json').write_text(json.dumps(files,indent=2))

if __name__=='__main__':unittest.main(verbosity=2)