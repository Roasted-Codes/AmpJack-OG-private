#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""One-time input import/audit from an explicitly supplied original W63 tree.
Normal portable packaging never needs this tool or the original workspace.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parent
ELF = '3ddc05b8c0c01a388ad9ab156660c8018a8a3d0fe4cc676af7548a5405ec7fab'
PAYLOAD = '8bf54869e1635fbcb8313226da7abd243c0b4fc4729b1b664f2828e030380448'
TRAINER = '3685f5680425fb72ec48acfd6c347e0f5d76c320352ee1d02d1ff76e5b6ed23d'
OLD_FLAGS = 'flags=(op+1<sz && t[op+1]==1)?1u:0u;   /* W63: XBTF option [1] */'
NEW_FLAGS = 'flags=0;   /* Preserve owner-selected live logging OFF; no second option. */'

def sha(b):
    return hashlib.sha256(b).hexdigest()

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--original', type=Path, required=True)
    ap.add_argument('--selection', type=Path, required=True)
    ap.add_argument('--import-inputs', action='store_true')
    a = ap.parse_args()
    old = a.original
    chosen = a.selection
    payload_name = 'AmpJack63-u803-3ddc05b8.bin'
    trainer_name = 'AmpJack63-u803-3ddc05b8.xbtf'
    assert sha((old/'artifact/pic.elf').read_bytes()) == ELF
    assert sha((old/'release/candidate'/payload_name).read_bytes()) == PAYLOAD
    assert sha((old/'release/candidate'/trainer_name).read_bytes()) == TRAINER
    assert (chosen/payload_name).read_bytes() == (old/'release/candidate'/payload_name).read_bytes()
    assert (chosen/trainer_name).read_bytes() == (old/'release/candidate'/trainer_name).read_bytes()
    sources = {}
    for p in sorted((old/'src').rglob('*')):
        if not p.is_file() or 'out' in p.relative_to(old/'src').parts:
            continue
        rel = p.relative_to(old).as_posix()
        assert p.read_bytes() == (ROOT/'../work/63-wake-rumble'/rel).read_bytes(), rel
        sources[rel] = sha(p.read_bytes())
    exported = {p.relative_to(ROOT/'../work/63-wake-rumble').as_posix() for p in (ROOT/'../work/63-wake-rumble/src').rglob('*') if p.is_file() and 'out' not in p.relative_to(ROOT/'../work/63-wake-rumble/src').parts}
    assert exported == set(sources), 'source coverage mismatch'
    wrapper_names = ('loader.c','bootstrap.S','bootstrap.ld','sha256.inc')
    mapping = {'module.elf':'artifact/pic.elf','module.bin':'release/candidate/'+payload_name,'layout.json':'artifact/layout.json','pins.h':'release/pins.h'}
    if a.import_inputs:
        for name in wrapper_names:
            shutil.copyfile(old/name, ROOT/name)
        for name, src in mapping.items():
            shutil.copyfile(old/src, ROOT/'inputs'/name)
        print('Imported exact W63 inputs; apply the single flags-zero wrapper patch, then rerun without --import-inputs.')
        return
    for name, src in mapping.items():
        assert (ROOT/'inputs'/name).read_bytes() == (old/src).read_bytes(), name
    expected = (old/'loader.c').read_text()
    assert expected.count(OLD_FLAGS) == 1
    assert (ROOT/'loader.c').read_text() == expected.replace(OLD_FLAGS, NEW_FLAGS), 'only permitted wrapper change is flags zero'
    for name in wrapper_names[1:]:
        assert (ROOT/name).read_bytes() == (old/name).read_bytes(), name
    selection = json.loads((chosen/'SELECTION.json').read_text())
    evidence = json.loads((chosen/'LIVE-TRAINER-IDENTITY.json').read_text())
    live = next(c for c in evidence['candidates'] if c['label'] == 'W63 combined')
    assert live['text_exact'] and live['same_base'] and selection['log_state']['raw_hex'] == '00'*28
    provenance = {'version':'0.1.0-preview.1','variant':'W63 combined; owner-selected live baseline; logging OFF','source_root':'../work/63-wake-rumble','elf_sha256':ELF,'payload_sha256':PAYLOAD,'old_trainer_sha256':TRAINER,'controller_sources':sources,'pinned_inputs':{n:sha((ROOT/'inputs'/n).read_bytes()) for n in mapping},'wrapper_sources':{n:sha((ROOT/n).read_bytes()) for n in wrapper_names},'original_wrapper_sources':{n:sha((old/n).read_bytes()) for n in wrapper_names},'wrapper_change':{'old':OLD_FLAGS,'new':NEW_FLAGS},'selected_live_evidence':{'selection_sha256':sha((chosen/'SELECTION.json').read_bytes()),'identity_sha256':sha((chosen/'LIVE-TRAINER-IDENTITY.json').read_bytes()),'base':selection['base'],'code_bytes':live['text_length'],'text_sha256':live['live_text_sha256'],'log_state_hex':selection['log_state']['raw_hex'],'log_state_offset':'0xa368','evidence_origin':'work/68-owner-selected-baseline; parent read-only XBDM evidence; not reproduced by package tests'},'hardware_status':'Owner reports input and rumble working after replug on selected original; branded wrapper UNTESTED; prior black-screen condition unresolved'}
    (ROOT/'inputs/provenance.json').write_text(json.dumps(provenance,indent=2)+'\n')
    print('PASS exact W63 source coverage:',len(sources),'files; only flags-zero wrapper change; original pair and live evidence bound')

if __name__ == '__main__':
    main()
