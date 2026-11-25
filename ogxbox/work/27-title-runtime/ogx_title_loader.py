#!/usr/bin/env python3
"""ogx_title_loader.py -- load/bind/call the AmpJack-OG title module into a running
Halo 2 TU1.5 u803 title through an EXISTING parent-owned runtime client.

Scope (deliberately small, stdlib only):
  * parse + validate an i386 static-PIE ELF32 (PT_LOAD only, R_386_RELATIVE only);
  * build the in-memory image for an allocator-returned base: copy file bytes,
    zero BSS, apply relocations, fill the published host-binding struct;
  * write it ONLY inside the parent's allocation receipt, read the whole
    footprint back, call the REAL module entry through a 15-byte register-saving
    stub placed in the module's own allocation, then VERIFY the effects the C
    installer is responsible for (7 E9 sites -> exact relocated targets, module
    status words).  The loader never writes a game hook itself.
  * journal every state; rollback refuses stale journals.

NOT in scope: allocation, picking a safe point, title startup, capture. A fake
adapter (tests only) proves loader mechanics, never live title acceptance.
"""
import hashlib
import json
import struct
from pathlib import Path

FROZEN_XBE = Path('/home/roasted/Desktop/Xbox/H2-Decomp/tu15-decomp/targets/halo2-tu15-u803/default.xbe')
FROZEN_XBE_SHA256 = '21b207e7efdacaf6124a0822837f8be570766a42505057f7fd2d2ba8f409c4fd'
XBE_LOAD = 0x10000
HEADER_GUARD_LEN = 0x178           # image header through the cert pointer area
RETAIL_EP_KEY = 0xA8FC57AB         # XBE entry-point XOR (retail key)
RETAIL_THUNK_KEY = 0x5B6D40B6      # XBE kernel-thunk XOR (retail key)

# The seven game sites owned by the production C installer (og_hook_sites.h +
# ogx_install.c OGX_FC_ORIG5).  name -> (va, orig5, displaced_len, status bit)
HOOK_SITES = {
    'FindClassDriver':       (0x0041517D, bytes.fromhex('56b8b42741'), 5, 7),
    'XGetDeviceChanges':     (0x004139A5, bytes.fromhex('558bec568b'), 7, 0),
    'XInputOpen':            (0x00413A12, bytes.fromhex('558bec518b'), 7, 1),
    'XInputClose':           (0x00413A68, bytes.fromhex('8b4c2404e8'), 9, 2),
    'XInputGetCapabilities': (0x00413A74, bytes.fromhex('558bec83ec'), 6, 3),
    'XInputGetState':        (0x00413C4C, bytes.fromhex('535633dbff'), 10, 4),
    'XInputSetState':        (0x00413CBF, bytes.fromhex('8b4c24048d'), 10, 5),
}
# Required bindings (worker26 bindings.json; independently pinned by parent).
REQUIRED_BINDINGS = {
    'submit_request': 0x004155BF, 'findclassdriver': 0x0041517D,
    'add_complete': 0x00416992, 'remove_complete': 0x004165C6,
    'class_table_begin': 0x004127B4, 'class_table_end': 0x004127CC,
    'xdevice_type_gamepad': 0x004127D8,       # pointer identity, contents are 0
}
OPTIONAL_ZERO = ('cancel_request',)           # unused by the close-based transport
METHOD_GUARD_LEN = 10                          # prologue bytes compared live
KE_TICK_COUNT_ORDINAL = 156                    # INFERENCE: xboxkrnl export table
# F6 critical span (work/32): the title's own kernel import SLOTS the module calls
# through. Ordinals pinned from the frozen XBE thunk table + XDK 5849 xboxkrnl.lib
# import records (work/32 tools/pin_irql.py): 129 _KeRaiseIrqlToDpcLevel@0 (stdcall),
# 161 @KfLowerIrql@4 (fastcall, CL). Required for any layout that declares them.
IRQL_SLOTS = {'irql_raise_slot': (0x0041B700, 129), 'irql_lower_slot': (0x0041B6FC, 161)}

R_386_RELATIVE = 8
PT_NULL, PT_LOAD, PT_DYNAMIC, PT_INTERP, PT_NOTE, PT_PHDR, PT_TLS = 0, 1, 2, 3, 4, 6, 7
PT_GNU_STACK, PT_GNU_RELRO = 0x6474E551, 0x6474E552
PF_X, PF_W = 1, 2
DT = dict(NULL=0, NEEDED=1, PLTRELSZ=2, RELA=7, RELASZ=8, REL=17, RELSZ=18, RELENT=19,
          TEXTREL=22, JMPREL=23, FLAGS=30, RELCOUNT=0x6FFFFFFA, FLAGS_1=0x6FFFFFFB)
