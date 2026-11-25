"""Isolated offline raw-boundary tests; no inherited suites or live constructors."""
import json
import copy
import os
import sys
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

D = Path(__file__).resolve().parents[2] / '57-usb-runtime-qualification'
RUN = Path(os.environ['USB57_RUN']) if 'USB57_RUN' in os.environ else Path(tempfile.mkdtemp(prefix='focused-',dir=D))
assert RUN.is_relative_to(D) and RUN.is_dir()
if 'USB57_RUN' in os.environ:
    for key in ('PYTHONPYCACHEPREFIX','TMPDIR','XDG_CACHE_HOME'):
        assert Path(os.environ[key]).is_relative_to(RUN)
old_prefix = sys.pycache_prefix
sys.pycache_prefix = str(RUN/'import-cache')
import runtime_effects as effects
import runtime_session
import usb_target57 as usb
sys.pycache_prefix = old_prefix

HIST = json.loads((effects.R / 'post-entry-49/live/usb-topology.json').read_text())

HUB_ROW = '  Device 1.0, Port 1, Speed 12 Mb/s, Product QEMU USB Hub\r\n'
TARGET_ROW = '  Device 1.5, Port 1.4, Speed 12 Mb/s, Product Fixture controller, ID: pt_pad3\r\n'
NEIGHBOR_ROW = '  Device 1.3, Port 1.3, Speed 12 Mb/s, Product Neighbor, ID: neighbor\r\n'
TREE_HEAD = '''bus: main-system-bus
  dev: xbox-pcihost, id ""
    bus: pci.0
      dev: pci-ohci, id ""
        addr = 02.0
        bus: usb-bus.1
          dev: usb-hub, id "hub"
            port = "1"
            addr 1.0, port 1, speed 12, name QEMU USB Hub, attached
'''
TREE_TARGET = '''          dev: usb-host, id "pt_pad3"
            hostbus = 3 (0x3)
            hostaddr = 7 (0x7)
            vendorid = 0 (0x0)
            productid = 0 (0x0)
            hostport = ""
            hostdevice = ""
            port = "1.4"
            addr 1.5, port 1.4, speed 12, name Fixture controller, attached
'''

def positive():
    return dict(before=HUB_ROW+NEIGHBOR_ROW,pre_qtree=TREE_HEAD,
                after=HUB_ROW+NEIGHBOR_ROW+TARGET_ROW,qtree=TREE_HEAD+TREE_TARGET)

def mutate(field, old, new):
    def change(c): c[field] = c[field].replace(old,new)
    return change

MUTATIONS = {
    'target_low_neighbor_full': lambda c: (mutate('after','1.4, Speed 12','1.4, Speed 1.5')(c),mutate('qtree','1.4, speed 12','1.4, speed 1.5')(c)),
    'target_unknown': lambda c: (mutate('after','1.4, Speed 12','1.4, Speed ?')(c),mutate('qtree','1.4, speed 12','1.4, speed ?')(c)),
    'target_absent_neighbor_full': lambda c: c.update(after=HUB_ROW+NEIGHBOR_ROW,qtree=TREE_HEAD),
    'missing_id': mutate('qtree','id "pt_pad3"','id "other"'),
    'duplicate_id': lambda c: c.update(qtree=c['qtree']+TREE_TARGET),
    'duplicate_path': lambda c: c.update(qtree=c['qtree']+TREE_TARGET.replace('pt_pad3','other')),
    'missing_row': lambda c: c.update(after=HUB_ROW+NEIGHBOR_ROW),
    'duplicate_row': lambda c: c.update(after=c['after']+TARGET_ROW),
    'wrong_controller': mutate('qtree','addr = 02.0','addr = 03.0'),
    'wrong_pci_ancestry': mutate('qtree','bus: pci.0','bus: pci.1'),
    'wrong_bus': mutate('qtree','usb-bus.1','usb-bus.2'),
    'wrong_busnr': mutate('qtree','addr 1.5','addr 2.5'),
    'wrong_hub': mutate('qtree','dev: usb-hub','dev: usb-host'),
    'detached_hub': mutate('qtree','name QEMU USB Hub, attached','name QEMU USB Hub'),
    'missing_hub': lambda c: c.update(qtree=c['qtree'].replace(TREE_HEAD,TREE_HEAD[:TREE_HEAD.index('          dev: usb-hub')])),
    'wrong_driver': mutate('qtree','dev: usb-host','dev: usb-mouse'),
    'wrong_port': mutate('qtree','port = "1.4"','port = "1.3.4"'),
    'wrong_hostbus': mutate('qtree','hostbus = 3','hostbus = 4'),
    'wrong_hostaddr': mutate('qtree','hostaddr = 7','hostaddr = 8'),
    'filter_vendor': mutate('qtree','vendorid = 0 (0x0)','vendorid = 1118 (0x45e)'),
    'filter_product': mutate('qtree','productid = 0 (0x0)','productid = 2834 (0xb12)'),
    'filter_hostport': mutate('qtree','hostport = ""','hostport = "1"'),
    'filter_hostdevice': mutate('qtree','hostdevice = ""','hostdevice = "/dev/example"'),
    'listing_address_disagrees': mutate('after','Device 1.5','Device 1.6'),
    'listing_product_disagrees': mutate('after','Fixture controller','Different label'),
    'listing_speed_disagrees': mutate('after','1.4, Speed 12','1.4, Speed 480'),
    'detached_target': mutate('qtree','Fixture controller, attached','Fixture controller'),
    'stale_listing': lambda c: c.update(before=c['before']+TARGET_ROW),
    'tree_only_collision': lambda c: c.update(pre_qtree=c['pre_qtree']+TREE_TARGET.replace('pt_pad3','other')),
    'tree_id_collision': lambda c: c.update(pre_qtree=c['pre_qtree']+TREE_TARGET.replace('"1.4"','"1.2"').replace('port 1.4','port 1.2')),
}

