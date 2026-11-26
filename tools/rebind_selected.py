#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""One-time import/audit of the pinned inputs from an original module build tree.
Normal packaging never needs this tool or that tree.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
INPUTS = ROOT/'inputs'
TRAINER_SRC = REPO/'src/trainer'
ELF = '5850fc63b387eca58f1dcccae3a390341b66f999bd04d75ee12ddb18135d362b'
PAYLOAD = '5e63fb1afb9c26d15af8165471e2a982171db1f1e9a2fc6c4d6114bd148ec39c'
TRAINER = '977dee0576b8dd5400dc3433afdb997d368ef60ac9ed7fef82c5bf21c40468d2'
TRAINER_NAMES = ('loader.c','bootstrap.S','bootstrap.ld','sha256.inc')

def sha(b):
    return hashlib.sha256(b).hexdigest()

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--original', type=Path, required=True)
    ap.add_argument('--import-inputs', action='store_true')
    a = ap.parse_args()
    old = a.original
    payload_name = 'AmpJack65R-u803-5850fc63.bin'
    trainer_name = 'AmpJack65R-u803-5850fc63.xbtf'
    assert sha((old/'artifact/pic.elf').read_bytes()) == ELF
    assert sha((old/'release/candidate'/payload_name).read_bytes()) == PAYLOAD
    assert sha((old/'release/candidate'/trainer_name).read_bytes()) == TRAINER

    sources = {}
    for p in sorted((old/'src').rglob('*')):
        if not p.is_file() or 'out' in p.relative_to(old/'src').parts:
            continue
        rel = p.relative_to(old).as_posix()
        assert p.read_bytes() == (REPO/rel).read_bytes(), rel
        sources[rel] = sha(p.read_bytes())
    tracked = set(subprocess.check_output(['git','ls-files','src'],cwd=REPO,text=True).splitlines())
    tracked -= {'src/trainer/'+n for n in TRAINER_NAMES}
    assert tracked == set(sources), 'Git source coverage mismatch'
    mapping = {'module.elf':'artifact/pic.elf','module.bin':'release/candidate/'+payload_name,'layout.json':'artifact/layout.json','pins.h':'release/pins.h'}
    if a.import_inputs:
        for name in TRAINER_NAMES:
            shutil.copyfile(old/name, TRAINER_SRC/name)
        for name, src in mapping.items():
            shutil.copyfile(old/src, INPUTS/name)
        print('Imported pinned inputs; trainer source unchanged.')
    for name, src in mapping.items():
        assert (INPUTS/name).read_bytes() == (old/src).read_bytes(), name
    for name in TRAINER_NAMES:
        assert (TRAINER_SRC/name).read_bytes() == (old/name).read_bytes(), name
    payload = (old/'release/candidate'/payload_name).read_bytes()
    assert b'AmpJack' not in payload and b'Trainers' not in payload and b'Harddisk0' not in payload, 'unexpected embedded payload path'
    provenance = {'version':'0.1.0','variant':'rumble-capable controller module','source_root':'../..',
        'elf_sha256':ELF,'payload_sha256':PAYLOAD,'old_trainer_sha256':TRAINER,'controller_sources':sources,
        'trainer_sources':{'src/trainer/'+n:sha((TRAINER_SRC/n).read_bytes()) for n in TRAINER_NAMES},
        'source_coverage':{'controller_files':len(sources),'trainer_files':len(TRAINER_NAMES),'exact_match':True,'excluded_directories':['src/**/out']},
        'pinned_inputs':{n:sha((INPUTS/n).read_bytes()) for n in mapping},
        'trainer_change':'No source changes; generated pins.h payload filename and XBTF display title renamed only',
        'payload_contains_own_path':False,'console_tested':'input, wake, rumble, all buttons'}
    (INPUTS/'provenance.json').write_text(json.dumps(provenance,indent=2)+'\n')
    print('PASS source coverage:',len(sources),'files; unchanged trainer sources; payload has no own path')

if __name__ == '__main__':
    main()
