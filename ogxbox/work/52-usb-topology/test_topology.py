"""Labelled derived fixtures exercise production checker, never emulator code."""
import copy
import json
from pathlib import Path
import unittest
from topology_check import check, digest, text_hash

O=Path(__file__).resolve().parent
L=O.parent/'45-x11-runtime-capture/post-entry-49/live'
ORIGINAL=json.loads((L/'usb-topology.json').read_bytes())
IDENTITY=json.loads((O/'capture-identity.json').read_text())
SELECTOR=json.loads((O/'target-selector.json').read_text())
MATRIX=[]


def fixture(full=False, opened=False):
    c=copy.deepcopy(ORIGINAL); s=copy.deepcopy(SELECTOR); i=copy.deepcopy(IDENTITY)
    s['capture_id']=i['capture_id']='DERIVED-fixture-not-runtime'
    if full:
        c['after']=c['after'].replace('Port 1.4, Speed 1.5','Port 1.4, Speed 12')
        c['qtree']=c['qtree'].replace('port 1.4, speed 1.5, name USB Host Device', 'port 1.4, speed 12, name USB Host Device, attached')
    if opened:
        i['host_open']={k:s[k] for k in ('capture_id','controller','bus','busnr','port','node_id','hostbus','hostaddr','vendorid','productid')}
        i['host_open'].update({k:i[k] for k in ('boot_id','pid','start_ticks','invocation_id')})
        i['host_open'].update(method='same-sample-handle-snapshot',source='DERIVED synthetic handle observation, NOT real evidence',handle_nonnull=True)
    return c,s,i


def run_fixture(c,s,i):
    raw=(json.dumps(c,indent=2)+'\n').encode()
    i.update(capture_sha256=digest(raw),listing_sha256=text_hash(c['after']),qtree_sha256=text_hash(c['qtree']))
    if i.get('host_open'):
        i['host_open']['capture_sha256']=i['capture_sha256']
    return check(c,s,i,raw)


