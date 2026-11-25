import hashlib,json,struct
from pathlib import Path
O=Path(__file__).resolve().parent;W=O.parent;R=W/'45-x11-runtime-capture';L=R/'post-entry-49/live';P=W/'50-astra-observer-topology-plan'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
f=json.loads((P/'PARENT-FROZEN-REFERENCE.json').read_text());p=json.loads((P/'PARENT-PINNED-INPUTS.json').read_text())
checks={}
for name,want in {**p['read_only_hashes'],**f['immutable_live_files']}.items():
 path=Path(name);got=sha(path);checks[name]={'expected':want,'actual':got,'ok':got==want}
for name,v in f['source'].items():
 path=Path(v['frozen_path']);got=sha(path);checks[str(path)]={'expected':v['sha256'],'actual':got,'ok':got==v['sha256']}
path=R/'tools/enum_watch.py';got=sha(path);want=f['source'][str(path)]['sha256'];checks[str(path)]={'expected':want,'actual':got,'ok':got==want}
(O/'protected-initial.json').write_text(json.dumps(checks,indent=2)+'\n')
assert all(v['ok'] for v in checks.values()),'protected drift'
rows=[json.loads(l) for l in (L/'ordered-trace.jsonl').read_text().splitlines()];assert [r['seq'] for r in rows]==[1,2,3]
identity=rows[0]['identity'];alloc=json.loads((L/'allocation-receipt.json').read_text());entry=json.loads((L/'entry-verified.json').read_text());install=json.loads((L/'install-verified.json').read_text());final=json.loads((L/'final-context.json').read_text());raw=rows[1]['raw_snapshot']
assert raw['regs']==final['regs'];assert bytes.fromhex(final['stack']).startswith(bytes.fromhex(raw['memory'][1]['hex']))
assert all(identity[k]==entry['identity'][k] for k in entry['identity'])
assert identity['base']==alloc['base']==install['base'] and identity['module']==install['module']
assert alloc['allocation_id']==f"W45-{identity['boot_id']}-{identity['pid']}-{identity['start_ticks']}"
(O/'original-ordered-trace.jsonl').write_bytes((L/'ordered-trace.jsonl').read_bytes())
(O/'original-seq2.json').write_text(json.dumps(rows[1],indent=2)+'\n')
xb=Path(next(n for n in p['read_only_hashes'] if n.endswith('default.xbe'))).read_bytes();u=lambda off:struct.unpack_from('<I',xb,off)[0];base=u(0x104);table=u(0x120)-base
sections=[struct.unpack_from('<4I',xb,table+i*56+4) for i in range(u(0x11c))]
(O/'xbe-sections.json').write_text(json.dumps(sections,indent=2)+'\n')
address=raw['regs']['eip']-16
for va,vs,off,rs in sections:
 if va<=0x4131e1<va+rs:
  (O/'tu-code-section.bin').write_bytes(xb[off:off+rs]);(O/'tu-code-section.json').write_text(json.dumps(dict(va=va,virtual_size=vs,raw_offset=off,raw_size=rs)))
  address=raw['regs']['eip']-16;code=bytes.fromhex(final['code']);assert code==xb[off+address-va:off+address-va+len(code)]
(O/'pairing.json').write_text(json.dumps(dict(identity=identity,rows=3,final_regs_equal=True,final_stack_prefix_equal=True,final_code_address=address,final_code_matches_tu=True),indent=2)+'\n')
print(json.dumps(dict(all_hashes_passed=True,count=len(checks),pairing=True,sections=sections)))
