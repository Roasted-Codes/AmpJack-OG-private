#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Read-only input/owner-output audit; writes only this work directory evidence."""
import json, struct, sys, zipfile
from pathlib import Path
sys.dont_write_bytecode=True
import build as B
out=B.ROOT/'release-build';m,p,j,fields=B.inputs();data,manifest=B.check(out)
blob=(out/'candidate'/B.NAMES[1]).read_bytes();maps=[]
for s in m.loads:
 got=blob[64+s['va']:64+s['va']+s['fsz']]
 original=m.data[s['off']:s['off']+s['fsz']]
 assert got==original
 maps.append({'elf_file_offset':s['off'],'original_virtual_offset':s['va'],'payload_file_offset':64+s['va'],'runtime_offset_unchanged':s['va'],'file_bytes':s['fsz'],'memory_bytes':s['msz'],'copied_sha256':B.sha(got),'byte_equivalent':True})
assert blob[64:64+13928]==m.data[4096:4096+13928]
with zipfile.ZipFile(out/'AmpJack43-u803-candidate.zip') as z:
 names=z.namelist();assert len(names)==7 and len(set(names))==7
 archive={'members':[{ 'name':i.filename,'bytes':i.file_size} for i in z.infolist()],'allowlist_count':len(names),'sha256':B.sha((out/'AmpJack43-u803-candidate.zip').read_bytes())}
r={'host_only':True,'guest_access_performed':False,'translation':'64-byte disk-only envelope; PT_LOAD virtual offsets and bytes unchanged; 20 original RELATIVE destinations appended as offsets; no code recompilation; BSS not stored','segments':maps,'bss_start':manifest['image_size'],'bss_end':m.mem_end,'bss_bytes':m.mem_end-manifest['image_size'],'header_fields_disk_or_decoded_only':fields,'hook_oracle':[{ 'name':n,'site':s['va'],'target_offset':s['target']-j['base'],'guard_bytes':len(bytes.fromhex(s['orig']))} for n,s in j['sites'].items()],'archive':archive,'measurements':{k:v for k,v in manifest.items() if k in ['image_size','mem_end','resident_alloc','file_buffer_alloc','payload_bytes','trainer_file_bytes','trainer_decoded_bytes','trainer_xbmc_allocation','peak_allocations_with_xbmc','resident_with_xbmc','module_struct','text','relocations']},'cpu_stack_high_water_bytes':1044,'peak_with_xbmc_plus_observed_stack_bytes':manifest['peak_allocations_with_xbmc']+1044}
clean=B.ROOT/'clean-rebuild-check'
r['second_clean_build_byte_identical']={n:(clean/'candidate'/n).read_bytes()==(out/'candidate'/n).read_bytes() for n in B.NAMES}
assert all(r['second_clean_build_byte_identical'].values())
r['clean_native_rejection_cases']=sum(line.startswith('PASS rejected cleanly:') for line in (out/'cpu-tests.log').read_text().splitlines())
(out/'audit.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2))
