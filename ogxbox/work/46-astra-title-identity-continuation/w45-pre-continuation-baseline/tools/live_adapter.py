#!/usr/bin/env python3
"""W45 existing-client loader/identity helpers. No launch on import."""
import hashlib
import importlib.util
import sys
sys.dont_write_bytecode=True
import json
import os
from pathlib import Path
import struct
import sys
import xml.etree.ElementTree as ET
import enum_watch as obs
ROOT=obs.ROOT
LEASE=ROOT/'PARENT-RUNTIME-LEASE.json'
sys.dont_write_bytecode=True
sys.path.insert(0,'/home/roasted/Desktop/Xbox/LAN_Stats/tools/xemu')
from gdbrsp import RSP
from qmp import QMP

def load_file(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); return mod

LOADER_PATH=ROOT.parent/'27-title-runtime/ogx_title_loader.py'
loader=load_file('w45_verified_loader',LOADER_PATH)

def save(name,obj):
    p=ROOT/name; obs.need(p.resolve().is_relative_to(ROOT),'output outside W45'); p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(obj,indent=2)+'\n'); return obj

def native(pid):
    p=Path(f'/proc/{pid}')
    st=p.joinpath('stat').read_text().rsplit(')',1)[1].split()
    exe=p.joinpath('exe').resolve(strict=True)
    return dict(pid=pid,start_ticks=int(st[19]),boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
                native_exe=str(exe),native_sha256=obs.sha(exe.read_bytes()),argv=p.joinpath('cmdline').read_bytes().decode().split('\0')[:-1])

def check_native(expected,lease):
    actual=native(expected['pid'])
    for k in ('pid','start_ticks','boot_id','native_sha256','argv'): obs.need(actual[k]==expected[k],f'native identity mismatch {k}')
    obs.need(actual['native_sha256']==lease['xemu_sha256'],'untrusted native hash')
    args=actual['argv']; obs.need(args[args.index('-config_path')+1]==str(Path(lease['fresh_clone'])/'xemu.toml'),'wrong config')
    return actual

def register_schema(r):
    docs={}
    def fetch(annex):
        raw=r.target_xml(annex)
        text=raw.replace('<target>','<target xmlns:xi="http://www.w3.org/2001/XInclude">',1)
        root=ET.fromstring(text); docs[annex]=raw
        regs=[]
        for child in root:
            if child.tag.endswith('include'): regs+=fetch(child.attrib['href'])
            else: regs+=list(child.iter('reg'))
        return regs
    regs=fetch('target.xml')
    names=[x.attrib['name'] for x in regs[:16]]
    obs.need(names=='eax ecx edx ebx esp ebp esi edi eip eflags cs ss ds es fs gs'.split(),'core register ordering mismatch')
    widths=[int(x.attrib['bitsize']) for x in regs]
    obs.need(all(w==32 for w in widths[:16]),'core register width mismatch')
    packet=r.raw_regs(); obs.need(len(bytes.fromhex(packet))*8==sum(widths),'register packet length mismatch')
    return dict(xml=docs,names=names,widths=widths,raw_g=packet)

def check_entry(r):
    obs.need(r.regs()['eip']==0x2da9de,'not decoded entry')
    pins=loader.Pins(); pins.verify_header(r)
    obs.need(r.read(0x2da9de,16)==pins.read(0x2da9de,16),'entry bytes mismatch')
    return dict(eip=r.regs()['eip'],header_hex=r.read(0x10000,0x178).hex(),entry_hex=r.read(0x2da9de,16).hex(),loader_path=str(LOADER_PATH),loader_sha256=obs.sha(LOADER_PATH.read_bytes()))

def allocate(r,identity):
    # Exact W31 proven allocator, without inject_trainer's hardcoded evidence directory.
    obs.need(r.regs()['eip']==0x2da9de,'allocation not at entry')
    scratch=0x233194; code=bytes.fromhex('ff1540b64100cc')
    saved=r.raw_regs(); g=r.regs(); old=r.read(scratch,len(code))
    obs.need(old==b'\xcc'*len(code),'scratch padding mismatch')
    sp=g['esp']-0x200; stack=r.read(sp,0x200)
    save('live/allocation-before.json',dict(identity=identity,regs=g,raw_g=saved,scratch=old.hex(),stack_address=sp,stack=stack.hex()))
    r.write(scratch,code); newsp=g['esp']-20
    r.write(newsp,struct.pack('<5I',0x9000,0,0xffffffff,0,4));r.set_regs(eip=scratch,esp=newsp)
    r.bp(scratch+6)
    try: why=r.continue_wait(15)
    finally: r.bp(scratch+6,False)
    after=r.regs(); obs.need(after['eip']==scratch+6 and after['esp']==g['esp'],'unexpected allocator stop')
    base=after['eax']; obs.need(base!=0 and base%4096==0,'invalid allocation')
    r.write(scratch,old);r.write(sp,stack);r.set_raw_regs(saved)
    obs.need(r.raw_regs()==saved and r.read(scratch,len(old))==old and r.read(sp,0x200)==stack,'allocator restore mismatch')
    r.write(base,b'\xff'*0x9000);obs.need(r.read(base,0x9000)==b'\xff'*0x9000,'allocation fill mismatch')
    return save('live/allocation-receipt.json',dict(base=base,extent=0x9000,fill_byte=255,allocation_id=f"W45-{identity['boot_id']}-{identity['pid']}-{identity['start_ticks']}",allocator_after=after,stop=why))

def install(r,receipt):
    m=loader.Module(obs.ELF.read_bytes(),json.loads(obs.LAYOUT.read_text()))
    tl=loader.TitleLoader(m,loader.Pins(),dict(loader.REQUIRED_BINDINGS,now_ms=0,cancel_request=0))
    result=tl.load(loader.GdbRspAdapter(r),receipt,str(ROOT/'live/module-journal.json'))
    obs.need(result['verdict']=='installed','module install refused')
    plan=tl.plan(receipt)
    obs.need(r.regs()['eip']==0x2da9de,'module call did not restore entry')
    obs.need(result['status']['installed_hooks']==0xbf and result['status']['install_failed']==0,'install flags')
    obs.need(r.read(receipt['base'],13928)==obs.ELF.read_bytes()[m._file_off(0,13928):m._file_off(0,13928)+13928],'full text mismatch')
    for n,s in plan['sites'].items(): obs.need(r.read(s['va'],len(bytes.fromhex(s['expect']))).hex()==s['expect'],f'hook readback {n}')
    host={n:int.from_bytes(r.read(plan['module']+o,4),'little') for n,o in m.layout['host_fields']}
    obs.need(host['xdevice_type_gamepad']==0x4127d8 and host['irql_raise_slot']==0x41b700 and host['irql_lower_slot']==0x41b6fc,'host address binding mismatch')
    return save('live/install-verified.json',dict(result=result,base=receipt['base'],module=plan['module'],module_symbol=m.module_off,host=host,sites=plan['sites'],text_sha256=obs.sha(r.read(receipt['base'],13928)),loader_path=str(LOADER_PATH),loader_sha256=obs.sha(LOADER_PATH.read_bytes())))

def close_q(q):
    try:q.f.close()
    finally:
        try:q.s.close()
        finally:q.close()
