"""Offline evidence expansion; all output is lane51-owned."""
import hashlib,json,struct,subprocess
from pathlib import Path
O=Path(__file__).resolve().parent;W=O.parent;R=W/'45-x11-runtime-capture';L=R/'post-entry-49/live'
def save(n,v):(O/n).write_text(json.dumps(v,indent=2,sort_keys=True)+'\n')
schema=json.loads((L/'register-schema.json').read_text());final=json.loads((L/'final-context.json').read_text());packet=bytes.fromhex(final['raw_g']);assert len(packet)*8==sum(schema['widths']);assert schema['names']=='eax ecx edx ebx esp ebp esi edi eip eflags cs ss ds es fs gs'.split();assert schema['widths'][:16]==[32]*16
regs=dict(zip(schema['names'],struct.unpack_from('<16I',packet)));assert regs==final['regs']
rows=[json.loads(x) for x in (L/'ordered-trace.jsonl').read_text().splitlines()];s=rows[1]['raw_snapshot'];g=s['regs'];stack=bytes.fromhex(final['stack']);esp=g['esp'];ebp=g['ebp']
assert ebp-esp==20
frames={hex(esp+i):hex(struct.unpack_from('<I',stack,i)[0]) for i in range(0,40,4)}
assert struct.unpack_from('<I',stack,24)[0]==0x412d9b
assert struct.unpack_from('<I',stack,28)[0]==29
assert struct.unpack_from('<I',stack,32)[0]==2
assert struct.unpack_from('<I',stack,0)[0]==29*32==g['eax']
xb=Path('/home/roasted/Desktop/Xbox/H2-Decomp/tu15-decomp/targets/halo2-tu15-u803/default.xbe').read_bytes()
header=bytearray(xb[:0x178])
for off,key in ((0x128,0xa8fc57ab),(0x158,0x5b6d40b6)):struct.pack_into('<I',header,off,struct.unpack_from('<I',header,off)[0]^key)
entry=json.loads((L/'entry-verified.json').read_text());assert header.hex()==entry['header_hex']
table=struct.unpack_from('<I',xb,0x120)[0]-struct.unpack_from('<I',xb,0x104)[0]
def mapped(a,n):
 for i in range(struct.unpack_from('<I',xb,0x11c)[0]):
  va,vs,off,rs=struct.unpack_from('<4I',xb,table+i*56+4)
  if va<=a and a+n<=va+rs:return xb[off+a-va:off+a-va+n]
 raise AssertionError('unmapped')
call=mapped(0x1273f4,5);assert call[0]==0xe8 and 0x1273f9+struct.unpack_from('<i',call,1)[0]==0x4139a0
save('independent-entry-edge.json',dict(hint_only_source='W26 verify.py:120; not executed',callsite='0x1273f4',exact_tu_bytes=call.hex(),target='0x4139a0',thunk_bytes=mapped(0x4139a0,5).hex(),thunk_target='0x412d37',qualification='exact TU call corroborates independent thunk entry; full caller function CFG not recovered'))
meta=json.loads((O/'tu-code-section.json').read_text());section=(O/'tu-code-section.bin').read_bytes()
def exact(va,n):return section[va-meta['va']:va-meta['va']+n].hex()
commands=[]
for start,end in ((0x412d37,0x412db0),(0x4131bb,0x41325e),(0x4139a0,0x4139a5),(0x415076,0x4150d0),(0x416375,0x416439),(0x41668e,0x41673d),(0x417078,0x4170cc),(0x412a20,0x412a61)):
 cmd=['objdump','-D','-w','-b','binary','-m','i386',f'--adjust-vma={meta["va"]}',f'--start-address={start}',f'--stop-address={end}',str(O/'tu-code-section.bin')];p=subprocess.run(cmd,capture_output=True,text=True);assert p.returncode==0;(O/f'anchored-{start:08x}.txt').write_text(p.stdout);commands.append(dict(command=cmd,exit=p.returncode,qualification='candidate aggregate entry, not independently call-anchored' if start==0x412a20 else 'entry/edge anchored in exact TU or existing authenticated production pins'))
save('analysis-commands.json',commands)
save('mechanical-proof.json',dict(register_schema_matches=True,raw_g_length=len(packet),registers={k:hex(v) for k,v in regs.items()},snapshot_ranges=[dict(address=hex(m['address']),length=len(bytes.fromhex(m['hex']))) for m in s['memory']],final_code_range=dict(address=hex(g['eip']-16),length=len(bytes.fromhex(final['code']))),final_stack_range=dict(address=hex(esp),length=len(stack)),frame_words=frames,writer=dict(va='0x4131e1',bytes=exact(0x4131e1,6),width=4,ea=hex(g['esi']+0x80),value=hex(g['ebx']),next_pc=hex(g['eip']),reason=rows[1]['stop_reason']),caller=dict(callsite='0x412d96',bytes=exact(0x412d96,5),target='0x4131bb',fallthrough='0x412d9b',saved_return_address=hex(ebp+4),return_word='0x412d9b',esp_top_role='allocation-size argument 29 shifted left 5, NOT return',argument1=29,argument2=2,upper_caller='not established; saved biased caller EBP is available but its entry/return path is not captured'),semantics='Explicit object-relative zero store inside setup-shaped routine; current-device role is inferred from separately authenticated producer/consumer instructions, not zero state alone',safe_continuation_proved=False))
inventory=[]
for va,n,kind,coverage in ((0x4131e1,6,'object_relative_zero_store','Observed exact EA from captured ESI; dominates neither future scheduling nor complete boot history'),(0x416412,6,'absolute_current_from_esi','Existing stock enqueue CFG; ESI is returned record pointer'),(0x4166b5,6,'absolute_current_zero','Existing EnumNext no-pending branch'),(0x4166c3,5,'absolute_current_from_eax','Existing EnumNext promotes pending pointer'),(0x4150ba,4,'aggregate_zero_plus_word','Generic constructor zeroes object+0x64..+0x95 including object+0x80 IF aliased; checked 0x412d4d passes caller stack local, NOT global'),(0x412a35,2,'aggregate_zero_region','Range 0x48d7f8..0x490808 exclusive; DOES NOT cover 0x490930'),(0x412dd5,9,'dynamic_aggregate_zero','Allocated pointer/size path; no proof of alias to static global'),(0x414e4e,7,'partial_width_object_store','Word store object+0x80; no proven alias to global')):
 inventory.append(dict(va=hex(va),bytes=exact(va,n),kind=kind,coverage=coverage))
save('writer-inventory.json',dict(entries=inventory,aggregate_range_end=hex(0x48d7f8+0xc04*4),coverage='Exact local TU section and anchored relevant functions only, not exhaustive whole-title alias analysis. Linear whole-section listing includes data; byte-pattern hits outside anchors are candidates only. Dynamic aggregate, indirect calls, other sections, DMA/module/unseen writers unresolved. No decoder allowlist derived.'))
print(json.dumps(dict(schema=True,frame=True,header=True,writer=True,caller=True,aggregate_end=hex(0x48d7f8+0xc04*4),commands=len(commands))))
