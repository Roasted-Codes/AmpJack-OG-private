#!/usr/bin/env python3
"""Make the W63 packaging copies from work/43-trainer-candidate (read-only) with
exact, asserted replacements. Run once from tools/."""
from pathlib import Path
W = Path(__file__).resolve().parents[1]; S = W.parent / '43-trainer-candidate'
def rep(t, old, new, n=1):
    assert t.count(old) == n, (old[:70], t.count(old)); return t.replace(old, new)
for f in ['bootstrap.S', 'bootstrap.ld', 'sha256.inc', 'NOTICES.txt']:
    (W / f).write_bytes((S / f).read_bytes())

# ---------------- build.py
t = (S / 'build.py').read_text()
t = rep(t, "ART=REPO/'ogxbox/work/32-opus-final-integration/artifact'\nELF_SHA='7bbfdafaa91920269876aa54e02efe278b738c0298aeb7bd629b1aaf8a1a08b8'\nLAYOUT_SHA='c1ecc50ad14a86246f516df080b96c50e348cefa5d5f779916c78164443858f6'\nNAMES=('AmpJack43-u803-7bbfdafa.xbtf','AmpJack43-u803-7bbfdafa.bin')\ndef sha(b):return hashlib.sha256(b).hexdigest()",
"ART32=REPO/'ogxbox/work/32-opus-final-integration/artifact'\nART=ROOT/'artifact'\nW43=REPO/'ogxbox/work/43-trainer-candidate'\ndef sha(b):return hashlib.sha256(b).hexdigest()\n# W63: identities are the NEW build in ./artifact (src/ build_pic.sh + tools/gen_layout.py).\nELF_SHA=sha((ART/'pic.elf').read_bytes())\nLAYOUT_SHA=sha((ART/'layout.json').read_bytes())\nNAMES=(f'AmpJack63-u803-{ELF_SHA[:8]}.xbtf',f'AmpJack63-u803-{ELF_SHA[:8]}.bin')\n# Title addresses, identical to work/43 release-build/pins.h host_values (44-byte host).\nHOST_VALUES=[0x4155bf,0x41517d,0x416992,0x0,0x4165c6,0x4127b4,0x4127cc,0x4127d8,0x0,0x41b700,0x41b6fc]")
t = rep(t, "W32=loadmod('w32',ART/'ogx_title_loader.py')", "W32=loadmod('w32',ART32/'ogx_title_loader.py')")
t = rep(t, "(ROOT/'PARENT-FROZEN-INPUTS.json')", "(W43/'PARENT-FROZEN-INPUTS.json')")
t = rep(t, """ assert sha(e)==ELF_SHA and sha(l)==LAYOUT_SHA,'frozen ELF/layout changed'
 m=W32.Module(e,json.loads(l));p=W32.Pins()
 # These pins are the exact ABI, not a similarly named host or H2S2 struct.
 assert m.entry_off==0 and m.module_off==14712 and m.mem_end==35896
 assert len(m.relocs)==20 and m.layout['host_size']==44
 j=json.loads((REPO/'ogxbox/work/33-title-input-repair/module-journal-33.json').read_text())
 assert j['state']=='verified_installed' and j['elf_sha256']==ELF_SHA
""", """ assert sha(e)==ELF_SHA and sha(l)==LAYOUT_SHA,'ELF/layout changed'
 m=W32.Module(e,json.loads(l));p=W32.Pins()
 assert json.loads(l)['elf_sha256']==ELF_SHA,'layout not bound to this ELF'
 assert m.entry_off==0 and m.layout['host_size']==44 and len(m.relocs)==len(set(m.relocs))
 # Journal-shaped dict synthesized from the NEW ELF (hook offsets) + XBE pins
 # (original site bytes) + the fixed title host values; no work/33 journal.
 j={'state':'w63_synthesized','elf_sha256':ELF_SHA,'base':0,
    'host':{n:v for (n,_),v in zip(m.layout['host_fields'],HOST_VALUES)},
    'sites':{n:{'va':W32.HOOK_SITES[n][0],'target':m.hook_off[n],'orig':p.sites[n].hex()} for n in W32.HOOK_SITES}}
 assert len(j['host'])==11
""")
t = rep(t, " assert len(m.relocs)==20 and len(set(m.relocs))==20,'extra/duplicate relocation'",
           " assert len(m.relocs)==len(set(m.relocs)),'extra/duplicate relocation'")