DF_TEXTREL = 4
U32 = 0xFFFFFFFF
PAGE = 0x1000
STUB_LEN = 15


class LoaderError(Exception):
    """Any refusal. Raised BEFORE the first runtime write whenever possible."""


def _need(cond, msg):
    if not cond:
        raise LoaderError(msg)


def sha256(b):
    return hashlib.sha256(b).hexdigest()


def align_up(v, a):
    _need(a > 0 and (a & (a - 1)) == 0, f'bad alignment {a:#x}')
    r = (v + a - 1) & ~(a - 1)
    _need(r >= v, 'alignment overflow')
    return r


# --------------------------------------------------------------------------- ELF
class Module:
    """Validated static-PIE image. All offsets are image-relative (base 0)."""

    def __init__(self, data, layout):
        self.data = bytes(data)
        self.sha256 = sha256(self.data)
        self.layout = layout
        _need(layout.get('elf_sha256') == self.sha256,
              f'no published layout for ELF {self.sha256}; refuse to guess offsets')
        self._header()
        self._segments()
        self._dynamic()
        self._sections_symbols()
        self._abi()

    # -- header
    def _header(self):
        d = self.data
        _need(len(d) >= 52, 'truncated ELF header')
        _need(d[:4] == b'\x7fELF' and d[4] == 1 and d[5] == 1 and d[6] == 1, 'not ELF32 LSB v1')
        (et, em, ev, self.e_entry, phoff, shoff, _fl, ehsz, phes, phn, shes, shn,
         shstr) = struct.unpack_from('<HHIIIIIHHHHHH', d, 16)
        _need(et == 3 and em == 3 and ev == 1, 'need ET_DYN EM_386 static PIE')
        _need(ehsz == 52 and phes == 32 and shes == 40, 'bad ELF entry sizes')
        _need(0 < phn <= 16 and phoff + phn * 32 <= len(d), 'program headers out of file')
        _need(shn and shoff + shn * 40 <= len(d) and shstr < shn, 'section headers out of file')
        self.phoff, self.phn, self.shoff, self.shn, self.shstr = phoff, phn, shoff, shn, shstr

    # -- PT_LOAD
    def _segments(self):
        d = self.data
        self.loads, self.dyn_ph = [], None
        for i in range(self.phn):
            t, off, va, _pa, fsz, msz, fl, al = struct.unpack_from('<8I', d, self.phoff + i * 32)
            if t == PT_LOAD:
                _need(fsz <= msz, f'PT_LOAD{i} filesz > memsz')
                _need(off + fsz <= len(d) and off + fsz >= off, f'PT_LOAD{i} file range out of file')
                _need(va + msz <= U32 and va + msz >= va, f'PT_LOAD{i} vaddr overflow')
                _need(al in (0, 1) or (al & (al - 1)) == 0, f'PT_LOAD{i} bad p_align')
                if al > 1:
                    _need(va % al == off % al, f'PT_LOAD{i} vaddr/offset congruence')
                _need(fl & ~7 == 0 and (fl & 4), f'PT_LOAD{i} bad flags')
                self.loads.append(dict(off=off, va=va, fsz=fsz, msz=msz, flags=fl, align=max(al, 1)))
            elif t == PT_DYNAMIC:
                _need(self.dyn_ph is None, 'two PT_DYNAMIC')
                self.dyn_ph = (off, va, fsz)
            elif t in (PT_INTERP, PT_TLS):
                raise LoaderError(f'unsupported program header type {t}')
            elif t not in (PT_NULL, PT_NOTE, PT_PHDR, PT_GNU_STACK, PT_GNU_RELRO):
                raise LoaderError(f'unknown program header type {t:#x}')
        _need(self.loads, 'no PT_LOAD')
        _need(self.loads[0]['va'] == 0, 'static PIE must link at 0')
        prev = 0
        for s in self.loads:
            _need(s['va'] >= prev, 'PT_LOAD segments overlap or are unsorted')
            prev = s['va'] + s['msz']
        self.mem_end = prev
        self.max_align = max(PAGE, max(s['align'] for s in self.loads))
        self.stub_off = align_up(self.mem_end, 16)
        self.required = align_up(self.stub_off + STUB_LEN, self.max_align)

    def seg_of(self, off, n):
        for s in self.loads:
            if s['va'] <= off and off + n <= s['va'] + s['msz']:
                return s
        return None

    def _file_off(self, va, n):
        for s in self.loads:
            if s['va'] <= va and va + n <= s['va'] + s['fsz']:
                return s['off'] + va - s['va']
        raise LoaderError(f'range {va:#x}+{n} not file-backed')

    # -- dynamic + relocations
    def _dynamic(self):
        _need(self.dyn_ph is not None, 'no PT_DYNAMIC')
        off, va, fsz = self.dyn_ph
        _need(fsz % 8 == 0 and off + fsz <= len(self.data), 'bad PT_DYNAMIC extent')
        _need(self._file_off(va, fsz) == off, 'PT_DYNAMIC not inside its PT_LOAD')
        tags = {}
        for i in range(0, fsz, 8):
            tag, val = struct.unpack_from('<II', self.data, off + i)
            if tag == DT['NULL']:
                break
            _need(tag not in tags or tag == DT['NEEDED'], f'duplicate dynamic tag {tag:#x}')
            tags[tag] = val
        else:
            raise LoaderError('PT_DYNAMIC lacks DT_NULL')
        for bad in ('NEEDED', 'TEXTREL', 'RELA', 'RELASZ', 'JMPREL', 'PLTRELSZ'):
            _need(DT[bad] not in tags, f'unsupported DT_{bad}')
        _need(not (tags.get(DT['FLAGS'], 0) & DF_TEXTREL), 'DF_TEXTREL set')
        self.relocs = []
        if DT['REL'] in tags:
            roff, rsz, rent = tags[DT['REL']], tags.get(DT['RELSZ']), tags.get(DT['RELENT'])
            _need(rsz is not None and rent == 8 and rsz % 8 == 0, 'bad DT_RELSZ/DT_RELENT')
            base = self._file_off(roff, rsz) if rsz else 0
            for i in range(0, rsz, 8):
                r_off, info = struct.unpack_from('<II', self.data, base + i)
                _need(info & 0xFF == R_386_RELATIVE and info >> 8 == 0,
                      f'unsupported relocation type {info & 0xFF} sym {info >> 8} @ {r_off:#x}')
                self.relocs.append(r_off)
            cnt = tags.get(DT['RELCOUNT'])
            _need(cnt is None or cnt <= len(self.relocs), 'DT_RELCOUNT > relocations')
        else:
            _need(DT['RELSZ'] not in tags, 'DT_RELSZ without DT_REL')
        _need(len(set(self.relocs)) == len(self.relocs), 'duplicate relocation target')
        for r in self.relocs:
            s = self.seg_of(r, 4)
            _need(s is not None, f'relocation target {r:#x} outside image')
            _need(s['flags'] & PF_W, f'relocation into non-writable segment {r:#x} (TEXTREL)')

    # -- sections / symbols (symbol value 0 is a VALID offset)
    def _sections_symbols(self):
        d = self.data
        sh = [struct.unpack_from('<10I', d, self.shoff + i * 40) for i in range(self.shn)]
        for (nm, typ, fl, addr, off, size, link, info, al, es) in sh:
            if typ != 8:  # SHT_NOBITS has no file bytes
                _need(off + size <= len(d) and off + size >= off, 'section out of file')
        self.sections = sh
        symtabs = [s for s in sh if s[1] == 2]
        _need(len(symtabs) == 1, 'need exactly one .symtab (unstripped module)')
        _nm, _t, _f, _a, off, size, link, _i, _al, es = symtabs[0]
        _need(es == 16 and size % 16 == 0 and link < self.shn, 'bad .symtab')
        stroff, strsz = sh[link][4], sh[link][5]
        self.symbols = {}
        dup = set()
        for i in range(1, size // 16):
            st_name, st_value, st_size, st_info, _o, st_shndx = struct.unpack_from('<IIIBBH', d, off + i * 16)
            _need(st_name < strsz, 'symbol name out of strtab')
            end = d.index(b'\0', stroff + st_name)
            _need(end < stroff + strsz, 'unterminated symbol name')
            name = d[stroff + st_name:end].decode('ascii')
            stype = st_info & 0xF
            if stype not in (1, 2) or not name:       # OBJECT / FUNC only
                continue
            _need(0 < st_shndx < self.shn, f'symbol {name} not section-defined')
            if name in self.symbols:
                dup.add(name)
            self.symbols[name] = dict(value=st_value, size=st_size, type=stype, shndx=st_shndx)
        self.dup_symbols = dup

    def sym(self, name, kind):
        _need(name not in self.dup_symbols, f'ambiguous symbol {name}')
        s = self.symbols.get(name)
        _need(s is not None, f'missing symbol {name}')          # NOT `if not value`
        _need(s['type'] == (2 if kind == 'func' else 1), f'symbol {name} wrong type')
        _need(s['size'] > 0, f'symbol {name} has zero size')
        seg = self.seg_of(s['value'], s['size'])
        _need(seg is not None, f'symbol {name} outside PT_LOAD')
        if kind == 'func':
            _need(seg['flags'] & PF_X, f'function {name} not in executable segment')
        return s['value']

    # -- ABI cross-checks against the published layout
    def _abi(self):
        L = self.layout
        self.entry_off = self.sym(L['entry_symbol'], 'func')
        _need(L['entry_abi'] == 'cdecl(void*)', 'unsupported entry ABI')
        self.module_off = self.sym(L['module_symbol'], 'object')
        _need(self.symbols[L['module_symbol']]['size'] == L['module_size'], 'module object size != layout')
        seg = self.seg_of(self.module_off, L['module_size'])
        _need(seg['flags'] & PF_W, 'module object not writable')
        _need(self.module_off >= seg['va'] + seg['fsz'], 'module object expected in BSS (zeroed)')
        names = [f for f, _ in L['host_fields']]
        for req in list(REQUIRED_BINDINGS) + list(OPTIONAL_ZERO) + ['now_ms']:
            _need(req in names, f'layout lacks host field {req}')
        has = [k in names for k in IRQL_SLOTS]
        _need(all(has) or not any(has), 'layout declares only one IRQL slot field')
        self.has_irql = all(has)
        if self.has_irql:
            _need(set(L.get('irql_abi', {})) == set(IRQL_SLOTS), 'layout IRQL fields lack irql_abi')
            _need(L['now_ms_abi'] == 'stdcall_u32', 'IRQL-span layout must publish now_ms as stdcall_u32')
        for f, o in L['host_fields']:
            _need(o % 4 == 0 and o + 4 <= L['host_size'], f'bad host field {f}')
        _need(L['host_offset'] + L['host_size'] <= L['module_size'], 'host struct beyond module')
        for f, o in L['status_fields'].items():
            _need(o % 4 == 0 and o + 4 <= L['module_size'], f'bad status field {f}')
        _need(set(L['hook_targets']) == set(HOOK_SITES), 'layout hook map != seven sites')
        self.hook_off = {k: self.sym(v, 'func') for k, v in L['hook_targets'].items()}
        exp = sum(1 << HOOK_SITES[k][3] for k in HOOK_SITES)
        _need(L['expected_installed_hooks'] == exp, 'expected_installed_hooks inconsistent')

    # -- image for a base (pure)
    def image(self, base, host_values):
        _need(base % self.max_align == 0, f'base {base:#x} not {self.max_align:#x}-aligned')
        _need(base + self.required <= U32 + 1, 'base + footprint overflows 32 bits')
        img = bytearray(self.stub_off)                  # BSS and gaps are zero
        for s in self.loads:
            img[s['va']:s['va'] + s['fsz']] = self.data[s['off']:s['off'] + s['fsz']]
        for r in self.relocs:
            addend = struct.unpack_from('<I', img, r)[0]
            _need(addend < self.mem_end, f'relocation addend {addend:#x} @ {r:#x} outside module')
            v = addend + base
            _need(v <= U32, 'relocated value overflows 32 bits')
            struct.pack_into('<I', img, r, v)
        L = self.layout
        host = self.module_off + L['host_offset']
        for f, o in L['host_fields']:
            _need(f in host_values, f'no binding value for host field {f}')
            struct.pack_into('<I', img, host + o, host_values[f] & U32)
        stub = bytes.fromhex('606a00b8') + struct.pack('<I', base + self.entry_off) + bytes.fromhex('ffd083c40461cc')
        assert len(stub) == STUB_LEN
        return bytes(img), stub


# --------------------------------------------------------------------------- XBE pins
class Pins:
    """Exact bytes the live title must show, taken from the frozen READONLY XBE."""

    def __init__(self, path=FROZEN_XBE, expected_sha=FROZEN_XBE_SHA256):
        b = Path(path).read_bytes()
        self.sha256 = sha256(b)
        _need(self.sha256 == expected_sha, f'frozen XBE sha mismatch {self.sha256}')
        _need(b[:4] == b'XBEH', 'not an XBE')
        base, _hs, img = struct.unpack_from('<III', b, 0x104)
        _need(base == XBE_LOAD, 'unexpected XBE base')
        self.image_lo, self.image_hi = base, base + img
        n, sh = struct.unpack_from('<II', b, 0x11C)
        self.secs = [struct.unpack_from('<5I', b, sh - base + i * 56) for i in range(n)]
        self.raw = b
        self.header = b[:HEADER_GUARD_LEN]
        self.sites = {}
        for name, (va, orig5, dlen, _bit) in HOOK_SITES.items():
            f, _v, _vs, _ra, _rs = self._sec(va, dlen)
            _need(f & 1, f'{name} site not in a writable XBE section')
            got = self.read(va, dlen)
            _need(got[:5] == orig5, f'{name} orig5 differs from frozen XBE')
            self.sites[name] = got
        self.methods = {k: self.read(REQUIRED_BINDINGS[k], METHOD_GUARD_LEN)
                        for k in ('submit_request', 'findclassdriver', 'add_complete', 'remove_complete')}

    def _sec(self, va, n):
        for s in self.secs:
            f, v, vs, ra, rs = s
            if v <= va and va + n <= v + min(vs, rs):
                return s
        raise LoaderError(f'{va:#x} not file-backed in XBE')

    def read(self, va, n):
        f, v, vs, ra, rs = self._sec(va, n)
        return self.raw[ra + va - v:ra + va - v + n]

    def verify_header(self, mem):
        """Live XBE header must equal the frozen u803 image EXCEPT that the kernel
        already decoded the entry point (0x128) and kernel thunk (0x158) fields
        into absolute VAs via the retail XOR keys. Required bindings, sections and
        the title timestamp are unchanged. This is read-only; nothing is written."""
        frozen = bytearray(self.header)
        disk_ep = struct.unpack_from('<I', frozen, 0x128)[0]
        disk_thunk = struct.unpack_from('<I', frozen, 0x158)[0]
        struct.pack_into('<I', frozen, 0x128, disk_ep ^ RETAIL_EP_KEY)
        struct.pack_into('<I', frozen, 0x158, disk_thunk ^ RETAIL_THUNK_KEY)
        live = mem.read(XBE_LOAD, HEADER_GUARD_LEN)
        _need(live[:0x178] == bytes(frozen), 'live XBE header != frozen u803 (decoded entry/thunk)')

    def verify_clock_receipt(self, getter_va, slot_va, ordinal):
        """Check a parent clock receipt: SDK GetTickCount body `A1 <slot> 8B 00 C3`
        reading an import slot whose thunk ordinal is KeTickCount. u32 __stdcall."""
        _need(self.read(getter_va, 8) == b'\xa1' + struct.pack('<I', slot_va) + b'\x8b\x00\xc3',
              'clock getter is not mov eax,[slot]; mov eax,[eax]; ret')
        thunk = struct.unpack_from('<I', self.raw, 0x158)[0] ^ 0x5B6D40B6   # retail key
        _need(thunk <= slot_va < thunk + 0x400 and (slot_va - thunk) % 4 == 0, 'slot not in thunk table')
        i = thunk
        while struct.unpack('<I', self.read(i, 4))[0]:
            i += 4
        _need(slot_va < i, 'slot past thunk terminator')
        _need(struct.unpack('<I', self.read(slot_va, 4))[0] == 0x80000000 | ordinal, 'slot ordinal mismatch')
        _need(ordinal == KE_TICK_COUNT_ORDINAL, f'ordinal {ordinal} is not KeTickCount')
        return getter_va

    def _thunk_ordinal(self, slot_va):
        thunk = struct.unpack_from('<I', self.raw, 0x158)[0] ^ 0x5B6D40B6   # retail key
        _need(thunk <= slot_va < thunk + 0x400 and (slot_va - thunk) % 4 == 0, 'slot not in thunk table')
        i = thunk
        while struct.unpack('<I', self.read(i, 4))[0]:
            i += 4
        _need(slot_va < i, 'slot past thunk terminator')
        return struct.unpack('<I', self.read(slot_va, 4))[0]

    def verify_irql_slot(self, field, slot_va):
        """F6 span: the injected value is the pinned import SLOT whose frozen thunk
        word is 0x80000000|ordinal (129 raise / 161 lower)."""
        want_va, ordinal = IRQL_SLOTS[field]
        _need(slot_va == want_va, f'{field}={slot_va:#x} != pinned {want_va:#x}')
        _need(self._thunk_ordinal(slot_va) == 0x80000000 | ordinal, f'{field} slot ordinal mismatch')
        return slot_va


# --------------------------------------------------------------------------- runtime
class GuardedMemory:
    """The only write path the loader has. Writes are confined to the parent's
    allocation receipt; the 7 pinned 5-byte hook sites are writable ONLY in
    rollback with an explicit allow flag. Reads are unrestricted."""

    def __init__(self, adapter, base, extent):
        self.a, self.base, self.extent = adapter, base, extent
        self.site_write_ok = False

    def read(self, addr, n):
        b = self.a.read(addr, n)
        _need(isinstance(b, (bytes, bytearray)) and len(b) == n, f'short read @ {addr:#x}')
        return bytes(b)

    def write(self, addr, data):
        inside = self.base <= addr and addr + len(data) <= self.base + self.extent
        site = self.site_write_ok and len(data) == 5 and any(addr == v[0] for v in HOOK_SITES.values())
        _need(inside or site, f'write {addr:#x}+{len(data)} outside allocation receipt refused')
        self.a.write(addr, bytes(data))


def e9(site_va, target):
    return b'\xe9' + struct.pack('<i', ((target - (site_va + 5) + 0x80000000) & U32) - 0x80000000)


class Journal:
    def __init__(self, path):
        self.path = Path(path) if path else None
        self.doc = None

    def open_new(self, doc):
        if self.path and self.path.exists():
            old = json.loads(self.path.read_text())
            _need(old.get('state') in ('closed', 'stale', 'refused'),
                  f'open journal exists (state {old.get("state")}); resolve it before a new load')
        self.doc = dict(doc, history=[])
        self.set('planned')

    def set(self, state, **kw):
        self.doc['state'] = state
        self.doc.update(kw)
        self.doc['history'].append(state)
        if self.path:
            tmp = self.path.with_suffix('.tmp')
            tmp.write_text(json.dumps(self.doc, indent=2))
            tmp.replace(self.path)

    @classmethod
    def load(cls, path):
        j = cls(path)
        j.doc = json.loads(Path(path).read_text())
        return j


class TitleLoader:
    def __init__(self, module, pins, bindings, clock=None):
        self.m, self.p = module, pins
        self.host = self._bind(bindings, clock)

    def _bind(self, b, clock):
        out = {}
        for k, v in REQUIRED_BINDINGS.items():
            _need(b.get(k) == v, f'binding {k}={b.get(k)} != pinned {v:#x}')
            out[k] = v
        for k in OPTIONAL_ZERO:
            _need(b.get(k, 0) == 0, f'{k} must be 0 (unused, unpinned)')
            out[k] = 0
        now = b.get('now_ms', 0)
        if now:
            _need(self.m.layout['now_ms_abi'] == 'stdcall_u32', 'module now_ms ABI is not u32 stdcall; must be 0')
            _need(clock is not None, 'nonzero now_ms needs a parent clock receipt')
            _need(now == self.p.verify_clock_receipt(**clock), 'now_ms != verified receipt getter')
        out['now_ms'] = now
        if self.m.has_irql:
            for k, (va, _o) in IRQL_SLOTS.items():
                out[k] = self.p.verify_irql_slot(k, b.get(k, va))
        extra = set(b) - set(out) - {'method_signatures', 'proof', 'target_sha256', 'target', 'scope',
                                     'target_header_guard'}
        _need(not extra, f'unknown binding fields {sorted(extra)}')
        return out

    # ---- plan: pure, no runtime access
    def plan(self, receipt):
        for k in ('base', 'extent', 'fill_byte', 'allocation_id'):
            _need(k in receipt, f'allocation receipt lacks {k}')
        base, extent = receipt['base'], receipt['extent']
        _need(isinstance(base, int) and isinstance(extent, int) and base > 0 and extent > 0, 'bad receipt numbers')
        _need(base + extent <= U32 + 1, 'receipt extent overflows 32 bits')
        _need(extent >= self.m.required, f'extent {extent:#x} < required {self.m.required:#x}')
        _need(base + extent <= self.p.image_lo or base >= self.p.image_hi,
              f'receipt overlaps title image [{self.p.image_lo:#x},{self.p.image_hi:#x})')
        _need(base >= 0x10000, 'receipt in low 64K')
        img, stub = self.m.image(base, self.host)
        sites = {}
        for name, (va, orig5, dlen, bit) in HOOK_SITES.items():
            sites[name] = dict(va=va, orig=self.p.sites[name].hex(),
                               expect=(e9(va, base + self.m.hook_off[name]) + self.p.sites[name][5:]).hex(),
                               target=base + self.m.hook_off[name], bit=bit)
        return dict(target_sha256=self.p.sha256, elf_sha256=self.m.sha256, allocation_id=receipt['allocation_id'],
                    base=base, extent=extent, fill_byte=receipt['fill_byte'], image_len=len(img),
                    required=self.m.required, mem_end=self.m.mem_end, relocs=len(self.m.relocs),
                    entry=base + self.m.entry_off, stub=base + self.m.stub_off,
                    stub_bp=base + self.m.stub_off + STUB_LEN - 1,
                    module=base + self.m.module_off, host=dict(self.host), sites=sites,
                    image_sha256=sha256(img), _img=img, _stub=stub)

    # ---- preflight: read-only, refuses before any write
    def preflight(self, mem, plan):
        self.p.verify_header(mem)
        # sites first: FindClassDriver's method guard overlaps its own hook site
        for name, s in plan['sites'].items():
            live = mem.read(s['va'], len(bytes.fromhex(s['orig'])))
            _need(live[:1] != b'\xe9', f'{name} already E9-patched (repeat install refused)')
            _need(live.hex() == s['orig'], f'{name} site bytes differ from frozen u803')
        for k, want in self.p.methods.items():
            _need(mem.read(REQUIRED_BINDINGS[k], METHOD_GUARD_LEN) == want, f'method guard {k} mismatch')
        if self.m.has_irql:     # kernel loader must have resolved both import slots
            for k, (va, ordinal) in IRQL_SLOTS.items():
                live = struct.unpack('<I', mem.read(va, 4))[0]
                _need(live != 0 and live != 0x80000000 | ordinal, f'{k} import slot unresolved live ({live:#x})')
        fill = bytes([plan['fill_byte']]) * plan['extent']
        _need(mem.read(plan['base'], plan['extent']) == fill,
              'allocation not in parent fill state (in use / previously loaded / not owned)')

    def load(self, adapter, receipt, journal_path=None, call_timeout=15):
        plan = self.plan(receipt)
        mem = GuardedMemory(adapter, plan['base'], plan['extent'])
        j = Journal(journal_path)
        self.preflight(mem, plan)                                   # zero writes so far
        j.open_new({k: v for k, v in plan.items() if not k.startswith('_')})
        img, stub = plan['_img'], plan['_stub']
        try:
            mem.write(plan['base'], img)
            mem.write(plan['stub'], stub)
            _need(mem.read(plan['base'], len(img)) == img, 'image readback mismatch')
            _need(mem.read(plan['stub'], STUB_LEN) == stub, 'stub readback mismatch')
        except Exception as e:
            self._scrub(mem, plan, j, f'image write failed: {e}')
            raise LoaderError(f'image write failed, region scrubbed: {e}') from e
        j.set('image_written')
        # sites must still be original: the image write touched nothing else
        for name, s in plan['sites'].items():
            _need(mem.read(s['va'], len(bytes.fromhex(s['orig']))).hex() == s['orig'], f'{name} changed before entry')
        j.set('entry_calling')
        regs = adapter.call_stub(plan['stub'], plan['stub_bp'], call_timeout)
        j.set('entry_returned', eax_informational=regs.get('eax'))
        return self.verify(mem, plan, j)

    def _scrub(self, mem, plan, j, why):
        try:
            fill = bytes([plan['fill_byte']]) * plan['extent']
            mem.write(plan['base'], fill)
            ok = mem.read(plan['base'], plan['extent']) == fill
        except Exception as e:   # adapter dead: say so, keep journal open-failed
            j.set('scrub_failed', error=f'{why}; scrub: {e}')
            raise LoaderError(f'{why}; scrub failed: {e}') from e
        j.set('closed' if ok else 'scrub_failed', error=why)
        _need(ok, f'{why}; scrub readback mismatch')

    def status(self, mem, plan):
        L = self.m.layout
        return {k: struct.unpack('<I', mem.read(plan['module'] + o, 4))[0] for k, o in L['status_fields'].items()}

    def verify(self, mem, plan, j):
        L = self.m.layout
        st = self.status(mem, plan)
        host = mem.read(plan['module'] + L['host_offset'], L['host_size'])
        _need(host == plan['_img'][self.m.module_off + L['host_offset']:][:L['host_size']], 'host struct changed')
        live = {n: mem.read(s['va'], len(bytes.fromhex(s['orig']))).hex() for n, s in plan['sites'].items()}
        all_orig = all(live[n] == s['orig'] for n, s in plan['sites'].items())
        all_hook = all(live[n] == s['expect'] for n, s in plan['sites'].items())
        res = dict(status=st, sites=live)
        if st['install_failed'] == 0 and st['installed_hooks'] == L['expected_installed_hooks'] and all_hook:
            j.set('verified_installed', result=res)
            return dict(res, verdict='installed')
        if st['install_failed'] == 1 and st['installed_hooks'] == 0 and all_orig:
            j.set('entry_refused_failclosed', result=res)
            return dict(res, verdict='refused_failclosed')
        j.set('inconsistent_halt', result=res)
        raise LoaderError(f'inconsistent post-entry state; keep CPU halted and inspect: {res}')

    # ---- rollback (parent safe point only); refuses stale journals
    def rollback(self, adapter, journal_path, allow_hook_restore=False):
        j = Journal.load(journal_path)
        d = j.doc
        _need(d['state'] not in ('closed', 'stale'), f'journal already {d["state"]}')
        _need(d['elf_sha256'] == self.m.sha256 and d['target_sha256'] == self.p.sha256, 'journal for other build')
        mem = GuardedMemory(adapter, d['base'], d['extent'])
        img_head = self.m.image(d['base'], self.host)[0][:256]
        live_head = mem.read(d['base'], 256)
        live = {n: mem.read(s['va'], len(bytes.fromhex(s['orig']))).hex() for n, s in d['sites'].items()}
        if live_head != img_head:
            # region no longer holds our image: title restarted / memory reused.
            # Restoring anything would write to addresses that are no longer ours.
            j.set('stale', error='region does not hold this image; nothing written')
            raise LoaderError('stale journal: region no longer holds the module; no write performed')
        hooked = [n for n, s in d['sites'].items() if live[n] == s['expect']]
        other = [n for n, s in d['sites'].items() if live[n] not in (s['expect'], s['orig'])]
        _need(not other, f'sites in unknown state {other}; refuse')
        if hooked:
            _need(allow_hook_restore, 'hooks are live; reload the title, or pass allow_hook_restore at a safe point')
            mem.site_write_ok = True
            try:
                for n in hooked:
                    s = d['sites'][n]
                    mem.write(s['va'], bytes.fromhex(s['orig'])[:5])
                    _need(mem.read(s['va'], 5) == bytes.fromhex(s['orig'])[:5], f'{n} restore readback')
            finally:
                mem.site_write_ok = False
        self._scrub(mem, d, j, 'rollback')
        return dict(restored_sites=hooked)


# --------------------------------------------------------------------------- GDB adapter
class GdbRspAdapter:
    """Thin wrapper over the EXISTING LAN_Stats tools/xemu/gdbrsp.RSP client,
    following inject_trainer.run_stub discipline: save raw regs + borrowed stack,
    plant a GDB breakpoint on the stub's INT3, continue, assert the stop EIP,
    restore. An unexpected stop raises and leaves the CPU halted. The CPU must
    already be stopped by the parent at its chosen safe point."""

    STACK_SAVE = 0x1000

    def __init__(self, rsp):
        self.r = rsp

    def read(self, addr, n):
        return self.r.read(addr, n)

    def write(self, addr, data):
        self.r.write(addr, data)

    def call_stub(self, stub, bp, timeout):
        saved = self.r.raw_regs()
        regs = self.r.regs()
        sp = regs['esp'] - self.STACK_SAVE
        stack = self.r.read(sp, self.STACK_SAVE)
        self.r.set_regs(eip=stub)
        self.r.bp(bp)
        try:
            reason = self.r.continue_wait(timeout)
        finally:
            self.r.bp(bp, False)
        after = self.r.regs()
        if after['eip'] not in (bp, bp + 1) or after['esp'] != regs['esp']:
            raise LoaderError(f'unexpected stop {reason} eip={after["eip"]:#x}; CPU left halted')
        self.r.write(sp, stack)
        self.r.set_raw_regs(saved)
        _need(self.r.raw_regs() == saved, 'register restore mismatch')
        return dict(after, reason=reason)


def connect_existing_gdb(host='127.0.0.1', port=1234):
    import sys
    sys.path.insert(0, '/home/roasted/Desktop/Xbox/LAN_Stats/tools/xemu')
    from gdbrsp import RSP
    return GdbRspAdapter(RSP(host, port))


def main(argv=None):
    import argparse
    here = Path(__file__).resolve().parent
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('cmd', choices=['plan', 'load', 'status', 'rollback'])
    ap.add_argument('--elf', required=True)
    ap.add_argument('--layout', required=True)
    ap.add_argument('--bindings', default=str(here.parents[1] / 'work/26-u803-bindings/bindings.json'))
    ap.add_argument('--receipt', help='parent allocation receipt JSON {base,extent,fill_byte,allocation_id}')
    ap.add_argument('--journal')
    ap.add_argument('--gdb', default='127.0.0.1:1234')
    ap.add_argument('--allow-hook-restore', action='store_true')
    a = ap.parse_args(argv)
    m = Module(Path(a.elf).read_bytes(), json.loads(Path(a.layout).read_text()))
    tl = TitleLoader(m, Pins(), json.loads(Path(a.bindings).read_text()))
    if a.cmd == 'plan':
        rc = json.loads(Path(a.receipt).read_text())
        p = tl.plan(rc)
        print(json.dumps({k: v for k, v in p.items() if not k.startswith('_')}, indent=2))
        return 0
    host, port = a.gdb.rsplit(':', 1)
    ad = connect_existing_gdb(host, int(port))
    if a.cmd == 'load':
        print(json.dumps(tl.load(ad, json.loads(Path(a.receipt).read_text()), a.journal), indent=2))
    elif a.cmd == 'status':
        d = Journal.load(a.journal).doc
        print(json.dumps(tl.status(GuardedMemory(ad, d['base'], d['extent']), d), indent=2))
    else:
        print(json.dumps(tl.rollback(ad, a.journal, a.allow_hook_restore), indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
