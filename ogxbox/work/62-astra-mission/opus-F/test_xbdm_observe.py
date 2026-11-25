#!/usr/bin/env python3
"""Offline tests for xbdm_observe.py / analyze_run.py.  Loopback fake only; no console, no emulator.

Run from opus-F/:  /usr/bin/python3 -B -m unittest -v test_xbdm_observe
"""
import hashlib
import json
import os
import shutil
import struct
import sys
import tempfile
import threading
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import analyze_run as ar          # noqa: E402
import ftplib                     # noqa: E402
import stage_ftp as sf            # noqa: E402
import xbdm_observe as xo         # noqa: E402
from fake_xbdm import FakeXbdm    # noqa: E402

PINS, PINS_SHA = xo.load_pins(xo.DEFAULT_PINS)
TS = int(PINS['title']['timestamp'], 16)
ENUM_BASE = int(PINS['enum']['poll_region']['addr'], 16)
ENUM_LEN = int(PINS['enum']['poll_region']['len'], 16)
MOD_OFF = PINS['trainer']['module_offset_from_resident']
MOD_SIZE = PINS['trainer']['module_size']
STATUS_OFF = PINS['trainer']['status_offsets']['attached']
XBE = 'F:\\Games\\h2u803\\default.xbe'
XDIR = 'F:\\Games\\h2u803'
KERNEL_MZ = b'MZ' + bytes(0x3e)
FORBIDDEN_SEEN = ('stop', 'go', 'continue', 'reboot', 'setmem', 'halt', 'debugger', 'setcontext', 'break',
                  'suspend', 'resume', 'sendfile', 'getfile')


def _header():
    with open(PINS['title']['xbe_local'], 'rb') as f:
        h = f.read(0x104)
    assert hashlib.sha256(h[4:260]).hexdigest() == PINS['title']['header_signature_sha256']
    return h


HEADER = _header()


def title_regions(resident=None, odd_site=None, header=None, enum=None, attached=1, hooks=191, failed=0):
    regs = {0x10000: header or HEADER, 0x80010000: KERNEL_MZ}
    if isinstance(enum, dict):
        regs.update(enum)
    else:
        regs[ENUM_BASE] = enum or bytes(ENUM_LEN)
    for name, s in PINS['hook_sites'].items():
        va = int(s['va'], 16)
        stock = bytes.fromhex(s['stock_hex'])
        if resident is None:
            b = stock
        else:
            r = resident + 0x1000 if name == odd_site else resident
            rel = (r + s['resident_offset'] - (va + 5)) & 0xffffffff
            b = b'\xe9' + struct.pack('<I', rel) + stock[5:]
        regs[va] = b
    if resident is not None:
        mod = bytearray(MOD_SIZE)
        struct.pack_into('<III', mod, STATUS_OFF, attached, hooks, failed)
        regs[resident + MOD_OFF] = bytes(mod)
    return regs


def title_threads():
    return {
        28: {'info': {'suspend': 0, 'priority': 8, 'tlsbase': 0xd0010000, 'start': 0x1c2e0,
                      'base': 0xd0011000, 'limit': 0xd000c000},
             'stopped': None, 'ctx': {'Eip': 0x416568, 'Esp': 0xd0010f00, 'Ebp': 0xd0010f40, 'EFlags': 0x246,
                                      'Eax': 0x8000058c}},
        32: {'info': {'suspend': 0, 'priority': 16, 'tlsbase': 0xd0020000, 'start': 0x80031000,
                      'base': 0xd0021000, 'limit': 0xd001f000},
             'stopped': None, 'ctx': {'Eip': 0x80031234, 'Esp': 0xd0020e00, 'Ebp': 0xd0020e40, 'EFlags': 0x202,
                                      'Eax': 0}}}


def title_xbe():
    return {'timestamp': TS, 'checksum': 0x1234, 'name': 'default.xbe'}


class Out:
    def __init__(self):
        self.lock = threading.Lock()
        self.buf = ''
        self.lines = []
        self.waiters = {}

    def write(self, s):
        with self.lock:
            self.buf += s
            while '\n' in self.buf:
                ln, self.buf = self.buf.split('\n', 1)
                self.lines.append(ln)
                for pat, ev in self.waiters.items():
                    if ln.startswith(pat):
                        ev.set()

    def flush(self):
        pass

    def wait_for(self, pat):
        ev = threading.Event()
        with self.lock:
            self.waiters[pat] = ev
            if any(l.startswith(pat) for l in self.lines):
                ev.set()
        return ev


def jl(path):
    with open(path) as f:
        return [json.loads(l) for l in f if l.strip()]