class Peer:
    def __init__(self, capture):
        self.capture = capture
        self.calls = []
        self.reads = 0
        self.reply = {}
        self.action = None
        self.hmp_action = None
    def hmp(self, command):
        self.calls.append(command)
        self.reads += 1
        if self.hmp_action: self.hmp_action(self.reads)
        if self.reads == 1: return self.capture['before']
        if self.reads == 2: return self.capture.get('pre_qtree', '')
        if self.reads == 3: return self.capture['after']
        return self.capture['qtree']
    def cmd(self, name, **args):
        self.calls.append((name, args))
        if self.action: self.action()
        if isinstance(self.reply, Exception): raise self.reply
        return self.reply

class InstallTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix=self._testMethodName+'-', dir=RUN))
        self.pad = self.root/'physical'; self.pad.mkdir()
        for k,v in dict(idVendor='045e',idProduct='0b12',busnum='3',devnum='7',speed='12').items():
            (self.pad/k).write_text(v+'\n')
        self.ident = dict(boot_id='offline-boot',pid=57,start_ticks=570)
        self.fx = object.__new__(effects.LiveEffects)
        self.fx.lease = {}
        self.fx.authenticated_handle = dict(invocation_id='offline-invocation')
        self.fx.pre = dict(usb=[dict(sysfs=str(self.pad),busnum='3',devnum='7',speed='12',node='/dev/bus/usb/003/007')])
        self.saved = {}; self.guards = []
        def save(name, value):
            self.saved[name] = json.loads(json.dumps(value))
            (self.root/Path(name).name).write_text(json.dumps(value,indent=2))
        self.patches = [patch.object(effects.a,'allocate',return_value={'base':4096}),
            patch.object(effects.a,'install',return_value={'module':8192}),
            patch.object(effects.a,'check_native',side_effect=lambda *x:self.guards.append('native') or dict(self.ident)),
            patch.object(effects.a,'check_entry',side_effect=lambda *x:self.guards.append('entry') or {'entry':'held'}),
            patch.object(effects.a,'save',side_effect=save),
            patch('subprocess.run',side_effect=AssertionError('external command forbidden')),
            patch('socket.socket',side_effect=AssertionError('socket forbidden'))]
        for p in self.patches: p.start(); self.addCleanup(p.stop)
    def test_original_wrong_device_speed_refused(self):
        q = Peer(HIST)
        with self.assertRaisesRegex(RuntimeError, 'USB|usb|target|speed|attached'):
            self.fx.install(q, object(), self.ident)
        self.assertTrue(any(isinstance(c,tuple) and c[0]=='device_add' for c in q.calls))
        proof=self.proof()
        self.assertFalse(proof['verdict']['qualified'])
        self.assertEqual(proof['after'],HIST['after'])
        self.assertEqual(proof['qtree'],HIST['qtree'])
        self.assertEqual(proof['verdict']['emulated_speed'],'1.5')
        self.assertIs(proof['verdict']['attached_at_sample'],False)

    def test_nondefault_validated_address(self):
        (self.pad/'busnum').write_text('5');(self.pad/'devnum').write_text('9')
        self.fx.pre['usb'][0].update(busnum='5',devnum='9',node='/dev/bus/usb/005/009')
        c=positive();c['qtree']=c['qtree'].replace('hostbus = 3 (0x3)','hostbus = 5 (0x5)').replace('hostaddr = 7 (0x7)','hostaddr = 9 (0x9)')
        q=Peer(c);self.fx.install(q,object(),self.ident)
        self.assertEqual(q.calls[2],('device_add',usb.direct_arguments(5,9)))
        self.assertTrue(self.proof()['verdict']['qualified'])

    def test_no_authenticated_invocation(self):
        del self.fx.authenticated_handle
        q=Peer(positive());self.refuse(q);self.assertEqual(q.calls,[])

    def test_physical_removed_after_add(self):
        q=Peer(positive());q.action=lambda:self.pad.rename(self.root/'gone');self.refuse(q)

    def test_physical_attribute_unreadable_after_add(self):
        q=Peer(positive());q.action=lambda:(self.pad/'speed').unlink();self.refuse(q)
        self.assertEqual(self.proof()['failed_stage'],'physical_post_add')
        self.assertIn('failed_observation',self.proof())
        self.assertNotIn('after',self.proof())

    def test_address_changes_after_query(self):
        q=Peer(positive())
        def change(n):
            if n==4:(self.pad/'devnum').write_text('8')
        q.hmp_action=change;self.refuse(q)

    def test_preflight_node_mismatch(self):
        self.fx.pre['usb'][0]['node']='/dev/bus/usb/003/008';self.refuse(Peer(positive()))

    def test_preflight_ambiguous(self):
        self.fx.pre['usb']*=2;self.refuse(Peer(positive()))

    def test_exact_not_substring_collision(self):
        c=positive();c['before']+='  Device 1.7, Port 1.4.2, Speed 12 Mb/s, Product Neighbor, ID: pt_pad30\n'
        c['pre_qtree']+=TREE_TARGET.replace('pt_pad3','pt_pad30').replace('1.4','1.4.2')
        self.fx.install(Peer(c),object(),self.ident)
        self.assertTrue(self.proof()['verdict']['qualified'])

    def test_guard_failure_preserves_partial_evidence(self):
        with patch.object(effects.a,'check_native',side_effect=RuntimeError('native mismatch')):
            q=Peer(positive());self.refuse(q);self.assertEqual(q.calls,[])
        self.assertEqual(self.proof()['failed_stage'],'native_before')

    def test_final_native_bracket_refuses(self):
        count=0
        def native(*args):
            nonlocal count
            count+=1
            if count==2:raise RuntimeError('native changed')
            return dict(self.ident)
        with patch.object(effects.a,'check_native',side_effect=native):self.refuse(Peer(positive()))
        self.assertEqual(self.proof()['failed_stage'],'native_after')

    def test_final_entry_bracket_refuses(self):
        with patch.object(effects.a,'check_entry',side_effect=[{'entry':'held'},RuntimeError('entry changed')]):
            self.refuse(Peer(positive()))
        self.assertEqual(self.proof()['failed_stage'],'entry_after')

    def test_source_direct_branch_and_failure_semantics(self):
        source=(D.parent/'astra-emu-fix/source/hw/usb/host-libusb.c').read_text()
        branch=source[source.index('if (s->match.addr && s->match.bus_num &&'):source.index('s->exit.notify =')]
        for fragment in ('!s->match.vendor_id','!s->match.product_id','!s->match.port','s->needs_autoscan = false',
                         'usb_host_find_ref','usb_host_open(s, ldev, 0)','if (!ldev)','if (rc < 0)',
                         'failed to find host usb device','failed to open host usb device'):
            self.assertIn(fragment,branch)
        opened=source[source.index('static int usb_host_open('):source.index('static int usb_host_close(')]
        for fragment in ('libusb_open(dev, &s->dh)','udev->speed = speed_map[libusb_speed]',
                         'usb_host_speed_compat(s)','usb_device_attach(udev, &local_err)','libusb_close(s->dh)'):
            self.assertIn(fragment,opened)
        self.assertLess(opened.index('usb_device_attach(udev, &local_err)'),opened.index('return 0;'))
        self.assertIn('if (runstate_is_running())',source)
        self.assertIn('udev->auto_attach = 0',source)

    def test_readonly_directory_flags(self):
        original=os.open;calls=[]
        def opened(path,flags,*args,**kwargs):
            calls.append((path,flags,kwargs));return original(path,flags,*args,**kwargs)
        with patch.object(usb.os,'open',side_effect=opened):self.run_positive()
        self.assertTrue(calls[0][1] & os.O_DIRECTORY)
        for path,flags,kw in calls:
            self.assertEqual(flags & os.O_ACCMODE,os.O_RDONLY)
            if not flags & os.O_DIRECTORY:self.assertIn('dir_fd',kw)

    def proof(self): return self.saved[effects.OUT+'usb-topology.json']

    def run_positive(self):
        q = Peer(positive()); self.fx.install(q,object(),self.ident)
        self.assertTrue(self.proof()['verdict']['qualified'])
        return q

    def refuse(self, q):
        with self.assertRaises((RuntimeError,OSError,ValueError)):
            self.fx.install(q,object(),self.ident)
        self.assertFalse(self.proof()['verdict']['qualified'])
        self.assertIn('failed_stage',self.proof())

    def test_positive_direct_result_and_order(self):
        q = self.run_positive()
        self.assertEqual(q.calls,['info usb','info qtree',('device_add',usb.direct_arguments(3,7)),'info usb','info qtree'])
        proof = self.proof()
        self.assertEqual([x['stage'] for x in proof['events']],usb.STAGES)
        self.assertEqual(self.guards,['native','entry']*3)
        for k in ('before','pre_qtree','after','qtree'): self.assertEqual(proof[k],positive()[k])
        self.assertEqual(proof['bus'],3);self.assertEqual(proof['address'],7)
        self.assertEqual(proof['sysfs'],str(self.pad))
        self.assertEqual(proof['verdict']['game_input'],'untested')
        self.assertTrue(usb.validate(proof)['qualified'])

    def test_host_instance_replaced_identical_text(self):
        q=Peer(positive())
        def replace():
            self.pad.rename(self.root/'removed')
            self.pad.mkdir()
            for p in (self.root/'removed').iterdir(): (self.pad/p.name).write_bytes(p.read_bytes())
        q.action=replace;self.refuse(q)
        self.assertEqual(self.proof()['failed_stage'],'physical_post_add')

    def test_symlink_retarget(self):
        link=self.root/'link';link.symlink_to(self.pad)
        self.fx.pre['usb'][0]['sysfs']=str(link)
        other=self.root/'other';other.mkdir()
        for p in self.pad.iterdir(): (other/p.name).write_bytes(p.read_bytes())
        q=Peer(positive())
        def replace(): link.unlink();link.symlink_to(other)
        q.action=replace;self.refuse(q)

    def test_denied_post_query(self):
        q=Peer(positive())
        def fail(n):
            if n==4: raise PermissionError('scripted qtree denied')
        q.hmp_action=fail;self.refuse(q)
        self.assertIn('after',self.proof());self.assertNotIn('qtree',self.proof())

    def test_directory_fd_closed_on_failure(self):
        closed=[];original=usb.PhysicalInstance.close
        def close(obj): closed.append(obj.fd);original(obj)
        with patch.object(usb.PhysicalInstance,'close',close):
            q=Peer(positive());q.reply=RuntimeError('scripted open failure');self.refuse(q)
        self.assertEqual(len(closed),1)
        with self.assertRaises(OSError):os.fstat(closed[0])

    def test_directory_fd_closed_on_success(self):
        closed=[];original=usb.PhysicalInstance.close
        def close(obj):closed.append(obj.fd);original(obj)
        with patch.object(usb.PhysicalInstance,'close',close):self.run_positive()
        with self.assertRaises(OSError):os.fstat(closed[0])

    def caller(self,cleanup_failure=False):
        owner=self
        class Caller(effects.LiveEffects):
            def launch(self): raise AssertionError('no launch')
            def existing(self): return self.authenticated_handle,owner.ident
            def authenticate(self,*args): owner.guards.append('authenticate')
            def open_q(self): return self.q
            def parity(self,*args): pass
            def open_r(self,*args): return self.r
            def load_title(self,*args): pass
            def observe(self,*args): raise AssertionError('observe after refusal')
            def capture(self,*args): raise AssertionError('capture after refusal')
            def accept(self,*args): raise AssertionError('takeover after refusal')
            def context(self,*args): owner.guards.append('context')
            def reauthenticate(self,*args): owner.guards.append('reauthenticate')
            def verify_release(self): owner.guards.append('release');return {'released':True}
            def record(self,result):
                owner.saved['caller']=result
                (owner.root/'caller-result.json').write_text(json.dumps(result,indent=2))
                (owner.root/'caller-boundary-order.json').write_text(json.dumps(dict(guards=owner.guards,qmp=self.q.calls),indent=2))
        fx=object.__new__(Caller);fx.__dict__.update(self.fx.__dict__)
        fx.q=Peer(HIST)
        def command(name,**args):
            fx.q.calls.append((name,args))
            if name=='quit':
                owner.guards.append('quit')
                if cleanup_failure: raise RuntimeError('scripted cleanup quit failure')
            return {}
        fx.q.cmd=command
        class Rsp:
            def close(self):owner.guards.append('rsp_close')
        fx.r=Rsp()
        with patch.object(effects.a,'close_q',side_effect=lambda q:owner.guards.append('qmp_close')):
            result=runtime_session.run_session(fx,existing=True)
        self.assertEqual(result['first_failed_link'],'install_and_topology')
        self.assertFalse(result['module']);self.assertFalse(result['healthy'])
        self.assertEqual(self.guards[-6:],['context','reauthenticate','quit','rsp_close','qmp_close','release'])
        self.assertTrue(result['clients_closed']);self.assertTrue(result['remaining_resources']['released'])
        self.assertEqual([c[0] for c in fx.q.calls if isinstance(c,tuple)],['device_add','quit'])
        return result

    def test_existing_run_session_refusal_cleanup(self):self.caller()
    def test_existing_run_session_cleanup_failure_preserved(self):self.assertIn('quit_error',self.caller(True))

