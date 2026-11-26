#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Package the pinned controller module and build the OG-AmpJack trainer."""
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
REPO = ROOT.parent
INPUTS = ROOT/'inputs'
TRAINER_SRC = REPO/'src/trainer'
sys.path.insert(0, str(ROOT))
import host_helpers as W32
spec = importlib.util.spec_from_file_location('trainerfmt', ROOT/'trainerfmt.py')
assert spec is not None and spec.loader is not None
TF = importlib.util.module_from_spec(spec)
spec.loader.exec_module(TF)
VERSION = '0.1.0'
NAMES = ('OG-AmpJack.xbtf', 'OG-AmpJack.bin')
PAIR = 'Trainers'
ZIP_NAME = 'OG-AmpJack-v0.1.0.zip'
assert ZIP_NAME == 'OG-AmpJack-v'+VERSION+'.zip'
NATIVE_PATH = '\\Device\\Harddisk0\\Partition1\\Trainers\\'+NAMES[1]
PAYLOAD_SHA = '5e63fb1afb9c26d15af8165471e2a982171db1f1e9a2fc6c4d6114bd148ec39c'
ELF_SHA = '5850fc63b387eca58f1dcccae3a390341b66f999bd04d75ee12ddb18135d362b'

def sha(b): return hashlib.sha256(b).hexdigest()
def PACKAGING_SOURCES():
    return sorted([*ROOT.glob('*.py'), *(ROOT/'release').iterdir(), *TRAINER_SRC.iterdir(), REPO/'LICENSE'])
def doc(p): return json.loads(p.read_text())

def verify_inputs():
    p = doc(INPUTS/'provenance.json')
    assert p['payload_sha256'] == PAYLOAD_SHA and p['elf_sha256'] == ELF_SHA
    source_root = (INPUTS/p['source_root']).resolve()
    assert source_root == REPO, 'source_root must be the repository root'
    for name, digest in p['pinned_inputs'].items():
        assert sha((INPUTS/name).read_bytes()) == digest, name
    sources = {**p['controller_sources'], **p['trainer_sources']}
    for name, digest in sources.items():
        assert sha((source_root/name).read_bytes()) == digest, name
    actual = {f.relative_to(source_root).as_posix() for f in (source_root/'src').rglob('*') if f.is_file() and 'out' not in f.relative_to(source_root/'src').parts and '__pycache__' not in f.parts}
    assert actual == set(sources), 'source coverage mismatch'
    assert sha((INPUTS/'module.bin').read_bytes()) == PAYLOAD_SHA
    assert sha((INPUTS/'module.elf').read_bytes()) == ELF_SHA
    return p

def module():
    return W32.Module((INPUTS/'module.elf').read_bytes(), doc(INPUTS/'layout.json'))

def package(m):
    assert m.sha256 == ELF_SHA and m.layout == doc(INPUTS/'layout.json'), 'incompatible layout'
    assert len(m.relocs) == len(set(m.relocs)), 'duplicate relocation'
    end = max(s['va']+s['fsz'] for s in m.loads)
    image = bytearray(end)
    for s in m.loads: image[s['va']:s['va']+s['fsz']] = m.data[s['off']:s['off']+s['fsz']]
    for r in m.relocs: assert r <= end-4 and struct.unpack_from('<I', image, r)[0] < m.mem_end
    hdr = struct.pack('<16I', 0x33344a41, 1, 64+end+4*len(m.relocs), end, m.mem_end, m.entry_off, m.module_off, len(m.relocs), 64, *([0]*7))
    result = hdr+image+b''.join(struct.pack('<I', r) for r in m.relocs)
    assert sha(result) == PAYLOAD_SHA, 'module envelope differs from the pinned payload'
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
        assert sha((out/PAIR/name).read_bytes()) == man[key], 'stale manifest'
    check_payload((out/PAIR/NAMES[1]).read_bytes(), module())
    data, info = TF.parse((out/PAIR/NAMES[0]).read_bytes(), True)
    assert info['name'] == 'OG-AmpJack'
    assert info['creation_key'] == 'AMPJAK-HALO2' and info['creation_key'][6] == '-'
    assert info['title_ids'] == ['0x4d530064','0x0','0x0']
    assert len(info['options']) == 1 and info['options'][0]['label'] == 'Enable controller support' and info['options'][0]['default'] == 0
    assert info['fits_xbmc_heap'] and len(data) <= 15193
    assert NATIVE_PATH.encode()+b'\0' in data
    assert man['resident_alloc'] == 36864 and man['file_buffer_alloc'] == 16384
    assert man['image_size'] == 14992 and man['mem_end'] == 36220
    assert man['entry_argument'] == 0 and man['logging'] == 'none'
    return data, man