def jload(path):
    with open(path) as f:
        return json.load(f)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='test-run-', dir=HERE)
        self.fakes = []

    def tearDown(self):
        for f in self.fakes:
            f.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def fake(self, **kw):
        f = FakeXbdm(**kw)
        self.fakes.append(f)
        return f

    def run_tool(self, port, args, out=None):
        out = out or Out()
        argv = [str(x) for x in args] + ['--ip', '127.0.0.1', '--port', str(port), '--out-root', self.tmp]
        return xo.main(argv, out), out

    def rd(self, n):
        return os.path.join(self.tmp, 'run-%d' % n)

    def receipt(self, **over):
        rc = {'console_path': XBE, 'sha256': PINS['title']['xbe_sha256'], 'size': PINS['title']['xbe_size'],
              'verified_epoch': time.time()}
        rc.update(over)
        p = os.path.join(self.tmp, 'receipt-%d.json' % len(os.listdir(self.tmp)))
        with open(p, 'w') as f:
            json.dump(rc, f)
        return p

    def assert_no_forbidden(self, fake):
        for v in fake.verbs():
            self.assertNotIn(v, FORBIDDEN_SEEN)
            self.assertIn(v, xo.READ_ONLY_VERBS | {'magicboot'})


class T01Probe(Base):
    def test_01_probe_dashboard_only_shapes_true_and_readonly_verbs(self):
        f = self.fake(regions={0x80010000: KERNEL_MZ}, xbeinfo=None)
        code, out = self.run_tool(f.port, ['probe', '--run', 1, '--shot'])
        self.assertEqual(code, 0, out.lines)
        p = jload(os.path.join(self.rd(1), 'probe.json'))
        self.assertTrue(p['shapes_ok'], p)
        for k, v in p['shapes_ok'].items():
            self.assertTrue(v, k)
        self.assertEqual(set(p['shapes_ok']), {'banner', 'dmversion', 'xbeinfo', 'modules', 'systime', 'threads',
                                               'threadinfo', 'isstopped', 'getcontext', 'getmem', 'notify',
                                               'screenshot'})
        self.assertTrue(set(f.verbs()) <= xo.READ_ONLY_VERBS, f.verbs())


class T02VerbGate(Base):
    FORBIDDEN = ['stop', 'go', 'continue', 'reboot', 'reboot warm', 'halt', 'setmem addr=0x10000 data=00',
                 'setcontext thread=28 Eip=0x0', 'break addr=0x416568', 'suspend thread=28', 'resume thread=28',
                 'debugger connect', 'sendfile name="E:\\x" length=0x1', 'getfile name="E:\\x"',
                 'delete name="E:\\x"', 'rename name="E:\\a" newname="E:\\b"', 'mkdir name="E:\\x"', 'frobnicate',
                 'notifyat port=731', 'magicboot title="E:\\a.xbe" directory="E:\\"', 'dmversion\r\nstop']

    def test_02a_forbidden_verbs_raise_before_any_byte(self):
        f = self.fake()
        c = xo.Conn('127.0.0.1', f.port, xo.Policy('observe'), None)
        for cmd in self.FORBIDDEN:
            with self.assertRaises(xo.Refused, msg=cmd):
                c.command(cmd)
        time.sleep(0.2)
        self.assertEqual(f.bytes_received, 0)
        self.assertEqual(c.command('dmversion').status, '200- 1.00.5455.1')
        time.sleep(0.1)
        self.assertEqual(f.commands(), ['dmversion'])
        self.assertEqual(f.bytes_received, len('dmversion\r\n'))
        c.close()

    def test_02b_magicboot_once_never_debug_or_cold(self):
        p = xo.Policy('launch-observe')
        for bad in ('magicboot title="E:\\a.xbe" directory="E:\\" debug',
                    'magicboot title="E:\\a.xbe" directory="E:\\" cold',
                    'magicboot title="E:\\a.xbe" directory="E:\\" DEBUG',
                    'magicboot title="E:\\a.xbe"'):
            with self.assertRaises(xo.Refused):
                p.check(bad)
        self.assertEqual(p.check('magicboot title="F:\\DEVKIT\\debug cold\\default.xbe" directory="F:\\x"'),
                         'magicboot')
        with self.assertRaises(xo.Refused):
            p.check('magicboot title="E:\\a.xbe" directory="E:\\"')
        with self.assertRaises(xo.Refused):
            xo.Policy('observe').check('magicboot title="E:\\a.xbe" directory="E:\\"')

    def _grant(self, **kw):
        g = {'verb': 'reboot warm', 'run': 7, 'issued_by': 'parent', 'issued_epoch': time.time()}
        g.update(kw)
        p = os.path.join(self.tmp, 'grant-%d.json' % len(os.listdir(self.tmp)))
        with open(p, 'w') as fh:
            json.dump(g, fh)
        return p

    def test_02c_recover_valid_grant_sends_exactly_one_command(self):
        for verb in ('reboot warm', 'stop', 'reboot'):
            f = self.fake()
            code, out = self.run_tool(f.port, ['recover', '--run', 7, '--grant', self._grant(verb=verb)])
            self.assertEqual(code, 0, out.lines)
            time.sleep(0.1)
            self.assertEqual(f.commands(), [verb])

    def test_02d_recover_bad_grants_send_nothing(self):
        cases = {'expired': self._grant(issued_epoch=time.time() - 1000), 'wrong_run': self._grant(run=8),
                 'wrong_verb': self._grant(verb='go'), 'wrong_verb_setmem': self._grant(verb='setmem'),
                 'not_parent': self._grant(issued_by='worker'),
                 'missing': os.path.join(self.tmp, 'no-such-grant.json')}
        for name, g in cases.items():
            f = self.fake()
            code, out = self.run_tool(f.port, ['recover', '--run', 7, '--grant', g])
            time.sleep(0.05)
            self.assertEqual(code, 2, name)
            self.assertEqual(f.connections, 0, name)
            self.assertEqual(f.commands(), [], name)


