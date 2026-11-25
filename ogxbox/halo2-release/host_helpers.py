# SPDX-License-Identifier: GPL-3.0-or-later
# Pure host helpers from work/32; no live console adapter.
import hashlib
import json
import struct
from pathlib import Path

FROZEN_XBE = None  # Caller must explicitly supply an owner-provided XBE.
FROZEN_XBE_SHA256 = '21b207e7efdacaf6124a0822837f8be570766a42505057f7fd2d2ba8f409c4fd'
XBE_LOAD = 0x10000
HEADER_GUARD_LEN = 0x178           # image header through the cert pointer area

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



def e9(site_va, target):
    return b"\xe9" + struct.pack("<I", (target-site_va-5)&0xffffffff)
