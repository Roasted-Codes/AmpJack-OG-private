#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Repackage selected exact W63 module; compile flags-OFF pre-entry wrapper."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import zipfile
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
sys.path.insert(0, str(ROOT))
import host_helpers as W32
spec = importlib.util.spec_from_file_location('trainerfmt', REPO/'tools/trainerfmt.py')
assert spec is not None and spec.loader is not None
TF = importlib.util.module_from_spec(spec)
spec.loader.exec_module(TF)
VERSION = '0.1.0-preview.1'
NAMES = ('OG-AmpJack-Halo2.xbtf', 'OG-AmpJack-Halo2.bin')
ZIP_NAME = 'OG-AmpJack-Halo2-v'+VERSION+'.zip'
NATIVE_PATH = '\\Device\\Harddisk0\\Partition1\\Trainers\\'+NAMES[1]
PAYLOAD_SHA = '8bf54869e1635fbcb8313226da7abd243c0b4fc4729b1b664f2828e030380448'
ELF_SHA = '3ddc05b8c0c01a388ad9ab156660c8018a8a3d0fe4cc676af7548a5405ec7fab'

def sha(b): return hashlib.sha256(b).hexdigest()
def doc(p): return json.loads(p.read_text())

def verify_inputs():
    p = doc(ROOT/'inputs/provenance.json')
    assert p['payload_sha256'] == PAYLOAD_SHA and p['elf_sha256'] == ELF_SHA
    for name, digest in p['pinned_inputs'].items():
        assert sha((ROOT/'inputs'/name).read_bytes()) == digest, name
    for name, digest in p['wrapper_sources'].items():
        assert sha((ROOT/name).read_bytes()) == digest, name
    for name, digest in p['controller_sources'].items():
        assert sha((ROOT/'../work/63-wake-rumble'/name).read_bytes()) == digest, name
    source_root = ROOT/'../work/63-wake-rumble'
    actual = {f.relative_to(source_root).as_posix() for f in (source_root/'src').rglob('*') if f.is_file() and 'out' not in f.relative_to(source_root/'src').parts}
    assert actual == set(p['controller_sources']), 'source coverage mismatch'
    assert sha((ROOT/'inputs/module.bin').read_bytes()) == PAYLOAD_SHA
    assert sha((ROOT/'inputs/module.elf').read_bytes()) == ELF_SHA
    return p

def module():
    return W32.Module((ROOT/'inputs/module.elf').read_bytes(), doc(ROOT/'inputs/layout.json'))

def package(m):
    assert m.sha256 == ELF_SHA and m.layout == doc(ROOT/'inputs/layout.json'), 'incompatible layout'
    assert len(m.relocs) == len(set(m.relocs)), 'duplicate relocation'
    end = max(s['va']+s['fsz'] for s in m.loads)
    image = bytearray(end)
    for s in m.loads: image[s['va']:s['va']+s['fsz']] = m.data[s['off']:s['off']+s['fsz']]
    for r in m.relocs: assert r <= end-4 and struct.unpack_from('<I', image, r)[0] < m.mem_end
    hdr = struct.pack('<16I', 0x33344a41, 1, 64+end+4*len(m.relocs), end, m.mem_end, m.entry_off, m.module_off, len(m.relocs), 64, *([0]*7))
    result = hdr+image+b''.join(struct.pack('<I', r) for r in m.relocs)
    assert sha(result) == PAYLOAD_SHA, 'module envelope differs from selected W63'
    return result

def check_payload(data, m):
    if data != package(m): raise ValueError('payload metadata, image or relocation mismatch')
    return True

def inputs(xbe):
    m = module()
    p = W32.Pins(xbe)
    values = [0x4155bf,0x41517d,0x416992,0,0x4165c6,0x4127b4,0x4127cc,0x4127d8,0,0x41b700,0x41b6fc]
    j = {'base':0, 'host':dict(zip((n for n,_ in m.layout['host_fields']), values)), 'sites':{n:{'va':v[0], 'target':m.hook_off[n], 'orig':p.sites[n].hex()} for n,v in W32.HOOK_SITES.items()}}
    return m,p,j,None