t = rep(t, "[0x41b700,129],[0x41b6fc,161]]", "[0x41b700,129],[0x41b6fc,161],\n       [0x41b660,190],[0x41b658,236],[0x41b6b0,198],[0x41b624,187],[0x41b774,156],[0x41b65c,211]]")
t = rep(t, "'AmpJack43 u803 CANDIDATE','Not cleared for physical test',['Enable AmpJack43 candidate'],[False])",
           "'AmpJack63 u803 TEST','Not cleared for physical test',['Enable AmpJack63','Write log E:\\\\Trainers\\\\AmpJack63.log'],[False,False])")
t = rep(t, "creation_key='AMPJ43-CAND'", "creation_key='AMPJ63-TEST'")
t = rep(t, "info['options'][0]['default']==0\n manifest", "info['options'][0]['default']==0 and info['options'][1]['default']==0\n manifest")
t = rep(t, "'label':'candidate — not cleared for physical test'", "'label':'W63 test build — not cleared for physical test','names':list(NAMES)")
t = rep(t, """ paths=[ART/'pic.elf',ART/'layout.json',ART/'src/crt0.c',ART/'ogx_title_loader.py',REPO/'ogxbox/work/31-title-runtime/accept_handoff.py',REPO/'ogxbox/work/31-title-runtime/PARENT-ACCEPTED.json',REPO/'ogxbox/work/33-title-input-repair/module-journal-33.json']
 paths +=[REPO/'ogxbox/integration'/n for n in ['ogx_module.h','ogx_install.c','ogx_stub.c','ogx_transport.c','module_main.c']]""",
""" paths=[ART/'pic.elf',ART/'layout.json',ART32/'ogx_title_loader.py',REPO/'ogxbox/work/31-title-runtime/PARENT-ACCEPTED.json']
 paths +=sorted(p for p in (ROOT/'src').rglob('*') if p.is_file() and '/out/' not in str(p))""")
t = rep(t, "assert info['creation_key']=='AMPJ43-CAND'", "assert info['creation_key']=='AMPJ63-TEST'")
(W / 'build.py').write_text(t)

# ---------------- loader.c
t = (S / 'loader.c').read_text()
t = rep(t, """__attribute__((noinline)) static int adapter_call(u8 *b){
 return ((int(*)(void*)) (b+ENTRY_OFF))(0);
}""", """__attribute__((noinline)) static int adapter_call(u8 *b,u32 flags){
 return ((int(*)(u32)) (b+ENTRY_OFF))(flags);   /* W63: bit0 = write log */
}""")
t = rep(t, " if(!title_ok())return;\n rc=", " if(!title_ok())return;\n flags=(op+1<sz && t[op+1]==1)?1u:0u;   /* W63: XBTF option [1] */\n rc=")
t = rep(t, " u8 *f=0,*b=0; s32 rc;u8 extra;", " u8 *f=0,*b=0; s32 rc;u8 extra;u32 flags;")
t = rep(t, " rc=adapter_call(b);", " rc=adapter_call(b,flags);")
t = rep(t, " * AJ43 matched-pair pre-entry loader.", " * AJ43 matched-pair pre-entry loader (W63 copy: entry argument = option flags,\n * six extra resolved-slot checks for the log file I/O + KeTickCount).")
(W / 'loader.c').write_text(t)