def add_cases():
    for name,change in MUTATIONS.items():
        def test(self,change=change,name=name):
            c=positive();change(c);q=Peer(c);self.refuse(q)
            if name.startswith('stale_') or name.startswith('tree_'):
                self.assertFalse(any(isinstance(c,tuple) for c in q.calls))
        setattr(InstallTests,'test_raw_'+name,test)
    for field,value in [('idVendor','ffff'),('idProduct','ffff'),('busnum','4'),('devnum','8'),('speed','480'),('speed','?')]:
        def test(self,field=field,value=value):
            (self.pad/field).write_text(value);self.refuse(Peer(positive()))
        setattr(InstallTests,'test_physical_'+field+'_'+value.replace('?','unknown'),test)
    for field in ('speed','idVendor','devnum'):
        def test(self,field=field):
            (self.pad/field).unlink();self.refuse(Peer(positive()))
        setattr(InstallTests,'test_missing_physical_'+field,test)
    for speed in ('1.5','480','?'):
        def test(self,speed=speed):
            (self.pad/'speed').write_text(speed);self.fx.pre['usb'][0]['speed']=speed
            self.refuse(Peer(positive()))
            self.assertEqual(self.proof()['verdict']['host_reported_speed'],speed)
        setattr(InstallTests,'test_host_emulated_disagreement_'+speed.replace('.','_').replace('?','unknown'),test)
    for name,value in [('none',None),('wire_envelope',{'return':{}}),('list',[]),('find',RuntimeError('failed to find host usb device')),('open',RuntimeError('failed to open host usb device')),('attach',RuntimeError('failed to attach host usb device'))]:
        def test(self,value=value):
            q=Peer(positive());q.reply=value;self.refuse(q)
            if isinstance(value,Exception):
                self.assertEqual(self.proof()['failed_stage'],'request')
                self.assertNotIn('after',self.proof())
                self.assertNotIn('request',[x['stage'] for x in self.proof()['events']])
        setattr(InstallTests,'test_client_result_'+name,test)
    for name in ('hash','event_hash','order','session','time','native','filtered_arguments','forged_handle','stale_before','raw_event','tuple'):
        def test(self,name=name):
            self.run_positive();p=copy.deepcopy(self.proof());p.pop('verdict')
            events={x['stage']:x for x in p['events']}
            if name=='hash':p['after']+='corrupt'
            elif name=='event_hash':events['after']['sha256']='bad'
            elif name=='order':p['events'][0],p['events'][1]=p['events'][1],p['events'][0]
            elif name=='session':events['after']['identity']['invocation_id']='stale'
            elif name=='time':events['after']['end_monotonic_ns']=0
            elif name=='native':events['native_after']['value']['start_ticks']+=1
            elif name=='filtered_arguments':events['request']['value']['arguments']['vendorid']=1118
            elif name=='forged_handle':
                p['handle_nonnull']=True;events['request']['value']['result']=None
            elif name=='stale_before':events['before']['value']+=TARGET_ROW
            elif name=='raw_event':p['qtree']+='unbound raw edit'
            elif name=='tuple':p['address']=8
            if name not in ('hash','event_hash'):
                for event in p['events']:event['sha256']=usb.digest(event['value'])
            if name!='hash':p['binding_sha256']=usb.digest({k:v for k,v in p.items() if k!='binding_sha256'})
            self.assertFalse(usb.validate(p)['qualified'])
            (self.root/'tampered-receipt.json').write_text(json.dumps(p,indent=2))
        setattr(InstallTests,'test_receipt_'+name,test)
add_cases()

if __name__ == '__main__': unittest.main()
