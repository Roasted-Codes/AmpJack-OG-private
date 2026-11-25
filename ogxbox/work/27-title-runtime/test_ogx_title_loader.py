#!/usr/bin/env python3
"""Offline tests for ogx_title_loader.py.

TEST SEAM (transparent): FakeTitle is an in-process byte map built from the
frozen READONLY u803 XBE plus a fake allocation; FakeTitle.call_stub stands in
for the C entry with scripted behaviours. It proves LOADER MECHANICS ONLY. It is
NEVER evidence that the module ran in, or was accepted by, the live title.
"""
import copy
import json
import struct
import subprocess
import unittest
from pathlib import Path

import ogx_title_loader as L

HERE = Path(__file__).resolve().parent
OG = HERE.parents[1]
BASE_ELF = OG / 'work/24-halo2-input/parent-before-correction/pic.elf'
BASE_ELF_SHA = '80a975c20aa53db1991a0e42bdec66b36703ad122aedf2bd5e5b44add543d316'
LAYOUT = json.loads((HERE / 'layout-baseline.json').read_text())
BINDINGS = json.loads((OG / 'work/26-u803-bindings/bindings.json').read_text())
CUR_ELF = OG / 'integration/out/pic.elf'
PINS = L.Pins()
FIX_BASE = 0x83F00000          # FIXTURE arithmetic only: not a claim the address is free
FIX_EXTENT = 0x8000


def elf():
    b = BASE_ELF.read_bytes()
    assert L.sha256(b) == BASE_ELF_SHA
    return b


def module(data=None, **lay):
    data = elf() if data is None else data
    lay = dict(copy.deepcopy(LAYOUT), **lay)
    if data != elf():
        lay['elf_sha256'] = L.sha256(data)     # mutated fixture gets its own layout key
    return L.Module(data, lay)


def receipt(base=FIX_BASE, extent=FIX_EXTENT, fill=0xFF):
    return dict(base=base, extent=extent, fill_byte=fill, allocation_id='fixture-1')