# ---------------- test_candidate.py
t = (S / 'test_candidate.py').read_text()
t = rep(t, "  d=bytearray(self.data);d[B.TF.u32(d,10)]=0 if case=='disabled' else 1\n",
           "  d=bytearray(self.data);d[B.TF.u32(d,10)]=0 if case=='disabled' else 1\n  self.flags=1 if case=='log' else 0\n  if case=='log':d[B.TF.u32(d,10)+1]=1\n")
t = rep(t, "(0x41b700,'raise',0),(0x41b6fc,'lower',0)]", "(0x41b700,'raise',0),(0x41b6fc,'lower',0),\n                                     (0x41b660,'ntcreate',9),(0x41b658,'ntwrite',8),(0x41b6b0,'ntflush',2),(0x41b774,'ketick',0),(0x41b65c,'ntquery',5)]")
t = rep(t, "  if case=='missing_slot':m.mem_write(0x41b700,pk(0))", "  if case=='missing_slot':m.mem_write(0x41b700,pk(0))\n  if case=='missing_log_slot':m.mem_write(0x41b660,pk(0))\n  if case=='unresolved_tick':m.mem_write(0x41b774,pk(0x8000009c))")
t = rep(t, "assert self.word(sp+4)==0,'cdecl ignored argument must be caller-balanced'", "assert self.word(sp+4)==self.flags,'cdecl flags argument'")
t = rep(t, "x.mod.module_off+21128", "x.mod.module_off+x.mod.layout['status_fields']['install_failed']", 2)
t = rep(t, "x.mod.module_off+21124", "x.mod.module_off+x.mod.layout['status_fields']['installed_hooks']", 2)
t = rep(t, "self.assertEqual(x.allocs,{base:0x9000});self.assertEqual(x.peak,0xd000)",
           "self.assertEqual(x.allocs,{base:x.man['resident_alloc']});self.assertEqual(x.peak,x.man['resident_alloc']+x.man['file_buffer_alloc'])")
t = rep(t, "self.assertEqual(x.allocs,{x.base:0x9000})", "self.assertEqual(x.allocs,{x.base:x.man['resident_alloc']})")
t = rep(t, "'missing_slot','unresolved_slot',", "'missing_slot','missing_log_slot','unresolved_tick','unresolved_slot',")
t = rep(t, "'already_installed','missing_slot']:", "'already_installed','missing_slot','missing_log_slot','unresolved_tick']:")
t = rep(t, "if __name__=='__main__':", """ def test_08_log_flag(self):
  # W63: XBTF option [1] -> cdecl entry argument 1; the entry itself does no file I/O.
  for base in (0x1000000,0x83000000):
   x=Machine(base,case='log').run();self.assertEqual(x.entered,1)
   self.assertEqual(x.word(base+x.mod.module_off+x.mod.layout['status_fields']['installed_hooks']),191)
   self.assertFalse(any(c.startswith('nt') for c in x.calls))
  print('PASS log option -> entry flags=1 at both bases, no file I/O at entry')
if __name__=='__main__':""")
(W / 'test_candidate.py').write_text(t)

# ---------------- release.py
t = (S / 'release.py').read_text()
t = rep(t, "archive=out/'AmpJack43-u803-candidate.zip'", "archive=out/'AmpJack63-u803-test.zip'")
(W / 'release.py').write_text(t)
(W / 'README.txt').write_text(
"AmpJack63 u803 TEST (W63) -- Halo 2 u803 only. NOT cleared for physical test.\n"
"Copy the .xbtf and .bin to E:\\Trainers\\. Options: [0] Enable AmpJack63, [1] Write log\n"
"E:\\Trainers\\AmpJack63.log (default off). With [1] off the module does no file I/O.\n"
"Changes vs AmpJack43: wired pad re-handshake on ANNOUNCE (wake), rumble forwarding,\n"
"opt-in diagnostic log. Unverified on hardware.\n")
print('packaging copies written')
