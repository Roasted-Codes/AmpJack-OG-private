#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Actual packaged i386 execution. ALL kernel/file surfaces are SYNTHETIC.
No USB, guest or native console behaviour is exercised here.
Pattern adapted from LAN_Stats/tests/test_stage2_loader_model.py; no builds there.
"""
import argparse, json, struct, sys, unittest
from pathlib import Path
sys.dont_write_bytecode=True
import build as B
import os, tempfile
import host_helpers
B.W32 = host_helpers
import unicorn as U
from unicorn import x86_const as R
OUT=Path(os.environ.get('AMPJACK_TEST_OUT', B.REPO/'build'))
T=0x800000; STACK=0xa00000; DONE=0xa80000; K=0x90000000; F=0xc00000
EXTRA_IMPORTS=[]  # Only the seven baseline imports, no logging imports.
REGS=[R.UC_X86_REG_EAX,R.UC_X86_REG_ECX,R.UC_X86_REG_EDX,R.UC_X86_REG_EBX,R.UC_X86_REG_EBP,R.UC_X86_REG_ESI,R.UC_X86_REG_EDI]
def u32(b):return struct.unpack('<I',b)[0]
def pk(v):return struct.pack('<I',v&0xffffffff)
class Machine:
 def __init__(self,base=0x1000000,case='ok',data=None,payload=None):
  self.mod,self.pins,self.j,_=B.inputs(Path(os.environ['AMPJACK_TEST_XBE']));self.base=base;self.case=case
  self.data,self.man=B.check(OUT) if data is None else (data,json.loads((OUT/'manifest.json').read_text()))
  self.file=(OUT/B.PAIR/B.NAMES[1]).read_bytes() if payload is None else payload
  self.m=U.Uc(U.UC_ARCH_X86,U.UC_MODE_32);m=self.m
  for start,size in [(0x10000,0x600000),(T,0x10000),(STACK-0x10000,0x90000),(F,0x10000),(base,0x10000),(K,0x1000)]:m.mem_map(start,size)
  m.mem_write(F,b'\xcc'*0x10000);m.mem_write(base,b'\xcc'*0x10000)
  d=bytearray(self.data)
  if case!='default_off':d[B.TF.u32(d,10)]=0 if case=='disabled' else 1

  if case=='bad_option':struct.pack_into('<I',d,10,0xfffffffe)
  m.mem_write(T,bytes(d))
  header=bytearray(self.pins.header)
  for off,val in [(0x128,0x2da9de),(0x158,0x41b600)]:struct.pack_into('<I',header,off,val)
  if case=='disk_header':header=bytearray(self.pins.header)
  if case=='wrong_tu':header[0x114]^=1
  if case=='bad_header':header[0x140]^=1
  if case=='bad_entry':struct.pack_into('<I',header,0x128,0x12e150)
  m.mem_write(0x10000,bytes(header))
  cert=u32(self.pins.raw[0x118:0x11c]);m.mem_write(cert+8,pk(0x12345678 if case=='wrong_title' else 0x4d530064))
  for n,s in self.j['sites'].items():m.mem_write(s['va'],bytes.fromhex(s['orig']))
  for n,b in self.pins.methods.items():m.mem_write(B.W32.REQUIRED_BINDINGS[n],b)
  m.mem_write(0x4127b4,self.pins.read(0x4127b4,0x28))
  if case=='wrong_orig':m.mem_write(0x413cbf,b'\x90')
  if case=='already_installed':m.mem_write(0x41517d,b'\xe9\x12\x34\x56\x78')
  if case=='wrong_method':m.mem_write(0x416992,b'\x90')
  # Kernel stubs have real stdcall returns. Effects only are synthetic.
  self.calls=[];self.allocs={};self.peak=0;self.opened=False;self.entered=0;self.entry_flags=[];self.zero_seen=False;self.preimage=False;self.pending=None;self.injected=0;self.stopped=False;self.minsp=STACK-4
  self.kernels={}
  for i,(slot,name,nargs) in enumerate([(0x41b654,'open',6),(0x41b6ac,'read',8),(0x41b640,'alloc',5),(0x41b60c,'free',1),(0x41b624,'close',1),(0x41b700,'raise',0),(0x41b6fc,'lower',0)]):
   addr=K+16*i;self.kernels[addr]=(name,nargs)
   m.mem_write(slot,pk(addr));m.mem_write(addr,b'\xc2'+struct.pack('<H',nargs*4) if nargs else b'\xc3')
  for i,(slot,ordinal) in enumerate(EXTRA_IMPORTS):
   if slot==0x41b624:continue  # Shared NtClose already has the production stub.
   addr=K+0x100+16*i
   m.mem_write(slot,pk(addr))
   if slot==0x41b774:m.mem_write(addr,pk(0x12345678))
   else:
    self.kernels[addr]=('unexpected_log_surface_'+str(ordinal),0)
    m.mem_write(addr,b'\xc3')
  if case.startswith(('extra_missing_','extra_unresolved_')):
   i=int(case.rsplit('_',1)[1]);slot,ordinal=EXTRA_IMPORTS[i]
   m.mem_write(slot,pk(0 if case.startswith('extra_missing_') else 0x80000000|ordinal))
  if case=='missing_slot':m.mem_write(0x41b700,pk(0))
  if case=='unresolved_slot':m.mem_write(0x41b6fc,pk(0x800000a1))
  if case=='corrupt':self.file=self.file[:100]+bytes([self.file[100]^1])+self.file[101:]
  if case=='oversize':self.file+=b'\0'
  if case=='truncated':self.file=self.file[:-1]
  if case=='bad_reloc':self.file=self.file[:-4]+pk(0xfffffffe)
  self.stock=bytes(m.mem_read(0x10000,0x600000))
  self.trainer_before=bytes(m.mem_read(T,0x10000))
  m.hook_add(U.UC_HOOK_CODE,self.code)
  m.hook_add(U.UC_HOOK_MEM_WRITE,self.write)
  self.saved={r:0x12340100+i*0x101 for i,r in enumerate(REGS)};self.saved[R.UC_X86_REG_EBP]=T
  for r,v in self.saved.items():m.reg_write(r,v)
  m.reg_write(R.UC_X86_REG_ESP,STACK-4);m.reg_write(R.UC_X86_REG_EFLAGS,0x646)
  m.mem_write(STACK-4,pk(DONE))
 def rd(self,p,n):return bytes(self.m.mem_read(p,n))
 def word(self,p):return u32(self.rd(p,4))
 def write(self,m,access,addr,size,value,user):
  if addr==self.base+self.mod.module_off and size==4 and value==self.j['host']['submit_request'] and not self.zero_seen:
   assert self.rd(self.base+struct.unpack_from('<I',B.package(self.mod),12)[0],self.man['resident_alloc']-self.man['image_size'])==bytes(self.man['resident_alloc']-self.man['image_size']),'BSS not zero before host fill'
   self.zero_seen=True
  # Force an actual production-installer readback failure on CURRENT site.
  va=0x413a12
  if self.case in ('partial','permanent') and addr==va+4:
   orig=bytes.fromhex(self.j['sites']['XInputOpen']['orig'])[4]
   if (self.case=='permanent' or not self.injected) and value!=orig:
    self.pending=(va+2,1);self.injected+=1
   elif self.case=='permanent' and self.injected:
    self.pending=(va+2,1)
 def code(self,m,addr,size,user):
  sp=m.reg_read(R.UC_X86_REG_ESP);self.minsp=min(self.minsp,sp)
  if self.pending:
   p,x=self.pending;self.pending=None;m.mem_write(p,bytes([self.rd(p,1)[0]^x]))
  if addr==self.base+self.mod.entry_off:
   self.entered+=1
   assert self.zero_seen
   self.entry_flags.append(self.word(sp+4))
   assert self.entry_flags[-1]==0,'actual cdecl entry must receive null argument'
   expected,_=self.mod.image(self.base,self.j['host'])
   assert self.rd(self.base,len(expected))==expected,'full relocated image/host/BSS differs from independent W32 image oracle'
   self.preimage=True
  if self.rd(addr,1)==b'\xf4':self.stopped=True;m.emu_stop();return
  if addr not in self.kernels:return
  name,n=self.kernels[addr];a=struct.unpack('<8I',self.rd(sp+4,32));self.calls.append(name);rc=0
  if name=='open':
   assert a[1:2]==(0x80100000,) and a[4:6]==(1,0x60)
   ansi=self.word(a[2]+4);path=self.rd(self.word(ansi+4),struct.unpack('<H',self.rd(ansi,2))[0])
   assert path==b'\\Device\\Harddisk0\\Partition1\\Trainers\\'+B.NAMES[1].encode(),path
   if self.case=='missing':rc=0xc0000034
   else:m.mem_write(a[0],pk(0x1234));self.opened=True
  elif name=='read':
   assert self.opened and a[0]==0x1234
   pos=struct.unpack('<Q',self.rd(a[7],8))[0] if a[7] else 0
   chunk=self.file[pos:pos+a[6]]
   if self.case=='io_fail':chunk=b'';rc=0xc0000001
   else:rc=0 if chunk else 0xc0000011
   if chunk:m.mem_write(a[5],chunk)
   m.mem_write(a[4],pk(rc)+pk(len(chunk)))
  elif name=='alloc':
   assert a[1:5]==(0,0xffffffff,0,4)
   nth=self.calls.count('alloc')
   if self.case==f'alloc{nth}':rc=0
   else:
    rc=F if nth==1 else self.base
    assert a[0]==(self.man['file_buffer_alloc'] if nth==1 else self.man['resident_alloc'])
    self.allocs[rc]=a[0];self.peak=max(self.peak,sum(self.allocs.values()))
  elif name=='free':
   assert a[0] in self.allocs,'double/unowned free'
   # No native hooks may reach any memory about to be freed.
   for s in self.j['sites'].values():
    if self.rd(s['va'],1)==b'\xe9':
     target=(s['va']+5+self.word(s['va']+1))&0xffffffff
     assert not a[0]<=target<a[0]+self.allocs[a[0]],'dangling hook on free'
   del self.allocs[a[0]]
  elif name=='close':assert self.opened;self.opened=False
  else:raise AssertionError('module unexpectedly executed a kernel/USB surface at entry')
  m.reg_write(R.UC_X86_REG_EAX,rc)
 def run(self):
  self.m.emu_start(T+B.TF.parse((OUT/B.PAIR/B.NAMES[0]).read_bytes(),True)[1]['entry_off'],DONE,count=8_000_000)
  if not self.stopped:
   assert self.m.reg_read(R.UC_X86_REG_EIP)==DONE,'instruction cap'
   assert self.m.reg_read(R.UC_X86_REG_ESP)==STACK,'unbalanced trainer/module call'
   assert self.m.reg_read(R.UC_X86_REG_EFLAGS)&0x646==0x646,'flags not preserved'
   for r,v in self.saved.items():assert self.m.reg_read(r)==v,'register clobber'
  assert not self.opened,'file handle leak'
  assert self.rd(T,0x10000)==self.trainer_before,'persistent trainer mutation'
  assert self.rd(self.base+self.man['resident_alloc'],16)==b'\xcc'*16,'resident overrun'
  return self
 def reject_clean(self):
  assert self.rd(0x10000,0x600000)==self.stock,'rejection modified title'
  assert not self.allocs,'rejection allocation leak'
  assert not self.stopped,'unexpected fail-stop'

class Tests(unittest.TestCase):
 def test_01_red_unadapted(self):
  # Execute the EXACT pinned module entry at its correct relocated base, but pass H2S2
  # host as argument without injecting real module.host (the legacy recipe).
  x=Machine();m=x.m;img,_=x.mod.image(x.base,{n:0 for n,_ in x.mod.layout['host_fields']})
  # Independent CPU run without observers, no success simulation.
  y=U.Uc(U.UC_ARCH_X86,U.UC_MODE_32)
  for a,n in [(0x10000,0x600000),(T,0x10000),(x.base,0x10000),(STACK-0x10000,0x90000)]:y.mem_map(a,n)
  y.mem_write(T,struct.pack('<8I',0x48533248,1,T,x.base,x.mod.mem_end,0,0,0))
  y.mem_write(0x10000,x.stock);y.mem_write(x.base,img);y.mem_write(STACK-8,pk(DONE)+pk(T));y.reg_write(R.UC_X86_REG_ESP,STACK-8)
  y.emu_start(x.base,DONE,count=100000)
  self.assertEqual(y.reg_read(R.UC_X86_REG_EIP),DONE)
  self.assertEqual(y.reg_read(R.UC_X86_REG_ESP),STACK-4) # stdcall would yield STACK
  self.assertEqual(u32(y.mem_read(x.base+x.mod.module_off+x.mod.layout['status_fields']['install_failed'],4)),1)
  self.assertEqual(u32(y.mem_read(x.base+x.mod.module_off+x.mod.layout['status_fields']['installed_hooks'],4)),0)
  print('RED reproduced: unadapted cdecl leaves argument, ignores H2S2 host, install_failed=1 hooks=0')
 def test_02_green_two_bases(self):
  for base in (0x1000000,0x83000000):
   x=Machine(base).run();self.assertEqual(x.entered,1);self.assertTrue(x.preimage)
   self.assertEqual(x.entry_flags,[0])
   self.assertEqual(x.allocs,{base:36864});self.assertEqual(x.peak,36864+16384)
   for s in x.j['sites'].values():
    expect=B.W32.e9(s['va'],base+s['target']-x.j['base'])+bytes.fromhex(s['orig'])[5:]
    self.assertEqual(x.rd(s['va'],len(expect)),expect)
   self.assertEqual(x.word(base+x.mod.module_off+x.mod.layout['status_fields']['installed_hooks']),191)
   self.assertEqual(x.word(base+x.mod.module_off+x.mod.layout['status_fields']['install_failed']),0)
   # No title writes except the exact seven 5-byte spans.
   after=bytearray(x.rd(0x10000,0x600000))
   for s in x.j['sites'].values():after[s['va']-0x10000:s['va']-0x10000+5]=x.stock[s['va']-0x10000:s['va']-0x10000+5]
   self.assertEqual(bytes(after),x.stock)
   print(f'GREEN base={base:#x} exact relocated image, host, 7 targets, hooks=BF failed=0; peak native={x.peak} resident={sum(x.allocs.values())} stack_high_water={STACK-4-x.minsp}')
 def test_03_negatives(self):
  for case in ['default_off','disabled','bad_option','wrong_title','wrong_tu','bad_header','bad_entry','wrong_orig','already_installed','wrong_method','missing_slot','unresolved_slot','missing','corrupt','oversize','truncated','bad_reloc','alloc1','alloc2','io_fail']:
   with self.subTest(case=case):
    x=Machine(case=case).run();x.reject_clean();self.assertEqual(x.entered,0)
    if case in ['disabled','wrong_title','wrong_tu','wrong_orig','already_installed','missing_slot']:self.assertEqual(x.calls,[])
   print('PASS rejected cleanly:',case)
 def test_04_partial_write(self):
  x=Machine(case='partial').run();x.reject_clean();self.assertEqual(x.entered,1);self.assertEqual(x.injected,1)
  print('PASS actual installer current-site partial write: adapter restored and verified all seven before free/stock return')
 def test_05_permanent_failure(self):
  x=Machine(case='permanent').run();self.assertTrue(x.stopped);self.assertEqual(x.allocs,{x.base:36864})
  print('PASS permanent restoration failure: native fail-stop, reachable allocation retained, no stock return')
 def test_06_disk_and_relaunch(self):
  Machine(case='disk_header').run()
  # Reuse persisted trainer bytes, not a stale module pointer. Retail first is
  # inert; decoded TU next installs freshly; unrelated title next is inert.
  a=Machine(case='wrong_tu').run();a.reject_clean()
  b=Machine(data=a.rd(T,len(a.data))).run();self.assertEqual(b.entered,1)
  c=Machine(case='wrong_title',data=b.rd(T,len(b.data))).run();c.reject_clean()
 def test_07_host_rejections(self):
  m,_,_,_=B.inputs(Path(os.environ['AMPJACK_TEST_XBE']));p=B.package(m)
  for bad in [p[:-1],p+b'\0',p[:20],p[:64]+b'\0'+p[65:],p[:-4]+pk(0xffffffff)]:
   with self.assertRaises(ValueError):B.check_payload(bad,m)

if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,default=OUT);a,rest=ap.parse_known_args();OUT=a.out.resolve()
 unittest.main(argv=[sys.argv[0]]+rest,verbosity=2)
