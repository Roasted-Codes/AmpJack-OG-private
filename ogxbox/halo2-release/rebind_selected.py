#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""One-time input import/audit from an explicitly supplied original W65R tree.
Normal portable packaging never needs this tool or the original workspace.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parent
ELF = '5850fc63b387eca58f1dcccae3a390341b66f999bd04d75ee12ddb18135d362b'
PAYLOAD = '5e63fb1afb9c26d15af8165471e2a982171db1f1e9a2fc6c4d6114bd148ec39c'
TRAINER = '977dee0576b8dd5400dc3433afdb997d368ef60ac9ed7fef82c5bf21c40468d2'
SOURCE = ROOT/'../work/65-bisect/rumble'

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
        assert p.read_bytes() == (SOURCE/rel).read_bytes(), rel
        sources[rel] = sha(p.read_bytes())
    exported = {p.relative_to(SOURCE).as_posix() for p in (SOURCE/'src').rglob('*') if p.is_file() and 'out' not in p.relative_to(SOURCE/'src').parts}
    assert exported == set(sources), 'source coverage mismatch'
    tracked = set(subprocess.check_output(['git','ls-files','ogxbox/work/65-bisect/rumble/src'],cwd=ROOT.parents[1],text=True).splitlines())
    assert tracked == {'ogxbox/work/65-bisect/rumble/'+s for s in sources}, 'Git source coverage mismatch'
    wrapper_names = ('loader.c','bootstrap.S','bootstrap.ld','sha256.inc')
    mapping = {'module.elf':'artifact/pic.elf','module.bin':'release/candidate/'+payload_name,'layout.json':'artifact/layout.json','pins.h':'release/pins.h'}
    if a.import_inputs:
        for name in wrapper_names:
            shutil.copyfile(old/name, ROOT/name)
        for name, src in mapping.items():
            shutil.copyfile(old/src, ROOT/'inputs'/name)
        print('Imported exact W65R inputs; wrapper source unchanged.')
    for name, src in mapping.items():
        assert (ROOT/'inputs'/name).read_bytes() == (old/src).read_bytes(), name
    expected = (old/'loader.c').read_text()
    assert (ROOT/'loader.c').read_text() == expected, 'W65R loader must be unchanged'
    for name in wrapper_names[1:]:
        assert (ROOT/name).read_bytes() == (old/name).read_bytes(), name
    payload = (old/'release/candidate'/payload_name).read_bytes()
    assert b'AmpJack' not in payload and b'Trainers' not in payload and b'Harddisk0' not in payload, 'unexpected embedded payload path'
    provenance = {'version':'0.1.0-preview.1','variant':'W65 rumble-only (W65R); owner-selected','source_root':'../work/65-bisect/rumble','elf_sha256':ELF,'payload_sha256':PAYLOAD,'old_trainer_sha256':TRAINER,'controller_sources':sources,'source_coverage':{'original_files':len(sources),'tracked_files':len(tracked),'exact_match':True,'excluded_directories':['src/**/out']},'pinned_inputs':{n:sha((ROOT/'inputs'/n).read_bytes()) for n in mapping},'wrapper_sources':{n:sha((ROOT/n).read_bytes()) for n in wrapper_names},'original_wrapper_sources':{n:sha((old/n).read_bytes()) for n in wrapper_names},'wrapper_change':'No source changes; generated pins payload filename and XBTF display title renamed only','payload_contains_own_path':False,'selected_live_evidence':{'origin':'Owner decision supplied in task; Discord 1575345691214086249; not independently queried by package tests','xbmc_path':'E:\\Trainers\\'+trainer_name,'Active':1,'settings':'1','other_ampjack_rows_active':0,'owner_report':'input and rumble working'},'hardware_status':'Renamed wrapper hardware UNTESTED until one console launch; original W65R owner-reported working'}
    (ROOT/'inputs/provenance.json').write_text(json.dumps(provenance,indent=2)+'\n')
    print('PASS exact W65R Git source coverage:',len(sources),'files; unchanged loader/bootstrap/SHA; payload has no own path')

if __name__ == '__main__':
    main()