class FakeTitle:
    """Sparse memory: XBE header + XPP section from the frozen file, plus one
    fake allocation filled with the parent's fill byte."""

    def __init__(self, base=FIX_BASE, extent=FIX_EXTENT, fill=0xFF, behaviour='install'):
        raw = L.FROZEN_XBE.read_bytes()
        self.regions = {0x10000: bytearray(raw[:0x2000])}
        # The real kernel decodes the entry (0x128) and thunk (0x158) from the
        # disk XOR into the absolute VAs the loader's verify_header expects.
        struct.pack_into('<I', self.regions[0x10000], 0x128,
                         struct.unpack_from('<I', self.regions[0x10000], 0x128)[0] ^ L.RETAIL_EP_KEY)
        struct.pack_into('<I', self.regions[0x10000], 0x158,
                         struct.unpack_from('<I', self.regions[0x10000], 0x158)[0] ^ L.RETAIL_THUNK_KEY)
        for f, v, vs, ra, rs in PINS.secs:
            if v == 0x4127A0:                              # XPP: sites + methods
                self.regions[v] = bytearray(raw[ra:ra + rs])
        self.regions[base] = bytearray([fill]) * extent
        self.behaviour = behaviour
        self.writes = []
        self.fail_write_after = None     # raise on the Nth write
        self.corrupt_next_write = False
        self.calls = []

    def _loc(self, addr, n):
        for s, r in self.regions.items():
            if s <= addr and addr + n <= s + len(r):
                return r, addr - s
        raise IOError(f'unmapped {addr:#x}+{n}')

    def read(self, addr, n):
        r, o = self._loc(addr, n)
        return bytes(r[o:o + n])

    def write(self, addr, data):
        if self.fail_write_after is not None and len(self.writes) >= self.fail_write_after:
            self.fail_write_after = None
            r, o = self._loc(addr, len(data))
            r[o:o + len(data) // 2] = data[:len(data) // 2]          # partial write, then error
            raise IOError('E01 simulated transport failure')
        r, o = self._loc(addr, len(data))
        data = bytearray(data)
        if self.corrupt_next_write:
            self.corrupt_next_write = False
            data[len(data) // 3] ^= 0x01
        r[o:o + len(data)] = data
        self.writes.append((addr, len(data)))

    def call_stub(self, stub, bp, timeout):
        # decode OUR stub: pushad; push 0; mov eax,imm32; call eax; add esp,4; popad; int3
        code = self.read(stub, L.STUB_LEN)
        assert code[:4] == bytes.fromhex('606a00b8') and code[8:] == bytes.fromhex('ffd083c40461cc')
        assert bp == stub + L.STUB_LEN - 1
        entry = struct.unpack('<I', code[4:8])[0]
        self.calls.append(entry)
        m, base = self.module, self.base
        host = base + m.module_off
        inst = host + m.layout['status_fields']['installed_hooks']
        fail = host + m.layout['status_fields']['install_failed']
        # scripted stand-in for the C installer (TEST ONLY)
        if self.behaviour in ('install', 'wrong_target'):
            for name, (va, _o, _d, bit) in L.HOOK_SITES.items():
                tgt = base + m.hook_off[name] + (16 if self.behaviour == 'wrong_target' else 0)
                self.write(va, L.e9(va, tgt))
            self.write(inst, struct.pack('<I', m.layout['expected_installed_hooks']))
        elif self.behaviour == 'refuse':
            self.write(fail, struct.pack('<I', 1))
        return dict(eax=0, eip=bp)


def loader(**b):
    bb = dict(BINDINGS, **b)
    return L.TitleLoader(module(), PINS, bb)


def run_load(tmp, ft=None, rc=None, **b):
    tl = loader(**b)
    ft = ft or FakeTitle()
    ft.module, ft.base = tl.m, (rc or receipt())['base']
    return tl, ft, tl.load(ft, rc or receipt(), tmp)


class T(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.td = Path(tempfile.mkdtemp(dir='/home/roasted/.hermes/cache/scratch'))
        self.j = self.td / 'journal.json'

    # ---------------- ELF mechanics on the ACTUAL frozen baseline
    def test_baseline_elf_geometry(self):
        m = module()
        self.assertEqual(len(m.loads), 3)
        self.assertEqual([(s['va'], s['fsz'], s['msz']) for s in m.loads],
                         [(0, 0x210c, 0x210c), (0x210c, 0x126, 0x126), (0x2234, 0x1ac, 0x5420)])
        self.assertEqual(len(m.relocs), 20)
        self.assertEqual(m.mem_end, 0x7654)
        self.assertEqual(m.entry_off, 0)                 # zero-valued entry symbol is valid
        self.assertEqual(m.module_off, 0x23E4)
        self.assertEqual(m.stub_off, 0x7660)
        self.assertEqual(m.required, 0x8000)

    def test_image_bytes_relocs_bss(self):
        m, raw = module(), elf()
        img, stub = m.image(FIX_BASE, loader().host)
        for s in m.loads:                                  # file bytes copied, except reloc slots
            seg = bytearray(raw[s['off']:s['off'] + s['fsz']])
            for r in m.relocs:
                if s['va'] <= r < s['va'] + s['fsz']:
                    o = r - s['va']
                    a = struct.unpack_from('<I', seg, o)[0]
                    self.assertEqual(struct.unpack_from('<I', img, r)[0], a + FIX_BASE)
                    struct.pack_into('<I', seg, o, a + FIX_BASE)
            self.assertEqual(img[s['va']:s['va'] + s['fsz']], bytes(seg))
        bss_lo = 0x2234 + 0x1ac
        host = m.module_off
        z = bytearray(img[bss_lo:m.mem_end])
        z[host - bss_lo:host - bss_lo + 36] = bytes(36)
        self.assertEqual(bytes(z), bytes(len(z)))         # BSS zero except host struct
        self.assertEqual(struct.unpack_from('<9I', img, host),
                         (0x4155BF, 0x41517D, 0x416992, 0, 0x4165C6, 0x4127B4, 0x4127CC, 0x4127D8, 0))
        self.assertEqual(stub[4:8], struct.pack('<I', FIX_BASE + 0))

    def test_symbols_match_readelf(self):
        out = subprocess.check_output(['readelf', '-sW', str(BASE_ELF)], text=True)
        ref = {l.split()[7]: int(l.split()[1], 16) for l in out.splitlines()
               if len(l.split()) == 8 and l.split()[0].rstrip(':').isdigit()}
        m = module()
        for name, off in m.hook_off.items():
            self.assertEqual(off, ref[LAYOUT['hook_targets'][name]])
        self.assertEqual(ref['ogx_module_entry'], m.entry_off)
        self.assertEqual(ref['_end'], m.mem_end)

    def test_moving_source_elf_needs_published_layout(self):
        if CUR_ELF.exists() and L.sha256(CUR_ELF.read_bytes()) != BASE_ELF_SHA:
            with self.assertRaisesRegex(L.LoaderError, 'no published layout'):
                L.Module(CUR_ELF.read_bytes(), LAYOUT)

    # ---------------- malformed ELF
    def _mut(self, fn):
        b = bytearray(elf())
        fn(b)
        return bytes(b)

    def test_malformed(self):
        ph = lambda i: 52 + 32 * i
        rel = 0x3130
        cases = {
            'truncated': lambda b: b.__delitem__(slice(40, None)),
            'filesz > memsz': lambda b: struct.pack_into('<I', b, ph(0) + 20, 0x2000),
            'file range out of file': lambda b: struct.pack_into('<I', b, ph(2) + 4, 0xFFFF0),
            'overlap': lambda b: struct.pack_into('<I', b, ph(1) + 8, 0x110c),
            'unsupported relocation type 1': lambda b: struct.pack_into('<I', b, rel + 4, 1),
            'non-writable segment': lambda b: struct.pack_into('<I', b, rel, 0x10),
            'outside image': lambda b: struct.pack_into('<I', b, rel, 0x9000),
            'program header type 3': lambda b: struct.pack_into('<I', b, ph(4), 3),
            'DT_TEXTREL': lambda b: struct.pack_into('<II', b, 0x3380 + 8, 22, 0),
            'need ET_DYN': lambda b: struct.pack_into('<H', b, 16, 2),
        }
        for msg, fn in cases.items():
            with self.subTest(msg), self.assertRaisesRegex(L.LoaderError, msg.split(' (')[0]):
                module(self._mut(fn))

    def test_bad_reloc_addend_overflow(self):
        b = self._mut(lambda b: struct.pack_into('<I', b, 0x3234, 0xF0000000))
        with self.assertRaisesRegex(L.LoaderError, 'addend'):
            module(b).image(FIX_BASE, loader().host)

    def test_layout_mismatch_refused(self):
        with self.assertRaisesRegex(L.LoaderError, 'module object size'):
            L.Module(elf(), dict(LAYOUT, module_size=21104))
        with self.assertRaisesRegex(L.LoaderError, 'no published layout'):
            L.Module(elf(), dict(LAYOUT, elf_sha256='00' * 32))

    # ---------------- bindings
    def test_bindings(self):
        loader()
        for k, v, msg in [('add_complete', 0, 'add_complete'), ('remove_complete', None, 'remove_complete'),
                          ('xdevice_type_gamepad', 0, 'xdevice'), ('submit_request', 0x4155C0, 'submit'),
                          ('cancel_request', 0x1234, 'cancel_request must be 0'),
                          ('now_ms', 0x33B590, 'ABI is not u32')]:
            with self.subTest(k), self.assertRaisesRegex(L.LoaderError, msg):
                loader(**{k: v})

    def test_clock_receipt(self):
        self.assertEqual(PINS.verify_clock_receipt(0x33B590, 0x41B774, 156), 0x33B590)
        with self.assertRaisesRegex(L.LoaderError, 'ordinal mismatch'):
            PINS.verify_clock_receipt(0x33C29D, 0x41B784, 156)
        with self.assertRaisesRegex(L.LoaderError, 'not KeTickCount'):
            PINS.verify_clock_receipt(0x33C29D, 0x41B784, 356)
        with self.assertRaisesRegex(L.LoaderError, 'not mov eax'):
            PINS.verify_clock_receipt(0x33B591, 0x41B774, 156)

    # ---------------- receipt / extents
    def test_receipt_validation(self):
        tl = loader()
        for rc, msg in [(receipt(base=FIX_BASE + 0x800), 'aligned'),
                        (receipt(extent=0x7FFF), 'required'),
                        (receipt(base=0x4F0000), 'overlaps title image'),
                        (receipt(base=0xFFFFC000, extent=0x8000), 'overflows'),
                        (receipt(base=0x1000), 'low 64K'),
                        ({'base': FIX_BASE, 'extent': FIX_EXTENT}, 'lacks fill_byte')]:
            with self.subTest(msg), self.assertRaisesRegex(L.LoaderError, msg):
                tl.plan(rc)

    # ---------------- failure before write
    def test_failure_before_write(self):
        def hdr(ft): ft.regions[0x10000][0x110] ^= 1
        def meth(ft): ft.regions[0x4127A0][0x416992 - 0x4127A0] ^= 1
        def site(ft): ft.regions[0x4127A0][0x413A12 - 0x4127A0] = 0xE9
        def site2(ft): ft.regions[0x4127A0][0x413C4C - 0x4127A0 + 7] ^= 1
        def used(ft): ft.regions[FIX_BASE][0x7000] = 0
        for fn, msg in [(hdr, 'header'), (meth, 'method guard'), (site, 'repeat install'),
                        (site2, 'differ from frozen'), (used, 'fill state')]:
            ft = FakeTitle()
            fn(ft)
            with self.subTest(msg), self.assertRaisesRegex(L.LoaderError, msg):
                run_load(None, ft)
            self.assertEqual(ft.writes, [])
            self.assertEqual(ft.calls, [])

    # ---------------- happy path, repeat rejection, status
    def test_load_verify_and_repeat_rejected(self):
        tl, ft, res = run_load(self.j)
        self.assertEqual(res['verdict'], 'installed')
        self.assertEqual(ft.calls, [FIX_BASE])            # entry = base + 0
        self.assertEqual(res['status'], {'attached': 0, 'installed_hooks': 0xBF, 'install_failed': 0})
        jd = json.loads(self.j.read_text())
        self.assertEqual(jd['state'], 'verified_installed')
        self.assertEqual(jd['history'], ['planned', 'image_written', 'entry_calling', 'entry_returned',
                                         'verified_installed'])
        loader_writes = [w for w in ft.writes if FIX_BASE <= w[0] < FIX_BASE + FIX_EXTENT]
        self.assertEqual(loader_writes[:2], [(FIX_BASE, 0x7660), (FIX_BASE + 0x7660, 15)])
        n = len(ft.writes)
        with self.assertRaisesRegex(L.LoaderError, 'repeat install'):
            tl.load(ft, receipt(), self.j)
        self.assertEqual(len(ft.writes), n)

    def test_open_journal_blocks_second_load(self):
        run_load(self.j)
        ft2 = FakeTitle()
        tl = loader()
        ft2.module, ft2.base = tl.m, FIX_BASE
        with self.assertRaisesRegex(L.LoaderError, 'open journal'):
            tl.load(ft2, receipt(), self.j)
        self.assertEqual(ft2.writes, [])

    def test_failclosed_entry(self):
        _, _, res = run_load(self.j, FakeTitle(behaviour='refuse'))
        self.assertEqual(res['verdict'], 'refused_failclosed')

    def test_inconsistent_entry(self):
        for beh in ('wrong_target', 'noop'):
            with self.subTest(beh), self.assertRaisesRegex(L.LoaderError, 'inconsistent'):
                run_load(None, FakeTitle(behaviour=beh))

    # ---------------- partial write / readback mismatch cleanup
    def test_partial_write_scrubbed(self):
        ft = FakeTitle()
        ft.fail_write_after = 0
        with self.assertRaisesRegex(L.LoaderError, 'region scrubbed'):
            run_load(self.j, ft)
        self.assertEqual(ft.read(FIX_BASE, FIX_EXTENT), b'\xff' * FIX_EXTENT)
        self.assertEqual(json.loads(self.j.read_text())['state'], 'closed')
        self.assertEqual(ft.calls, [])

    def test_readback_mismatch_scrubbed(self):
        ft = FakeTitle()
        ft.corrupt_next_write = True
        with self.assertRaisesRegex(L.LoaderError, 'image readback mismatch'):
            run_load(self.j, ft)
        self.assertEqual(ft.read(FIX_BASE, FIX_EXTENT), b'\xff' * FIX_EXTENT)
        self.assertEqual(ft.calls, [])

    def test_guarded_memory(self):
        ft = FakeTitle()
        g = L.GuardedMemory(ft, FIX_BASE, FIX_EXTENT)
        for a, n in [(0x41517D, 5), (FIX_BASE - 1, 2), (FIX_BASE + FIX_EXTENT - 1, 2)]:
            with self.assertRaisesRegex(L.LoaderError, 'outside allocation'):
                g.write(a, b'\0' * n)
        self.assertEqual(ft.writes, [])

    # ---------------- rollback / journal lifetime
    def test_rollback(self):
        tl, ft, _ = run_load(self.j)
        with self.assertRaisesRegex(L.LoaderError, 'hooks are live'):
            tl.rollback(ft, self.j)
        r = tl.rollback(ft, self.j, allow_hook_restore=True)
        self.assertEqual(sorted(r['restored_sites']), sorted(L.HOOK_SITES))
        for name, (va, orig5, dlen, _b) in L.HOOK_SITES.items():
            self.assertEqual(ft.read(va, dlen), PINS.sites[name])
        self.assertEqual(ft.read(FIX_BASE, FIX_EXTENT), b'\xff' * FIX_EXTENT)
        with self.assertRaisesRegex(L.LoaderError, 'already closed'):
            tl.rollback(ft, self.j, allow_hook_restore=True)

    def test_stale_journal_never_restores(self):
        tl, ft, _ = run_load(self.j)
        fresh = FakeTitle()                               # title restarted: new memory state
        fresh.regions[FIX_BASE][:] = b'\x00' * FIX_EXTENT
        with self.assertRaisesRegex(L.LoaderError, 'stale journal'):
            tl.rollback(fresh, self.j, allow_hook_restore=True)
        self.assertEqual(fresh.writes, [])
        self.assertEqual(json.loads(self.j.read_text())['state'], 'stale')
        tl2 = loader()                                    # stale journal does not block a new load
        fresh2 = FakeTitle()
        fresh2.module, fresh2.base = tl2.m, FIX_BASE
        self.assertEqual(tl2.load(fresh2, receipt(), self.j)['verdict'], 'installed')

    def test_rollback_refuses_foreign_site(self):
        tl, ft, _ = run_load(self.j)
        ft.regions[0x4127A0][0x413A12 - 0x4127A0 + 1] ^= 0x55       # someone else re-patched
        n = len(ft.writes)
        with self.assertRaisesRegex(L.LoaderError, 'unknown state'):
            tl.rollback(ft, self.j, allow_hook_restore=True)
        self.assertEqual(len(ft.writes), n)

    # ---------------- GDB adapter discipline against a fake RSP (no socket)
    def test_gdb_adapter_register_discipline(self):
        class FakeRSP:
            def __init__(s, stop_eip):
                s.r = dict(eax=0x11, ecx=0, edx=0, ebx=0, esp=0xD0010000, ebp=0, esi=0, edi=0, eip=0x12E1A0)
                s.raw = 'aa' * 16
                s.bps, s.mem, s.stop_eip = [], {}, stop_eip
            def raw_regs(s): return s.raw
            def regs(s): return dict(s.r)
            def set_regs(s, **v): s.r.update(v); s.raw = 'bb' * 16
            def set_raw_regs(s, raw): s.raw = raw; s.r['eip'] = 0x12E1A0
            def read(s, a, n): return s.mem.get(a, b'\x5a' * n)
            def write(s, a, d): s.mem[a] = d
            def bp(s, a, insert=True): s.bps.append((a, insert))
            def continue_wait(s, t): s.r['eip'] = s.stop_eip; s.r['eax'] = 0x99; return 'T05'
        ok = FakeRSP(0x1000E)
        out = L.GdbRspAdapter(ok).call_stub(0x10000, 0x1000E, 5)
        self.assertEqual(out['eax'], 0x99)
        self.assertEqual(ok.raw, 'aa' * 16)
        self.assertEqual(ok.bps, [(0x1000E, True), (0x1000E, False)])
        self.assertIn(0xD0010000 - 0x1000, ok.mem)
        bad = FakeRSP(0x41517D)
        with self.assertRaisesRegex(L.LoaderError, 'unexpected stop'):
            L.GdbRspAdapter(bad).call_stub(0x10000, 0x1000E, 5)
        self.assertNotEqual(bad.raw, 'aa' * 16)           # left halted, not "restored" blindly


class T32(unittest.TestCase):
    """work/32 combined ELF (F6 IRQL span). FIXTURE allocation only (FIX_BASE is
    arithmetic, not a claim the address is free); FakeTitle is a test double."""
    ELF32 = OG / 'work/32-opus-final-integration/artifact/pic.elf'
    LAY32 = json.loads((OG / 'work/32-opus-final-integration/artifact/layout.json').read_text())
    RESOLVED = {0x41B700: 0x8003C1A0, 0x41B6FC: 0x8003C1C0}   # FIXTURE kernel addresses

    def setUp(self):
        import tempfile
        self.j = Path(tempfile.mkdtemp(dir='/home/roasted/.hermes/cache/scratch')) / 'journal.json'

    def mod(self, **lay):
        return L.Module(self.ELF32.read_bytes(), dict(copy.deepcopy(self.LAY32), **lay))

    def ft(self, resolve=True):
        ft = FakeTitle(extent=0x9000)
        if 0x41B6FC not in range(0x4127A0, 0x4127A0 + len(ft.regions[0x4127A0])):
            ft.regions[0x41B600] = bytearray(PINS.read(0x41B600, 0x264))
        if resolve:
            for va, v in self.RESOLVED.items():
                ft.write(va, struct.pack('<I', v))
            ft.writes.clear()
        return ft

    def test_w32_layout_bound_and_irql_required(self):
        m = self.mod()
        self.assertTrue(m.has_irql)
        self.assertEqual(m.symbols['ogx_g_module']['size'], self.LAY32['module_size'])
        with self.assertRaisesRegex(L.LoaderError, 'no published layout'):
            L.Module(self.ELF32.read_bytes(), copy.deepcopy(LAYOUT))       # loader27 baseline layout refused
        one = [f for f in self.LAY32['host_fields'] if f[0] != 'irql_lower_slot']
        with self.assertRaisesRegex(L.LoaderError, 'only one IRQL'):
            self.mod(host_fields=one)
        with self.assertRaisesRegex(L.LoaderError, 'stdcall_u32'):
            self.mod(now_ms_abi='cdecl_u64')

    def test_w32_irql_bindings_pinned(self):
        tl = L.TitleLoader(self.mod(), PINS, dict(BINDINGS))
        self.assertEqual((tl.host['irql_raise_slot'], tl.host['irql_lower_slot']), (0x41B700, 0x41B6FC))
        for k, v, msg in [('irql_raise_slot', 0x41B6FC, 'pinned'), ('irql_lower_slot', 0x41B774, 'pinned')]:
            with self.subTest(k), self.assertRaisesRegex(L.LoaderError, msg):
                L.TitleLoader(self.mod(), PINS, dict(BINDINGS, **{k: v}))
        saved = L.IRQL_SLOTS['irql_raise_slot']
        try:
            L.IRQL_SLOTS['irql_raise_slot'] = (0x41B700, 130)    # wrong ordinal for this slot
            with self.assertRaisesRegex(L.LoaderError, 'ordinal mismatch'):
                PINS.verify_irql_slot('irql_raise_slot', 0x41B700)
        finally:
            L.IRQL_SLOTS['irql_raise_slot'] = saved

    def test_w32_fixture_load_serializes_irql_fields(self):
        tl = L.TitleLoader(self.mod(), PINS, dict(BINDINGS))
        ft = self.ft()
        ft.module, ft.base = tl.m, FIX_BASE
        res = tl.load(ft, receipt(extent=0x9000), self.j)
        self.assertEqual(res['verdict'], 'installed')
        host = FIX_BASE + tl.m.module_off + self.LAY32['host_offset']
        got = {f: struct.unpack('<I', ft.read(host + o, 4))[0] for f, o in self.LAY32['host_fields']}
        self.assertEqual((got['irql_raise_slot'], got['irql_lower_slot'], got['now_ms']), (0x41B700, 0x41B6FC, 0))

    def test_w32_unresolved_slot_refused_before_write(self):
        tl = L.TitleLoader(self.mod(), PINS, dict(BINDINGS))
        ft = self.ft(resolve=False)                    # thunk still 0x80000081 / 0x800000A1
        ft.module, ft.base = tl.m, FIX_BASE
        with self.assertRaisesRegex(L.LoaderError, 'unresolved live'):
            tl.load(ft, receipt(extent=0x9000), self.j)
        self.assertEqual((ft.writes, ft.calls), ([], []))


if __name__ == '__main__':
    unittest.main(verbosity=2)
