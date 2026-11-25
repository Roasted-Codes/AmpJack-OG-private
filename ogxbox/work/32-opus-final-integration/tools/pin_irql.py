#!/usr/bin/env python3
"""pin_irql.py -- pin the two IRQL kernel imports the F6 critical span uses,
from the FROZEN u803 XBE (read-only) and the local XDK 5849 xboxkrnl.lib import
short records. Stdlib + objdump only. Exit 0 only if every check holds.

Checks
  1. frozen XBE sha256.
  2. kernel thunk table (retail key) slot 0x41B700 = 0x80000000|129 and
     0x41B6FC = 0x80000000|161, both before the terminator.
  3. xboxkrnl.lib import short records: ordinal 129 = _KeRaiseIrqlToDpcLevel@0
     (stdcall, 0 arg bytes), ordinal 161 = @KfLowerIrql@4 (fastcall, 1 arg -> ECX/CL).
  4. XInputGetState (0x413C4C) full body: `call [0x41B700]` then the result
     (AL) is moved into CL before `call [0x41B6FC]` on every return path.
"""
import hashlib, struct, subprocess, sys, re, json

XBE = '/home/roasted/Desktop/Xbox/H2-Decomp/tu15-decomp/targets/halo2-tu15-u803/default.xbe'
XBE_SHA = '21b207e7efdacaf6124a0822837f8be570766a42505057f7fd2d2ba8f409c4fd'
LIB = '/home/roasted/Desktop/Xbox/H2-Decomp/tu15-decomp/work/xdk5849/XDK/xbox/lib/xboxkrnl.lib'
RAISE_SLOT, LOWER_SLOT = 0x41B700, 0x41B6FC
RAISE_ORD, LOWER_ORD = 129, 161
GETSTATE, GETSTATE_LEN = 0x413C4C, 0x73        # up to XInputSetState 0x413CBF

ok = True
out = {}
def check(name, cond, info: object = ''):
    global ok
    ok &= bool(cond)
    print(('PASS ' if cond else 'FAIL ') + name + (('  ' + str(info)) if info else ''))

b = open(XBE, 'rb').read()
sha = hashlib.sha256(b).hexdigest()
check('frozen XBE sha256', sha == XBE_SHA, sha)
base = struct.unpack_from('<I', b, 0x104)[0]
n, sh = struct.unpack_from('<II', b, 0x11C)
secs = [struct.unpack_from('<5I', b, sh - base + i * 56) for i in range(n)]
def rd(va, k):
    for f, v, vs, ra, rs in secs:
        if v <= va and va + k <= v + min(vs, rs):
            return b[ra + va - v: ra + va - v + k]
    raise SystemExit(f'{va:#x} not file-backed')
thunk = struct.unpack_from('<I', b, 0x158)[0] ^ 0x5B6D40B6
ords = {}
i = thunk
while True:
    w = struct.unpack('<I', rd(i, 4))[0]
    if not w:
        break
    ords[i] = w
    i += 4
check('thunk table located', thunk <= RAISE_SLOT < i and thunk <= LOWER_SLOT < i, f'{thunk:#x}..{i:#x}')
check('slot 0x41B700 = ordinal 129', ords.get(RAISE_SLOT) == 0x80000000 | RAISE_ORD, hex(ords.get(RAISE_SLOT, 0)))
check('slot 0x41B6FC = ordinal 161', ords.get(LOWER_SLOT) == 0x80000000 | LOWER_ORD, hex(ords.get(LOWER_SLOT, 0)))

# import short records (IMPORT_OBJECT_HEADER: Sig1=0, Sig2=0xFFFF)
d = open(LIB, 'rb').read()
names = {}
off = 8
while off + 60 <= len(d):
    size = int(d[off + 48: off + 58].decode().strip())
    m = d[off + 60: off + 60 + size]
    if len(m) >= 20 and struct.unpack_from('<HH', m, 0) == (0, 0xFFFF):
        _v, mach, _ts, sod, hint, typ = struct.unpack_from('<HHIIHH', m, 4)
        sym = m[20:].split(b'\0')[0].decode()
        if typ & 3 == 0 and (typ >> 2) & 7 == 0:       # IMPORT_CODE, IMPORT_ORDINAL
            names.setdefault(hint, set()).add(sym)
    off += 60 + size + (size & 1)
check('lib ordinal 129 = _KeRaiseIrqlToDpcLevel@0 (stdcall, no args)', '_KeRaiseIrqlToDpcLevel@0' in names.get(RAISE_ORD, ()), sorted(names.get(RAISE_ORD, ())))
check('lib ordinal 161 = @KfLowerIrql@4 (fastcall, NewIrql in CL)', '@KfLowerIrql@4' in names.get(LOWER_ORD, ()), sorted(names.get(LOWER_ORD, ())))

# XInputGetState full body
code = rd(GETSTATE, GETSTATE_LEN)
import tempfile, os
with tempfile.NamedTemporaryFile(delete=False, suffix='.bin') as tf:
    tf.write(code)
p = subprocess.run(['objdump', '-D', '-b', 'binary', '-mi386', '-Mintel', f'--adjust-vma={GETSTATE:#x}', tf.name],
                   capture_output=True)
os.unlink(tf.name)
lines = [l for l in p.stdout.decode().splitlines() if re.match(r'\s+[0-9a-f]+:', l)]
body = '\n'.join(lines)
print(body)
raise_calls = [l for l in lines if 'call' in l and '0x41b700' in l]
lower_calls = [l for l in lines if 'call' in l and '0x41b6fc' in l]
check('GetState calls [0x41B700] (raise)', len(raise_calls) >= 1, len(raise_calls))
check('GetState calls [0x41B6FC] (lower)', len(lower_calls) >= 1, len(lower_calls))
# every lower is preceded by mov cl,<saved irql>; the saved value originates from al after the raise
ok_cl = True
for idx, l in enumerate(lines):
    if 'call' in l and '0x41b6fc' in l:
        prev = ' '.join(lines[max(0, idx - 3): idx])
        ok_cl &= bool(re.search(r'mov\s+cl,', prev))
check('each lower passes NewIrql in CL (fastcall)', ok_cl and lower_calls)
ri = lines.index(raise_calls[0]) if raise_calls else 0
li = lines.index(lower_calls[0]) if lower_calls else 0
between = [l.split('\t')[-1] for l in lines[ri + 1: li]]
clobber = [x for x in between if re.match(r'\S+\s+(eax|ax|al)\b', x) or (re.match(r'(pop|call|xchg)\s', x) and 'eax' in x)]
check('raise result kept in AL (no eax/al write between raise and lower)', bool(raise_calls and lower_calls and not clobber), clobber)
check('lower is immediately preceded by mov cl,al', bool(li and re.search(r'mov\s+cl,al', lines[li - 1])), lines[li - 1].split('\t')[-1] if li else '')
print('RESULT', 'PASS' if ok else 'FAIL')
sys.exit(0 if ok else 1)