class TopologyTests(unittest.TestCase):
    def record(self,r,join,qualified=False):
        self.assertEqual(r['join'],join)
        self.assertEqual(r['qualifies_full_speed_host_open'],qualified)
        self.assertIs(r['working_game_pad'],False)
        if join=='unique':
            self.assertEqual(r['target_row']['node_id'],'pt_pad3')
            self.assertEqual(r['target_row']['port'],'1.4')
            self.assertEqual(r['target_row']['busnr'],1)
            self.assertIn('ID: pt_pad3',r['target_row']['raw'])
            self.assertEqual(r['target_node']['node_id'],'pt_pad3')
            self.assertEqual(r['target_node']['controller'],'00:02.0')
        MATRIX.append(dict(case=self._testMethodName,derived=self._testMethodName!='test_original',join=r['join'],qualification=r['qualifies_full_speed_host_open'],speed=r['speed_label'],host_open=r['host_open'],reasons=r['reasons'],row=r['target_row']))

    def test_original(self):
        raw=(L/'usb-topology.json').read_bytes()
        r=check(ORIGINAL,SELECTOR,IDENTITY,raw); self.record(r,'unique')
        self.assertEqual(r['target_row']['line'],4)
        self.assertEqual(r['speed_label']['mbps'],'1.5')
        self.assertEqual(r['host_open']['verdict'],'unknown')
        self.assertEqual(r['logical_port']['configured_xbox_connector'],2)

    def test_unique_full_speed_positive(self):
        r=run_fixture(*fixture(True,True));self.record(r,'unique',True)
        self.assertEqual(r['speed_label']['mbps'],'12')
        self.assertEqual(r['host_open']['verdict'],'confirmed')

    def test_reordered_rows_nodes(self):
        c,s,i=fixture(True,True)
        c['after']='\r\n'.join(reversed(c['after'].splitlines()))+'\r\n'
        lines=c['qtree'].splitlines(keepends=True)
        start=next(n for n,l in enumerate(lines) if 'dev: usb-host, id "pt_pad3"' in l)
        end=next(n for n in range(start+1,len(lines)) if 'dev: usb-xbox-gamepad' in lines[n])
        finish=next(n for n in range(end+1,len(lines)) if 'dev: usb-hub' in lines[n])
        lines[start:finish]=lines[end:finish]+lines[start:end]
        c['qtree']=''.join(lines)
        r=run_fixture(c,s,i);self.record(r,'unique',True)
        self.assertEqual(r['target_row']['line'],1)
        self.assertEqual(r['target_row']['raw'],c['after'].splitlines()[0])

    def test_missing_target(self):
        c,s,i=fixture();c['after']='\n'.join(l for l in c['after'].splitlines() if 'pt_pad3' not in l)
        self.record(run_fixture(c,s,i),'invalid')

    def test_duplicate_listing(self):
        c,s,i=fixture();c['after']+=c['after'].splitlines()[-1]+'\n'
        self.record(run_fixture(c,s,i),'invalid')

    def test_duplicate_node_id(self):
        c,s,i=fixture();c['qtree']+='\n          dev: usb-host, id "pt_pad3"\n            port = "2"\n'
        self.record(run_fixture(c,s,i),'invalid')

    def test_colliding_listing_path(self):
        c,s,i=fixture();c['after']+='  Device 1.9, Port 1.4, Speed 12 Mb/s, Product Other, ID: other\n'
        self.record(run_fixture(c,s,i),'invalid')

    def test_colliding_qtree_path(self):
        c,s,i=fixture();needle='          dev: usb-host, id "pt_pad3"'
        c['qtree']=c['qtree'].replace(needle,'          dev: usb-host, id "other"\n            port = "1.4"\n'+needle)
        self.record(run_fixture(c,s,i),'invalid')

    def test_stale_target(self):
        c,s,i=fixture();c['before']=c['after']
        self.record(run_fixture(c,s,i),'invalid')

    def test_stale_identity(self):
        c,s,i=fixture();s['capture_id']='another-interval'
        self.record(run_fixture(c,s,i),'invalid')

    def test_tampered_capture(self):
        c,s,i=fixture();run_fixture(c,s,i)
        raw=json.dumps(c).encode();i['capture_sha256']='0'*64
        self.record(check(c,s,i,raw),'invalid')

    def test_low_speed_full_speed_neighbor(self):
        r=run_fixture(*fixture(False,True));self.record(r,'unique')
        self.assertEqual(r['target_row']['speed'],'1.5')
        self.assertEqual(r['host_open']['verdict'],'unknown')  # not attached
        self.assertNotIn('gamepad_0',r['target_row']['raw'])

    def test_full_speed_unknown_open(self):
        r=run_fixture(*fixture(True));self.record(r,'unique')
        self.assertTrue(r['speed_label']['full_speed'])
        self.assertEqual(r['host_open']['verdict'],'unknown')

    def test_host_selector_mismatch(self):
        c,s,i=fixture();s['hostaddr']=8
        self.record(run_fixture(c,s,i),'invalid')

    def test_wrong_controller(self):
        c,s,i=fixture();s['controller']='00:03.0'
        self.record(run_fixture(c,s,i),'invalid')

    def test_wrong_bus(self):
        c,s,i=fixture();s['bus']='usb-bus.0'
        self.record(run_fixture(c,s,i),'invalid')

    def test_qtree_speed_mismatch(self):
        c,s,i=fixture();c['after']=c['after'].replace('Port 1.4, Speed 1.5','Port 1.4, Speed 12')
        self.record(run_fixture(c,s,i),'invalid')

    def test_stale_open(self):
        c,s,i=fixture(True,True);i['host_open']['pid']+=1
        r=run_fixture(c,s,i);self.record(r,'unique')
        self.assertEqual(r['host_open']['verdict'],'unknown')

    def test_missing_intermediary(self):
        c,s,i=fixture();c['qtree']=c['qtree'].replace('port = "1"','port = "9"')
        self.record(run_fixture(c,s,i),'invalid')

    def test_null_open(self):
        c,s,i=fixture(True,True);i['host_open']['handle_nonnull']=False
        r=run_fixture(c,s,i);self.record(r,'unique')
        self.assertEqual(r['host_open']['verdict'],'not-open')


if __name__=='__main__':
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(TopologyTests)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    (O/'test-matrix.json').write_text(json.dumps(dict(derived_tests_are_not_runtime=True,tests_run=result.testsRun,failures=len(result.failures),errors=len(result.errors),matrix=MATRIX),indent=2)+'\n')
    raise SystemExit(0 if result.wasSuccessful() else 1)
