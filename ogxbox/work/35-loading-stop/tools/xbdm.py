#!/usr/bin/env python3
"""Offline analysis of a probe dump of XBDM (image at 0xB0000000).
usage: xbdm.py DUMP.bin [dis ADDR LEN]... [xref ADDR]... [str PATTERN]...
"""
import struct, subprocess, sys, os, re, json

B = 0xB0000000
m = open(sys.argv[1], 'rb').read()
H = m.index(b"MZ\x90\x00"); IB = B + H
pe = H + struct.unpack_from("<I", m, H + 0x3c)[0]
nsec = struct.unpack_from('<H', m, pe + 6)[0]
opt = struct.unpack_from('<H', m, pe + 20)[0]
o = pe + 24
info = {'image_at': hex(IB), 'pe': m[pe:pe+4].hex(), 'timestamp': hex(struct.unpack_from('<I', m, pe + 8)[0]),
        'imagebase': hex(struct.unpack_from('<I', m, o + 28)[0]), 'sizeofimage': hex(struct.unpack_from('<I', m, o + 56)[0]),
        'entry': hex(B + struct.unpack_from('<I', m, o + 16)[0]), 'sections': []}
for i in range(nsec):
    n, vs, va = struct.unpack_from('<8sII', m, o + opt + 40 * i); va += H
    info['sections'].append([n.rstrip(b'\0').decode(), hex(B + va), hex(vs)])
names = {}
erva = struct.unpack_from('<I', m, o + 96)[0]; erva = erva + H if erva else 0
if erva:
    nm = H + struct.unpack_from('<I', m, erva + 12)[0]
    info['dll'] = m[nm:m.index(b'\0', nm)].decode()
    base, nf, nn, af, an, ao = struct.unpack_from('<IIIIII', m, erva + 16)
    fun = [H + struct.unpack_from('<I', m, H + af + 4 * i)[0] for i in range(nf)]
    named = set()
    for i in range(nn):
        r = H + struct.unpack_from('<I', m, H + an + 4 * i)[0]
        od = struct.unpack_from('<H', m, H + ao + 2 * i)[0]
        names[B + fun[od]] = m[r:m.index(b'\0', r)].decode(); named.add(od)
    for i, f in enumerate(fun):
        if i not in named and f:
            names.setdefault(B + f, f'ord{base+i}')
    info['exports'] = len(names)


def near(a):
    best = max((x for x in names if x <= a), default=None)
    return f'{names[best]}+{a-best:#x}' if best else '?'


args = sys.argv[2:]
if not args:
    print(json.dumps(info, indent=1))
i = 0
while i < len(args):
    k = args[i]
    if k == 'dis':
        a, n = int(args[i+1], 16), int(args[i+2], 16); i += 3
        tmp = os.environ.get('TMPDIR', '/tmp') + '/xbdm_dis.bin'
        open(tmp, 'wb').write(m[a-B:a-B+n])
        out = subprocess.run(['objdump', '-D', '-b', 'binary', '-mi386', '-Mintel', f'--adjust-vma={a:#x}', tmp],
                             capture_output=True, text=True).stdout
        print(f'== dis {a:#x} ({near(a)})')
        for line in out.splitlines()[7:]:
            mm = re.search(r'0x(b0[0-9a-f]{6})', line)
            print(line + (f'   ; {near(int(mm.group(1),16))}' if mm else ''))
    elif k == 'xref':  # direct call/jmp rel32 and absolute dword refs
        t = int(args[i+1], 16); i += 2
        hits = []
        for p in range(len(m) - 5):
            if m[p] in (0xe8, 0xe9) and (B + p + 5 + struct.unpack_from('<i', m, p+1)[0]) & 0xffffffff == t:
                hits.append(f'{"call" if m[p]==0xe8 else "jmp"}@{B+p:#x} ({near(B+p)})')
        for p in range(len(m) - 3):
            if struct.unpack_from('<I', m, p)[0] == t:
                hits.append(f'abs@{B+p:#x} ({near(B+p)})')
        print(f'== xref {t:#x}:', hits)
    elif k == 'str':
        pat = args[i+1].encode(); i += 2
        for mm in re.finditer(pat, m, re.I):
            s = mm.start()
            while s > 0 and 32 <= m[s-1] < 127: s -= 1
            e = m.index(b'\0', mm.start())
            print(f'str {B+s:#x}: {m[s:e][:120]!r}')
    elif k == 'near':
        print(args[i+1], near(int(args[i+1], 16))); i += 2
    elif k == 'exports':
        i += 1
        for a in sorted(names): print(hex(a), names[a])
