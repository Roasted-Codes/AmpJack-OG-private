#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Host-only exact-input pack/build/check. Never accesses an Xbox or network."""
import argparse, hashlib, importlib.util, json, os, shutil, struct, subprocess, sys, zipfile
from pathlib import Path
sys.dont_write_bytecode = True
ROOT=Path(__file__).resolve().parent
REPO=ROOT.parents[3]
LAN=REPO.parent/'LAN_Stats'
ART32=REPO/'ogxbox/work/32-opus-final-integration/artifact'
ART=ROOT/'artifact'
W43=REPO/'ogxbox/work/43-trainer-candidate'
def sha(b):return hashlib.sha256(b).hexdigest()
# W63: identities are the NEW build in ./artifact (src/ build_pic.sh + tools/gen_layout.py).
ELF_SHA=sha((ART/'pic.elf').read_bytes())
LAYOUT_SHA=sha((ART/'layout.json').read_bytes())
NAMES=(f'AmpJack65R-u803-{ELF_SHA[:8]}.xbtf',f'AmpJack65R-u803-{ELF_SHA[:8]}.bin')
# Title addresses, identical to work/43 release-build/pins.h host_values (44-byte host).
HOST_VALUES=[0x4155bf,0x41517d,0x416992,0x0,0x4165c6,0x4127b4,0x4127cc,0x4127d8,0x0,0x41b700,0x41b6fc]
def loadmod(name,path):
 s=importlib.util.spec_from_file_location(name,path)
 assert s is not None and s.loader is not None
 m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
W32=loadmod('w32',ART32/'ogx_title_loader.py')
TF=loadmod('trainerfmt',LAN/'tools/trainerfmt.py')
def inputs():
 for path,digest in json.loads((W43/'PARENT-FROZEN-INPUTS.json').read_text()).items():
  assert sha((REPO/'ogxbox'/path).read_bytes())==digest,f'frozen input changed: {path}'
 e=(ART/'pic.elf').read_bytes();l=(ART/'layout.json').read_bytes()
 assert sha(e)==ELF_SHA and sha(l)==LAYOUT_SHA,'ELF/layout changed'
 m=W32.Module(e,json.loads(l));p=W32.Pins()
 assert json.loads(l)['elf_sha256']==ELF_SHA,'layout not bound to this ELF'
 assert m.entry_off==0 and m.layout['host_size']==44 and len(m.relocs)==len(set(m.relocs))
 # Journal-shaped dict synthesized from the NEW ELF (hook offsets) + XBE pins
 # (original site bytes) + the fixed title host values; no work/33 journal.
 j={'state':'w65_synthesized','elf_sha256':ELF_SHA,'base':0,
    'host':{n:v for (n,_),v in zip(m.layout['host_fields'],HOST_VALUES)},
    'sites':{n:{'va':W32.HOOK_SITES[n][0],'target':m.hook_off[n],'orig':p.sites[n].hex()} for n in W32.HOOK_SITES}}
 assert len(j['host'])==11
 a=json.loads((REPO/'ogxbox/work/31-title-runtime/PARENT-ACCEPTED.json').read_text())
 fields=[]
 for off in (0x128,0x158):
  v=a['header_fields'][hex(off)];fields.append([off,int(v['disk'],16),int(v['decoded'],16)])
 assert fields==[[0x128,0xa8d1fe75,0x2da9de],[0x158,0x5b2cf6b6,0x41b600]]
 for n,s in j['sites'].items():
  assert s['target']-j['base']==m.hook_off[n] and s['va']==W32.HOOK_SITES[n][0]
 return m,p,j,fields

def package(m):
 assert m.sha256==ELF_SHA and m.layout==json.loads((ART/'layout.json').read_text()),'incompatible layout'
 assert len(m.relocs)==len(set(m.relocs)),'extra/duplicate relocation'
 end=max(s['va']+s['fsz'] for s in m.loads)
 image=bytearray(end)
 for s in m.loads:image[s['va']:s['va']+s['fsz']]=m.data[s['off']:s['off']+s['fsz']]
 for r in m.relocs:
  assert r<=end-4 and struct.unpack_from('<I',image,r)[0]<m.mem_end
 # AJ43 v1: file_size,image_size,mem_end,entry,module,reloc_count,header_size,
 # then reserved zeros. ELF virtual offsets preserved; envelope not mapped.
 hdr=struct.pack('<16I',0x33344a41,1,64+end+4*len(m.relocs),end,m.mem_end,m.entry_off,m.module_off,len(m.relocs),64,*([0]*7))
 return hdr+image+b''.join(struct.pack('<I',r) for r in m.relocs)

def check_payload(data,m):
 expected=package(m)
 if len(data)!=len(expected):raise ValueError('payload size/truncation/overflow')
 if data!=expected:raise ValueError('payload metadata, image or relocation mismatch')
 return True