class T03LaunchRefusals(Base):
    def test_03_launch_observe_receipt_refusals_no_connection(self):
        cases = {
            'missing': os.path.join(self.tmp, 'nope.json'),
            'wrong_sha': self.receipt(sha256='00' * 32),
            'wrong_size': self.receipt(size=PINS['title']['xbe_size'] + 1),
            'path_mismatch': self.receipt(console_path='F:\\Games\\Halo 2 HD 1.5 480p\\default.xbe'),
            'stale': self.receipt(verified_epoch=time.time() - 7 * 3600),
        }
        for i, (name, rc) in enumerate(cases.items()):
            f = self.fake()
            code, out = self.run_tool(f.port, ['launch-observe', '--run', 30 + i, '--xbe', XBE, '--dir', XDIR,
                                               '--identity', rc])
            time.sleep(0.05)
            self.assertEqual(code, 2, name)
            self.assertEqual(f.connections, 0, name)
            self.assertFalse(os.path.exists(self.rd(30 + i)), name)


def _boot_title(regions_fn, threads_fn=title_threads):
    def after(fk):
        fk.regions = {b: bytearray(v) for b, v in regions_fn().items()}
        fk.xbeinfo = title_xbe()
        fk.threads = threads_fn()
    return after


class T04LaunchOff(Base):
    def test_04_launch_observe_off_path_one_magicboot_reconnect_bh(self):
        f = self.fake(regions={0x80010000: KERNEL_MZ}, xbeinfo=None, reboot_s=0.4,
                      after_boot=_boot_title(lambda: title_regions()))
        code, out = self.run_tool(f.port, ['launch-observe', '--run', 4, '--xbe', XBE, '--dir', XDIR,
                                           '--identity', self.receipt(), '--duration', '3', '--cadence-ms', '20',
                                           '--shot-every', '0', '--wait-title', '10'])
        self.assertEqual(code, 0, out.lines)
        mb = [c for c in f.commands() if c.lower().startswith('magicboot')]
        self.assertEqual(len(mb), 1)
        self.assertNotIn('debug', mb[0].lower().replace(XBE.lower(), '').replace(XDIR.lower(), ''))
        self.assertNotIn('cold', mb[0].lower())
        self.assertGreater(f.connections, 1)
        self.assert_no_forbidden(f)
        g = jload(os.path.join(self.rd(4), 'title-gate.json'))
        self.assertEqual((g['identity'], g['trainer_state']), ('MATCH', 'OFF'))
        self.assertIsNotNone(g['ms_since_launch'])
        self.assertIn('GATE OFF hooks=0 failed=0', out.lines)
        s = jl(os.path.join(self.rd(4), 'samples.jsonl'))
        self.assertGreaterEqual(len(s), 100)
        d = sorted((b['mono_ns'] - a['mono_ns']) / 1e6 for a, b in zip(s, s[1:]))
        self.assertTrue(15 <= d[len(d) // 2] <= 30, d[len(d) // 2])
        self.assertEqual(ar.analyze(self.rd(4))['class'], 'B-H')


class T05On(Base):
    def test_05a_on_consistent_sites_other_base(self):
        res = 0x83a40000                                  # W59 resident was 0x83fd7000
        f = self.fake(regions=title_regions(resident=res), xbeinfo=title_xbe(), threads=title_threads())
        code, out = self.run_tool(f.port, ['observe', '--run', 5, '--attach-now', '--duration', '1',
                                           '--cadence-ms', '50', '--shot-every', '0'])
        self.assertEqual(code, 0, out.lines)
        g = jload(os.path.join(self.rd(5), 'title-gate.json'))
        self.assertEqual(g['trainer_state'], 'ON')
        self.assertEqual(g['resident'], '0x%x' % res)
        self.assertEqual(g['module'], '0x%x' % (res + MOD_OFF))
        self.assertEqual(g['trainer_status']['attached'], 1)
        self.assertEqual(g['trainer_status']['installed_hooks'], 191)
        self.assertEqual(g['trainer_status']['install_failed'], 0)
        self.assertTrue(all(v['state'] == 'HOOKED' for v in g['sites'].values()))
        self.assertEqual(os.path.getsize(os.path.join(self.rd(5), 'module-000.bin')), MOD_SIZE)
        self.assertIn('GATE ON hooks=191 failed=0', out.lines)
        self.assert_no_forbidden(f)

    def test_05b_one_site_other_base_inconsistent_analyzer_x(self):
        f = self.fake(regions=title_regions(resident=0x83a40000, odd_site='XInputGetState'), xbeinfo=title_xbe(),
                      threads=title_threads())
        code, out = self.run_tool(f.port, ['observe', '--run', 6, '--attach-now', '--duration', '2.5',
                                           '--cadence-ms', '20', '--shot-every', '0'])
        self.assertEqual(code, 0, out.lines)
        g = jload(os.path.join(self.rd(6), 'title-gate.json'))
        self.assertEqual(g['trainer_state'], 'INCONSISTENT')
        self.assertFalse(os.path.exists(os.path.join(self.rd(6), 'module-000.bin')))
        self.assertEqual(ar.analyze(self.rd(6))['class'], 'X')


class T06Identity(Base):
    def test_06_identity_mismatch_same_timestamp_exit2_no_observation(self):
        h = bytearray(HEADER)
        h[10] ^= 0xff
        f = self.fake(regions=title_regions(header=bytes(h)), xbeinfo=title_xbe(), threads=title_threads())
        code, out = self.run_tool(f.port, ['observe', '--run', 8, '--attach-now', '--duration', '2'])
        self.assertEqual(code, 2)
        g = jload(os.path.join(self.rd(8), 'title-gate.json'))
        self.assertEqual(g['identity'], 'MISMATCH')
        self.assertFalse(os.path.exists(os.path.join(self.rd(8), 'samples.jsonl')))
        self.assertEqual(ar.analyze(self.rd(8))['class'], 'X')


class T07Unreadable(Base):
    def test_07_unreadable_bytes_null_field_raw_preserved_never_zero(self):
        enum = {ENUM_BASE: bytes(0x7c), ENUM_BASE + 0x80: bytes(ENUM_LEN - 0x80)}   # pending (0x7c..0x7f) unmapped
        f = self.fake(regions=title_regions(enum=enum), xbeinfo=title_xbe(), threads=title_threads())
        code, out = self.run_tool(f.port, ['observe', '--run', 9, '--attach-now', '--duration', '0.5',
                                           '--shot-every', '0'])
        self.assertEqual(code, 0, out.lines)
        s = jl(os.path.join(self.rd(9), 'samples.jsonl'))[0]
        self.assertIsNone(s['fields']['pending'])
        self.assertEqual(s['fields']['current'], 0)
        self.assertEqual(s['raw_hex'][0x7c * 2:0x80 * 2], '????????')
        vals = xo.hex_to_vals('0102??04')
        self.assertEqual(vals, [1, 2, None, 4])
        self.assertIsNone(xo.v_u32(vals, 0))
        self.assertEqual(xo.vals_hex(vals), '0102??04')


class T08Fault(Base):
    def _check_fault(self, n, f, out, code):
        self.assertEqual(code, 3, out.lines)
        fj = jload(os.path.join(self.rd(n), 'fault', 'fault.json'))
        self.assertEqual(set(fj['threads']), {'28', '32'})
        for tid, t in fj['threads'].items():
            self.assertTrue(t['getcontext']['status'].startswith('202'), tid)
            self.assertIsNotNone(t['stack'])
            self.assertLessEqual(t['stack']['len'], 0x200)
            self.assertEqual(t['code']['len'], 0x40)
            self.assertEqual(t['code']['addr'], t['regs']['eip'] - 0x20)
        self.assertEqual(fj['threads']['28']['stack']['len'], 0x100)    # min(0x200, top - Esp)
        self.assertEqual(fj['fault_pc_class'], 'title')
        self.assertIsNotNone(fj['screenshot'])
        cmds = [c.lower() for c in f.commands()]
        for bad in ('stop', 'go', 'continue', 'reboot', 'setmem'):
            self.assertFalse(any(c.split()[0] == bad for c in cmds), bad)
        self.assertTrue(any(l.startswith('FAULT') for l in out.lines))
        r = ar.analyze(self.rd(n))
        self.assertEqual(r['class'], 'B-F')
        self.assertEqual(r['fault_pc_class'], 'title')

    def test_08a_thread_stopped_mid_run_fault_dump_exit3(self):
        f = self.fake(regions=title_regions(), xbeinfo=title_xbe(), threads=title_threads())
        threading.Timer(0.6, lambda: f.threads[28].__setitem__(
            'stopped', 'exception code=0xc0000005 address=0x416568 thread=28')).start()
        code, out = self.run_tool(f.port, ['observe', '--run', 10, '--attach-now', '--duration', '8',
                                           '--post-fault-seconds', '1', '--shot-every', '0'])
        self._check_fault(10, f, out, code)

    def test_08b_exception_notification_fault_exit3(self):
        f = self.fake(regions=title_regions(), xbeinfo=title_xbe(), threads=title_threads())
        threading.Timer(0.6, lambda: f.push_notification(
            'exception code=0xc0000005 thread=28 address=0x416568 first-chance')).start()
        code, out = self.run_tool(f.port, ['observe', '--run', 11, '--attach-now', '--duration', '8',
                                           '--post-fault-seconds', '1', '--shot-every', '0'])
        with open(os.path.join(self.rd(11), 'notifications.log')) as fh:
            self.assertIn('exception code=0xc0000005', fh.read())
        self._check_fault(11, f, out, code)


class T09Unreachable(Base):
    def test_09_unreachable_mid_run_exit5_within_budget(self):
        f = self.fake(regions=title_regions(), xbeinfo=title_xbe(), threads=title_threads())
        threading.Timer(0.8, lambda: f.set_down(True)).start()
        t0 = time.monotonic()
        code, out = self.run_tool(f.port, ['observe', '--run', 12, '--attach-now', '--duration', '20',
                                           '--unreachable-budget', '1.5', '--reconnect-fast-s', '0.5',
                                           '--shot-every', '0'])
        el = time.monotonic() - t0
        self.assertEqual(code, 5, out.lines)
        self.assertLess(el, 8.0)
        u = jload(os.path.join(self.rd(12), 'unreachable.json'))
        self.assertFalse(u['returned'])
        self.assertLessEqual(u['elapsed_ms'], 1500 + 1500)
        self.assertIn('UNREACHABLE', out.lines)
        self.assertEqual(ar.analyze(self.rd(12))['class'], 'X')


def w59_rows():
    with open(PINS['fixtures_w59']['trace'], 'rb') as fh:
        data = fh.read()
    assert hashlib.sha256(data).hexdigest() == PINS['fixtures_w59']['trace_sha256']
    return [json.loads(l) for l in data.splitlines() if l.strip()]


class T10DecoderW59(unittest.TestCase):
    def test_10_decoder_on_real_EMULATOR_w59_rows_matches_pins(self):
        rows = {r['seq']: r for r in w59_rows()}
        for k, want in PINS['fixtures_w59']['rows'].items():
            r = rows[int(k)]
            mem = r['raw_snapshot']['memory'][0]
            self.assertEqual(mem['address'], ENUM_BASE)
            vals = xo.hex_to_vals(mem['hex'])
            self.assertEqual(len(vals), want['len'], k)
            d = xo.decode_enum(vals, PINS)
            self.assertEqual(r['monotonic_ns'], want['mono_ns'], k)
            self.assertEqual(d['b0'], want['b0'], k)
            self.assertEqual(d['retry'], want['retry_b2'], k)
            self.assertEqual(d['marker'], want['marker_b3'], k)
            self.assertEqual(d['marker'], want['trace_marker'], k)
            self.assertEqual(d['timer_inserted'], want['timer_inserted_b53'], k)
            self.assertEqual(d['timer_hdr'], want['timer_hdr_hex'], k)
            self.assertEqual(d['duetime'], want['duetime_hex'], k)
            self.assertEqual('0x%x' % d['dpc_ptr'], want['dpc_ptr'], k)
            self.assertEqual('0x%x' % d['pending'], want['pending'], k)
            self.assertEqual('0x%x' % d['current'], want['current'], k)
            self.assertEqual(d['pending'], want['trace_pending'], k)
            self.assertEqual(d['current'], want['trace_current'], k)
            self.assertIsNone(d['node_pool_ptr'])        # outside the 0x84 block: unknown, not zero


def write_run(rd, state, samples, status=None, mark=None, exit_code=0, identity='MATCH'):
    os.makedirs(rd)
    gate = {'status': 'PASS' if identity == 'MATCH' else identity, 'identity': identity, 'trainer_state': state,
            'trainer_status': status}
    with open(os.path.join(rd, 'title-gate.json'), 'w') as f:
        json.dump(gate, f)
    with open(os.path.join(rd, 'manifest.json'), 'w') as f:
        json.dump({'mark': mark}, f)
    with open(os.path.join(rd, 'summary.json'), 'w') as f:
        json.dump({'exit_code': exit_code, 'unreachable_episodes': []}, f)
    with open(os.path.join(rd, 'samples.jsonl'), 'w') as f:
        for s in samples:
            f.write(json.dumps(s) + '\n')


QUIET = {'b0': 0, 'retry': 0, 'marker': 10, 'timer_inserted': 0, 'duetime': '00' * 8, 'pending': 0, 'current': 0,
         'timer_hdr': '08010a00', 'dpc_ptr': 0x4908e4, 'node_pool_ptr': 0, 'state_word': 0}


def synth(n, status=None, busy=None, step_ns=50 * 10**6):
    out = []
    for i in range(n):
        f = dict(QUIET)
        if busy:
            f.update(busy(i) or {})
        s = {'seq': i + 1, 'mono_ns': 10**12 + i * step_ns, 'fields': f}
        if status is not None:
            s['status'] = dict(status)
        out.append(s)
    return out


class T11AnalyzerW59(Base):
    def test_11_analyzer_on_real_EMULATOR_w59_sequence_is_RF(self):
        st = {'attached': 1, 'installed_hooks': 191, 'install_failed': 0}
        samples = []
        for r in w59_rows():
            mem = (r.get('raw_snapshot') or {}).get('memory') or []
            if not mem:
                continue
            samples.append({'seq': r['seq'], 'mono_ns': r['monotonic_ns'],
                            'fields': xo.decode_enum(xo.hex_to_vals(mem[0]['hex']), PINS), 'status': st})
        self.assertEqual(len(samples), 227)
        rd = os.path.join(self.tmp, 'w59')
        write_run(rd, 'ON', samples, status=st, mark='W59 EMULATOR replay ON')
        r = ar.analyze(rd)
        self.assertTrue(r['stuck_record'], r['records'])
        self.assertTrue(r['orphan_timer'], r['orphan_events'])
        self.assertEqual(r['class'], 'R-F')


class T12AnalyzerSynthetic(Base):
    ON_OK = {'attached': 1, 'installed_hooks': 191, 'install_failed': 0}

    def _cls(self, name, state, samples, **kw):
        rd = os.path.join(self.tmp, name)
        write_run(rd, state, samples, **kw)
        return ar.analyze(rd)

    def test_12a_RH(self):
        self.assertEqual(self._cls('rh', 'ON', synth(300, self.ON_OK), status=self.ON_OK, mark='ON')['class'], 'R-H')

    def test_12b_RH_slow_attach_long_dwell_is_reported_not_failure(self):
        busy = lambda i: {'current': 0x8000058c, 'retry': 5, 'b0': 1} if 10 <= i < 100 else None  # 4.5 s dwell
        r = self._cls('rhs', 'ON', synth(400, self.ON_OK, busy), status=self.ON_OK, mark='ON')
        self.assertTrue(r['long_dwell'])
        self.assertFalse(r['stuck_record'])
        self.assertEqual(r['class'], 'R-H')

    def test_12c_RA(self):
        st = dict(self.ON_OK, attached=0)
        self.assertEqual(self._cls('ra', 'ON', synth(300, st), status=st, mark='ON')['class'], 'R-A')

    def test_12d_RT(self):
        self.assertEqual(self._cls('rt', 'OFF', synth(300), mark='trainer ON')['class'], 'R-T')

    def test_12e_BH(self):
        self.assertEqual(self._cls('bh', 'OFF', synth(300), mark='baseline OFF')['class'], 'B-H')

    def test_12f_BF_stuck_record(self):
        busy = lambda i: {'current': 0x8000058c, 'retry': 5 - i // 5, 'b0': 1} if i < 20 else None
        r = self._cls('bf', 'OFF', synth(300, None, busy), mark='baseline OFF')
        self.assertTrue(r['stuck_record'])
        self.assertEqual(r['class'], 'B-F')

    def test_12g_X_too_few_samples(self):
        r = self._cls('x', 'OFF', synth(50), mark='baseline OFF')
        self.assertEqual(r['class'], 'X')
        self.assertIn('too few', ' '.join(r['reasons']))


class T13Exclusive(Base):
    def test_13_run_dir_exclusive_manifest_hashes(self):
        f = self.fake(regions={0x80010000: KERNEL_MZ})
        code, _ = self.run_tool(f.port, ['probe', '--run', 13])
        self.assertEqual(code, 0)
        n = f.connections
        code2, out2 = self.run_tool(f.port, ['probe', '--run', 13])
        self.assertEqual(code2, 2)
        self.assertEqual(f.connections, n)
        self.assertTrue(any(l.startswith('REFUSED run directory exists') for l in out2.lines))
        m = jload(os.path.join(self.rd(13), 'manifest.json'))
        self.assertEqual(m['tool_sha256'], xo.sha256_file(xo.__file__))
        self.assertEqual(m['pins_sha256'], PINS_SHA)
        self.assertEqual(PINS_SHA, 'a34d3deac8feb3ee4e4a33c9e63c032268ac727c3b420e39e756ae29b1317079')


class T14HotAdd(Base):
    def test_14_hot_add_quiescent_mark_attached_module_change_RH(self):
        res = 0x83b00000
        mod = res + MOD_OFF
        f = self.fake(regions=title_regions(resident=res, attached=0), xbeinfo=title_xbe(), threads=title_threads())
        out = Out()
        q = out.wait_for('QUIESCENT')
        box = {}
        th = threading.Thread(target=lambda: box.update(code=self.run_tool(
            f.port, ['observe', '--run', 14, '--attach-now', '--duration', '14', '--cadence-ms', '50',
                     '--shot-every', '0', '--module-hz', '2', '--mark', 'hot-add ON'], out)[0]))
        th.start()
        self.assertTrue(q.wait(13), out.lines)
        with open(os.path.join(self.rd(14), 'marks.in'), 'a') as fh:
            fh.write('ASK_SENT\n')
        time.sleep(0.4)
        f.set_mem(mod + STATUS_OFF, struct.pack('<I', 1))
        f.set_mem(mod, b'\x55\xaa')
        th.join(30)
        self.assertEqual(box.get('code'), 0, out.lines)
        self.assertIn('ATTACHED 0->1', out.lines)
        self.assertTrue(any(l.startswith('MODULE_CHANGED k=1') for l in out.lines), out.lines)
        self.assertTrue(os.path.exists(os.path.join(self.rd(14), 'module-001.bin')))
        marks = jl(os.path.join(self.rd(14), 'marks.jsonl'))
        self.assertEqual([m['text'] for m in marks], ['ASK_SENT'])
        r = ar.analyze(self.rd(14))
        self.assertEqual(r['class'], 'R-H', r['reasons'])
        self.assertGreater(r['attached_first_mono_ns'], marks[0]['mono_ns'])
        self.assertTrue(r['marks'][0]['attached_first_after_mark'])
        self.assert_no_forbidden(f)


class MockFTP:
    """In-memory FTP double: only the methods stage_ftp may use. delete/rename/rmd/mkd do not exist."""
    instances = []

    def __init__(self, files=None, corrupt=False):
        self.files = dict(files or {})        # '/F/Games/h2/default.xbe' -> bytes
        self.cwd_path = '/'
        self.corrupt = corrupt
        self.calls = []
        self.login_args = None
        MockFTP.instances.append(self)

    def connect(self, host, port, timeout=None):
        self.calls.append(('connect', host, port))

    def login(self, user, pw):
        self.login_args = (user, pw)
        self.calls.append(('login',))

    def voidcmd(self, c):
        self.calls.append(('voidcmd', c))

    def _abs(self, name):
        return name if name.startswith('/') else self.cwd_path.rstrip('/') + '/' + name

    def cwd(self, d):
        self.calls.append(('cwd', d))
        self.cwd_path = d

    def nlst(self):
        self.calls.append(('nlst',))
        pre = self.cwd_path.rstrip('/') + '/'
        names = [k[len(pre):] for k in self.files if k.startswith(pre) and '/' not in k[len(pre):]]
        if not names:
            raise ftplib.error_perm('550 No files found')
        return names

    def retrbinary(self, cmd, cb, blocksize=8192):
        self.calls.append(('retr', cmd))
        data = self.files[self._abs(cmd.split(' ', 1)[1])]
        if self.corrupt:
            data = data[:-1] + bytes([data[-1] ^ 1])
        for i in range(0, len(data), blocksize):
            cb(data[i:i + blocksize])

    def storbinary(self, cmd, f, blocksize=8192):
        self.calls.append(('stor', cmd))
        self.files[self._abs(cmd.split(' ', 1)[1])] = f.read()

    def quit(self):
        self.calls.append(('quit',))


class T15StageFtpP3(Base):
    def setUp(self):
        super().setUp()
        self.cred = os.path.join(self.tmp, 'cred.txt')
        with open(self.cred, 'w') as fh:
            fh.write('xbox\nS3cretPw!\n')
        self.local = os.path.join(self.tmp, 'default.xbe')
        with open(self.local, 'wb') as fh:
            fh.write(b'XBEH' + bytes(range(256)) * 40)

    def _run(self, mock, args):
        out = Out()
        code = sf.main(['--host', '127.0.0.1', '--cred-file', self.cred] + args, factory=lambda: mock, out=out)
        return code, out

    def test_15a_put_verify_receipt_usable_by_launch_observe(self):
        m = MockFTP({'/F/Games/h2u803/other.txt': b'x'})
        rc = os.path.join(self.tmp, 'receipt.json')
        code, out = self._run(m, ['put-verify', self.local, '/F/Games/h2u803', 'default.xbe', '--receipt', rc])
        self.assertEqual(code, 0, out.lines)
        r = jload(rc)
        self.assertTrue(r['verified'])
        self.assertEqual(r['console_path'], XBE)
        self.assertEqual(r['sha256'], xo.sha256_file(self.local))
        self.assertEqual([c[0] for c in m.calls if c[0] in ('stor', 'retr')], ['stor', 'retr'])
        self.assertNotIn('S3cretPw!', '\n'.join(out.lines))
        fake_pins = {'title': {'xbe_sha256': r['sha256'], 'xbe_size': r['size']}}
        self.assertEqual(xo.check_receipt(rc, XBE, fake_pins), (True, 'ok'))

    def test_15b_put_verify_refuses_existing_basename_no_stor(self):
        m = MockFTP({'/F/Games/h2u803/DEFAULT.XBE': b'old'})
        code, out = self._run(m, ['put-verify', self.local, '/F/Games/h2u803', 'default.xbe'])
        self.assertEqual(code, 2)
        self.assertFalse(any(c[0] == 'stor' for c in m.calls))
        self.assertEqual(m.files['/F/Games/h2u803/DEFAULT.XBE'], b'old')

    def test_15c_put_verify_readback_mismatch_exit1_no_verified_epoch(self):
        m = MockFTP({}, corrupt=True)
        rc = os.path.join(self.tmp, 'receipt-bad.json')
        code, out = self._run(m, ['put-verify', self.local, '/F/Games/h2u803', 'default.xbe', '--receipt', rc])
        self.assertEqual(code, 1)
        r = jload(rc)
        self.assertFalse(r['verified'])
        self.assertNotIn('verified_epoch', r)

    def test_15d_fetch_hash_and_list(self):
        data = b'MZ' + bytes(5000)
        m = MockFTP({'/F/DEVKIT/Tools/x/default.xbe': data})
        rc = os.path.join(self.tmp, 'fetch.json')
        code, out = self._run(m, ['fetch-hash', '/F/DEVKIT/Tools/x/default.xbe', '--receipt', rc])
        self.assertEqual(code, 0, out.lines)
        r = jload(rc)
        self.assertEqual((r['size'], r['sha256']), (len(data), hashlib.sha256(data).hexdigest()))
        self.assertEqual(r['console_path'], 'F:\\DEVKIT\\Tools\\x\\default.xbe')
        code, out = self._run(MockFTP({'/F/a/b.txt': b'1', '/F/a/c.txt': b'2'}), ['list', '/F/a'])
        self.assertEqual((code, sorted(out.lines)), (0, ['b.txt', 'c.txt']))
        for name in ('delete', 'rename', 'rmd', 'mkd'):
            self.assertFalse(hasattr(MockFTP, name))
        src = open(sf.__file__).read()
        for bad in ('.delete(', '.rename(', '.rmd(', '.mkd(', 'DELE ', 'RNFR', 'RNTO'):
            self.assertNotIn(bad, src)

    def test_15e_png_conversion_of_raw_screenshot(self):
        raw = bytes([0x10, 0x20, 0x30, 0x00]) * 8
        p = os.path.join(self.tmp, 's.png')
        self.assertTrue(xo.shot_to_png(raw, {'width': 4, 'height': 2, 'pitch': 16}, p))
        with open(p, 'rb') as fh:
            png = fh.read()
        self.assertEqual(png[:8], b'\x89PNG\r\n\x1a\n')
        self.assertEqual(struct.unpack('>II', png[16:24]), (4, 2))
        self.assertFalse(xo.shot_to_png(raw, {'width': 4, 'height': 4, 'pitch': 16}, p + '2'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