def build(out):
    out = Path(out).resolve()
    # Never overwrite input/source directories; caller may reuse a valid output.
    assert not ROOT.is_relative_to(out) and not out.is_relative_to(ROOT)
    assert not out.is_relative_to(REPO/'src') and not out.is_relative_to(REPO/'tests')
    if out.exists() and any(out.iterdir()):
        assert (out/'manifest.json').is_file(), 'output must be new or an existing release output'
    provenance = verify_inputs()
    m = module()
    payload = (INPUTS/'module.bin').read_bytes()
    check_payload(payload, m)
    out.mkdir(parents=True, exist_ok=True)
    work = out/'.build'; work.mkdir(exist_ok=True)
    pins = (INPUTS/'pins.h').read_text()
    assert pins.count('AmpJack65R-u803-5850fc63.bin') == 1
    pins = pins.replace('AmpJack65R-u803-5850fc63.bin', NAMES[1])
    (work/'pins.h').write_text(pins)
    flags = ['clang','-target','i386-unknown-none-elf','-march=pentium3','-Os','-ffreestanding','-nostdlib','-fpie','-fvisibility=hidden','-mgeneral-regs-only','-mstack-alignment=4','-fno-stack-protector','-fno-asynchronous-unwind-tables','-fno-unwind-tables','-Wall','-Wextra','-Werror','-I',work,'-I',TRAINER_SRC]
    run(flags+['-c',TRAINER_SRC/'loader.c','-o',work/'loader.o'])
    run(['clang','-target','i386-unknown-none-elf','-c',TRAINER_SRC/'bootstrap.S','-o',work/'bootstrap.o'])
    run(['ld.lld','-pie','--no-dynamic-linker','-z','text','-z','norelro','--hash-style=sysv','-T',TRAINER_SRC/'bootstrap.ld',work/'bootstrap.o',work/'loader.o','-o',work/'bootstrap.elf'])
    rel = run(['readelf','-S','-l','-r',work/'bootstrap.elf'])
    assert 'R_386' not in rel, 'trainer stub has dynamic relocations'
    symbols = {x[2]:int(x[0],16) for line in run(['nm','-an',work/'bootstrap.elf']).splitlines() if len(x:=line.split()) == 3}
    run(['objcopy','-O','binary',work/'bootstrap.elf',work/'bootstrap.bin'])
    code = (work/'bootstrap.bin').read_bytes()
    assert symbols['trainer_entry'] == 0 and symbols['boot_end'] == len(code)
    data = TF.build_data(code,[0x4d530064],'OG-AmpJack','Wired Xbox One / Series controller support for Halo 2 (port 2)',['Enable controller support'],[False])
    trainer = TF.build_xbtf(data, creation_key='AMPJAK-HALO2', scroller='')
    pair = out/PAIR; pair.mkdir(exist_ok=True)
    (pair/NAMES[0]).write_bytes(trainer)
    (pair/NAMES[1]).write_bytes(payload)
    manifest = {'version':VERSION,'name':'OG-AmpJack','console_tested':'input, wake, rumble, all buttons','entry_argument':0,'logging':'none','provenance':provenance,'elf_sha256':ELF_SHA,'payload_sha256':sha(payload),'trainer_sha256':sha(trainer),'resident_alloc':36864,'file_buffer_alloc':16384,'image_size':14992,'mem_end':m.mem_end,'module_struct':m.layout['module_size'],'trainer_file_bytes':len(trainer),'trainer_decoded_bytes':len(data),'trainer_xbmc_allocation':16384,'peak_allocations_with_xbmc':36864+16384+16384,'resident_with_xbmc':36864+16384,'bootstrap_symbols':symbols,'trainer_dynamic_relocations':False,'native_payload_path':NATIVE_PATH,'packaging_sources':{p.relative_to(REPO).as_posix():sha(p.read_bytes()) for p in PACKAGING_SOURCES()},'trainerfmt_sha256':sha((ROOT/'trainerfmt.py').read_bytes())}
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n')
    check(out)
    files = [PAIR+'/'+n for n in NAMES]+['README.md','COPYING.GPL-3','NOTICES.txt','manifest.json']
    for name in ('README.md','NOTICES.txt'): shutil.copyfile(ROOT/'release'/name,out/name)
    shutil.copyfile(REPO/'LICENSE',out/'COPYING.GPL-3')
    with zipfile.ZipFile(out/ZIP_NAME,'w',compression=zipfile.ZIP_STORED) as z:
        for name in sorted(files):
            zi = zipfile.ZipInfo(name, (2026,1,1,0,0,0)); zi.external_attr = 0o100644 << 16
            z.writestr(zi, (out/name).read_bytes())
    (out/'SHA256SUMS').write_text(''.join(sha((out/n).read_bytes())+'  '+n+'\n' for n in sorted(files+[ZIP_NAME])))
    print('PASS OG-AmpJack '+VERSION+'; pinned payload; cdecl(0); default OFF; resident=36864 file=16384; trainer relocations=0')
    print(PAIR+'/'+NAMES[0]+'; '+PAIR+'/'+NAMES[1]+'; '+ZIP_NAME+'; manifest.json; SHA256SUMS')
    return out

if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out',type=Path,default=REPO/'build')
    build(ap.parse_args().out)