def run(cmd,out):
 r=subprocess.run([str(x) for x in cmd],text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,cwd=ROOT)
 with (out/'commands.log').open('a') as f:f.write('$ '+' '.join(map(str,cmd))+'\n'+r.stdout+f'\nexit={r.returncode}\n')
 if r.returncode:raise RuntimeError(r.stdout)
 return r.stdout

def build(out):
 out=out.resolve();assert out.is_relative_to(ROOT) and out!=ROOT
 out.mkdir(parents=True,exist_ok=True)
 m,p,j,fields=inputs();payload=package(m);check_payload(payload,m)
 img=struct.unpack_from('<I',payload,12)[0]
 host=j['host'];hosts=[host[n] for n,_ in m.layout['host_fields']]
 assert hosts[-2:]==[0x41b700,0x41b6fc]
 slots=[[0x41b640,166],[0x41b60c,171],[0x41b654,202],[0x41b6ac,219],[0x41b624,187],[0x41b700,129],[0x41b6fc,161]]
 # Validate all ordinal assertions against actual pinned XBE before emitting.
 for va,ordinal in slots:assert p._thunk_ordinal(va)==0x80000000|ordinal,(hex(va),ordinal,p._thunk_ordinal(va))
 sites=[]
 for n,(va,orig,dlen,bit) in W32.HOOK_SITES.items():
  sites.append((va,m.hook_off[n],p.sites[n]))
 methods=[(W32.REQUIRED_BINDINGS[n],v) for n,v in p.methods.items()]
 def arr(name,vs,typ='u32'):return f'static const {typ} {name}[]={{'+','.join(hex(x) for x in vs)+'};\n'
 def bytearr(name,b):return arr(name,b,'u8')
 pins='/* Generated from pinned inputs; do not edit. */\n'
 vals={'FILE_SIZE':len(payload),'IMAGE_SIZE':img,'MEM_END':m.mem_end,'ENTRY_OFF':m.entry_off,'MODULE_OFF':m.module_off,'RELOC_COUNT':len(m.relocs),'RESIDENT_ALLOC':W32.align_up(m.mem_end,4096),'FILE_ALLOC':W32.align_up(len(payload),4096),'STATUS_HOOKS':m.layout['status_fields']['installed_hooks'],'STATUS_FAILED':m.layout['status_fields']['install_failed'],'TITLE_END':p.image_hi,'CERT_VA':struct.unpack_from('<I',p.raw,0x118)[0],'METHOD_COUNT':len(methods),'SLOT_COUNT':len(slots)}
 for n,v in vals.items():pins+=f'#define {n} {v}u\n'
 pins+=arr('host_values',hosts)+arr('reloc_offsets',m.relocs)+arr('expected_header',struct.unpack_from('<16I',payload))
 pins+=bytearr('payload_sha',hashlib.sha256(payload).digest())+bytearr('header_sha',hashlib.sha256(p.header).digest())
 pins+='static const u32 header_fields[2][3]={'+','.join('{'+','.join(hex(v) for v in f)+'}' for f in fields)+'};\n'
 pins+='static const u32 slots[][2]={'+','.join('{'+','.join(hex(v) for v in s)+'}' for s in slots)+'};\n'
 pins+='struct site {u32 va,off,len;u8 orig[10];};\nstatic const struct site sites[]={'+','.join('{'+f'{va},{off},{len(b)},'+'{'+','.join(hex(v) for v in b)+'}}' for va,off,b in sites)+'};\n'
 pins+='struct method {u32 va;u8 orig[10];};\nstatic const struct method methods[]={'+','.join('{'+str(va)+',{'+','.join(hex(v) for v in b)+'}}' for va,b in methods)+'};\n'
 pins+='static const char payload_path[]="\\\\Device\\\\Harddisk0\\\\Partition1\\\\Trainers\\\\'+NAMES[1]+'";\n'
 (out/'pins.h').write_text(pins)
 flags=['clang','-target','i386-unknown-none-elf','-march=pentium3','-Os','-ffreestanding','-nostdlib','-fpie','-fvisibility=hidden','-mgeneral-regs-only','-mstack-alignment=4','-fno-stack-protector','-fno-asynchronous-unwind-tables','-fno-unwind-tables','-Wall','-Wextra','-Werror','-I',out,'-I',ROOT]
 run(flags+['-c',ROOT/'loader.c','-o',out/'loader.o'],out)
 run(['clang','-target','i386-unknown-none-elf','-c',ROOT/'bootstrap.S','-o',out/'bootstrap.o'],out)
 run(['ld.lld','-pie','--no-dynamic-linker','-z','text','-z','norelro','--hash-style=sysv','-T',ROOT/'bootstrap.ld',out/'bootstrap.o',out/'loader.o','-o',out/'bootstrap.elf'],out)
 rel=run(['readelf','-S','-l','-r',out/'bootstrap.elf'],out)
 assert 'R_386' not in rel,'bootstrap cannot have dynamic fixups'
 nm=run(['nm','-an',out/'bootstrap.elf'],out)
 syms={x[2]:int(x[0],16) for line in nm.splitlines() if len(x:=line.split())==3}
 run(['objcopy','-O','binary',out/'bootstrap.elf',out/'bootstrap.bin'],out)
 code=(out/'bootstrap.bin').read_bytes()
 assert syms['trainer_entry']==0 and syms['boot_end']==len(code),(syms,len(code))
 candidate=out/'candidate';candidate.mkdir(exist_ok=True)
 (candidate/NAMES[1]).write_bytes(payload)
 trainer=TF.build_data(code,[0x4d530064],'AmpJack65 RUMBLE-ONLY','Not cleared for physical test',['Enable'],[False])
 xbtf=TF.build_xbtf(trainer,creation_key='AMPJ65-R',scroller='')
 (candidate/NAMES[0]).write_bytes(xbtf)
 dec,info=TF.parse(xbtf,True)
 assert dec==trainer and len(dec)<=15193 and info['options'][0]['default']==0
 manifest={'label':'candidate — not cleared for physical test','format':'AJ43 v1 (not H2S2)','elf_sha256':ELF_SHA,'layout_sha256':LAYOUT_SHA,'payload_sha256':sha(payload),'trainer_sha256':sha(xbtf),'image_size':img,'mem_end':m.mem_end,'resident_alloc':vals['RESIDENT_ALLOC'],'file_buffer_alloc':vals['FILE_ALLOC'],'payload_bytes':len(payload),'trainer_file_bytes':len(xbtf),'trainer_decoded_bytes':len(dec),'trainer_xbmc_allocation':16384,'peak_allocations_with_xbmc':16384+vals['RESIDENT_ALLOC']+vals['FILE_ALLOC'],'resident_with_xbmc':16384+vals['RESIDENT_ALLOC'],'module_struct':m.layout['module_size'],'text':m.loads[0]['fsz'],'relocations':len(m.relocs),'bootstrap_symbols':syms,'inputs':{},'sources':{}}
 paths=[ART/'pic.elf',ART/'layout.json',ART32/'ogx_title_loader.py',REPO/'ogxbox/work/31-title-runtime/PARENT-ACCEPTED.json']
 paths +=sorted(p for p in (ROOT/'src').rglob('*') if p.is_file() and '/out/' not in str(p))
 paths +=[REPO/'ogxbox/loader'/n for n in ['REPORT.md','h2s2.h','mkmodule.py']]
 paths +=[LAN/n for n in ['trainer/h2stats.s','trainer/stage2/h2s2.h','trainer/stage2/crt0.c','trainer/stage2/mkmodule.py','trainer/build.sh','references/stage2-platform.md','tools/trainerfmt.py','tools/make_trainer.py']]
 for path in paths:manifest['inputs'][str(path)]=sha(path.read_bytes())
 for name in ['build.py','loader.c','bootstrap.S','bootstrap.ld','sha256.inc','test_candidate.py','release.py','README.txt','NOTICES.txt']:manifest['sources'][name]=sha((ROOT/name).read_bytes())
 (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
 print(json.dumps({k:v for k,v in manifest.items() if k not in ('bootstrap_symbols','inputs','sources')},indent=2))
 return out

def check(out):
 m,p,j,f=inputs();man=json.loads((out/'manifest.json').read_text());c=out/'candidate'
 for name,hashkey in zip(NAMES,['trainer_sha256','payload_sha256']):assert sha((c/name).read_bytes())==man[hashkey],f'stale manifest: {name}'
 for name,digest in man['sources'].items():assert sha((ROOT/name).read_bytes())==digest,f'stale source manifest: {name}'
 for path,digest in man['inputs'].items():assert sha(Path(path).read_bytes())==digest,f'changed frozen input: {path}'
 check_payload((c/NAMES[1]).read_bytes(),m)
 data,info=TF.parse((c/NAMES[0]).read_bytes(),True)
 assert info['creation_key']=='AMPJ65-R' and info['scroller']=='' and len(data)<=15193 and info['options'][0]['default']==0
 print('PASS matched pair, frozen identities, consumer framing, payload byte equivalence, bounds and default OFF')
 return data,man

def main():
 ap=argparse.ArgumentParser();ap.add_argument('cmd',choices=['build','check']);ap.add_argument('--out',type=Path,default=ROOT/'build');a=ap.parse_args()
 if a.cmd=='build':build(a.out)
 else:check(a.out.resolve())
if __name__=='__main__':main()