def run(cmd):
    r = subprocess.run(list(map(str, cmd)), check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return r.stdout

def check(out):
    man = doc(out/'manifest.json')
    for name,key in zip(NAMES, ('trainer_sha256','payload_sha256')):
        assert sha((out/'candidate'/name).read_bytes()) == man[key], 'stale manifest'
    check_payload((out/'candidate'/NAMES[1]).read_bytes(), module())
    data, info = TF.parse((out/'candidate'/NAMES[0]).read_bytes(), True)
    assert info['name'] == 'OG-AmpJack - Halo 2'
    assert info['creation_key'] == 'AMPJAK-HALO2' and info['creation_key'][6] == '-'
    assert info['title_ids'] == ['0x4d530064','0x0','0x0']
    assert len(info['options']) == 1 and info['options'][0]['label'] == 'Enable controller support' and info['options'][0]['default'] == 0
    assert info['fits_xbmc_heap'] and len(data) <= 15193
    assert NATIVE_PATH.encode()+b'\0' in data
    assert man['resident_alloc'] == 45056 and man['file_buffer_alloc'] == 24576
    assert man['image_size'] == 20492 and man['mem_end'] == 43912
    assert man['module_entry_flags'] == 0 and man['logging'] == 'OFF'
    return data, man

def build(out):
    out = Path(out).resolve()
    # Never overwrite input/source directories; caller may reuse a valid output.
    assert out != ROOT and not ROOT.is_relative_to(out)
    assert not out.is_relative_to(ROOT/'inputs')
    if out.exists() and any(out.iterdir()):
        assert (out/'manifest.json').is_file(), 'output must be new or an existing release output'
    provenance = verify_inputs()
    m = module()
    payload = (ROOT/'inputs/module.bin').read_bytes()
    check_payload(payload, m)
    out.mkdir(parents=True, exist_ok=True)
    work = out/'.build'; work.mkdir(exist_ok=True)
    pins = (ROOT/'inputs/pins.h').read_text()
    assert pins.count('AmpJack63-u803-3ddc05b8.bin') == 1
    pins = pins.replace('AmpJack63-u803-3ddc05b8.bin', NAMES[1])
    (work/'pins.h').write_text(pins)
    flags = ['clang','-target','i386-unknown-none-elf','-march=pentium3','-Os','-ffreestanding','-nostdlib','-fpie','-fvisibility=hidden','-mgeneral-regs-only','-mstack-alignment=4','-fno-stack-protector','-fno-asynchronous-unwind-tables','-fno-unwind-tables','-Wall','-Wextra','-Werror','-I',work,'-I',ROOT]
    run(flags+['-c',ROOT/'loader.c','-o',work/'loader.o'])
    run(['clang','-target','i386-unknown-none-elf','-c',ROOT/'bootstrap.S','-o',work/'bootstrap.o'])
    run(['ld.lld','-pie','--no-dynamic-linker','-z','text','-z','norelro','--hash-style=sysv','-T',ROOT/'bootstrap.ld',work/'bootstrap.o',work/'loader.o','-o',work/'bootstrap.elf'])
    rel = run(['readelf','-S','-l','-r',work/'bootstrap.elf'])
    assert 'R_386' not in rel, 'wrapper dynamic relocation'
    symbols = {x[2]:int(x[0],16) for line in run(['nm','-an',work/'bootstrap.elf']).splitlines() if len(x:=line.split()) == 3}
    run(['objcopy','-O','binary',work/'bootstrap.elf',work/'bootstrap.bin'])
    code = (work/'bootstrap.bin').read_bytes()
    assert symbols['trainer_entry'] == 0 and symbols['boot_end'] == len(code)
    data = TF.build_data(code,[0x4d530064],'OG-AmpJack - Halo 2','Selected W63; logging OFF; branded wrapper hardware untested',['Enable controller support'],[False])
    trainer = TF.build_xbtf(data, creation_key='AMPJAK-HALO2', scroller='')
    candidate = out/'candidate'; candidate.mkdir(exist_ok=True)
    (candidate/NAMES[0]).write_bytes(trainer)
    (candidate/NAMES[1]).write_bytes(payload)
    manifest = {'version':VERSION,'name':'OG-AmpJack - Halo 2','hardware_status':'Branded wrapper UNTESTED; selected original W63 identified live, owner reports input/rumble working after replug; logging OFF; earlier black-screen condition unresolved','module_entry_flags':0,'logging':'OFF','provenance':provenance,'elf_sha256':ELF_SHA,'payload_sha256':sha(payload),'trainer_sha256':sha(trainer),'resident_alloc':45056,'file_buffer_alloc':24576,'image_size':20492,'mem_end':m.mem_end,'module_struct':m.layout['module_size'],'trainer_file_bytes':len(trainer),'trainer_decoded_bytes':len(data),'trainer_xbmc_allocation':16384,'peak_allocations_with_xbmc':45056+24576+16384,'resident_with_xbmc':45056+16384,'bootstrap_symbols':symbols,'wrapper_dynamic_relocations':False,'native_payload_path':NATIVE_PATH,'packaging_sources':{p.relative_to(ROOT).as_posix():sha(p.read_bytes()) for p in sorted(ROOT.iterdir()) if p.is_file() and p.suffix in ('.py','.c','.S','.ld','.inc','.md','.txt')},'trainerfmt_sha256':sha((REPO/'tools/trainerfmt.py').read_bytes())}
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n')
    check(out)
    files = ['candidate/'+n for n in NAMES]+['README.md','COPYING.GPL-3','NOTICES.txt','manifest.json']
    for name in ('README.md','COPYING.GPL-3','NOTICES.txt'): shutil.copyfile(ROOT/name,out/name)
    with zipfile.ZipFile(out/ZIP_NAME,'w',compression=zipfile.ZIP_STORED) as z:
        for name in sorted(files):
            zi = zipfile.ZipInfo(name, (2026,1,1,0,0,0)); zi.external_attr = 0o100644 << 16
            z.writestr(zi, (out/name).read_bytes())
    (out/'SHA256SUMS').write_text(''.join(sha((out/n).read_bytes())+'  '+n+'\n' for n in sorted(files+[ZIP_NAME])))
    print('PASS OG-AmpJack - Halo 2 '+VERSION+'; exact selected W63 payload; flags=0; default OFF; resident=45056 file=24576; wrapper relocations=0')
    print('candidate/'+NAMES[0]+'; candidate/'+NAMES[1]+'; '+ZIP_NAME+'; manifest.json; SHA256SUMS')
    return out

if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out',type=Path,default=ROOT/'dist')
    build(ap.parse_args().out)
