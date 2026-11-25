#!/usr/bin/env python3
"""W45 observer. No launcher; live API uses parent's EXISTING paused clients.
CLI offline fixtures exercise the identical pins, arming, loop and decoder.
Fixtures are synthetic control/ABI cases, NOT execution or input evidence.
"""
import argparse
import hashlib
import fcntl
import sys
sys.dont_write_bytecode=True
import json
import os
import re
import struct
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT.parent
DUMP = WORK/'35-loading-stop/probe3/mem_00412000_a000.bin'
ELF = WORK/'32-opus-final-integration/artifact/pic.elf'
LAYOUT = WORK/'32-opus-final-integration/artifact/layout.json'
XBE = Path('/home/roasted/Desktop/Xbox/H2-Decomp/tu15-decomp/targets/halo2-tu15-u803/default.xbe')
HASHES = {'dump':'9d5dac16db6d1d7e431fd8cf7e89bb215de54d013f1852686d7311fe87255054',
          'elf':'7bbfdafaa91920269876aa54e02efe278b738c0298aeb7bd629b1aaf8a1a08b8',
          'layout':'c1ecc50ad14a86246f516df080b96c50e348cefa5d5f779916c78164443858f6',
          'xbe':'21b207e7efdacaf6124a0822837f8be570766a42505057f7fd2d2ba8f409c4fd'}
WATCHES = [(0x490930,4),(0x490928,1)]
# Verified function/call/instruction starts; NOT arbitrary byte-scanned addresses.
STOCK = {0x416375:'enqueue',0x41655f:'stage0',0x416568:'pre_invalid_access',
         0x4165c6:'native_remove_complete',0x41663c:'remove_dispatch',
         0x41668e:'enum_next',0x41673d:'stock_removal',0x4167f9:'finish_failed_or_aborted',
         0x41688d:'abort_callback',0x4168c0:'failure',0x416992:'native_add_complete',
         0x417078:'timer_dpc',0x4170b1:'pre_stage1_deref'}
MODULE = {0xa0a:'module_attach',0xd13:'module_remove',0xee7:'module_add_wrapper',
          0xab1:'module_refused_add_call',0x2ada:'module_signal_add',
          0x2bbc:'module_normal_add_call',0xf06:'module_native_add_call',
          0xf32:'module_remove_wrapper',0xf4f:'module_remove_tail'}

# Inert, exact TU instruction starts, NOT additional breakpoints or a writer map.
# Upper edges are static reachability only, never an observed upper stack.
LOCAL_INSTRUCTIONS = (
    (0x1273f4,'e8a7c52e00'), (0x4139a0,'e992f3ffff'),
    (0x412d37,'55'), (0x412d38,'8d6c2490'),
    (0x412d91,'b9b0084900'), (0x412d96,'e820040000'),
    (0x4131bb,'55'), (0x4131bc,'8bec'), (0x4131be,'8a4508'),
    (0x4131c1,'53'), (0x4131c2,'56'), (0x4131c3,'57'),
    (0x4131c4,'8bf1'), (0x4131c6,'0fb6f8'), (0x4131c9,'88467a'),
    (0x4131cc,'33db'), (0x4131ce,'8bc7'), (0x4131d0,'6855534244'),
    (0x4131d5,'c1e005'), (0x4131d8,'50'), (0x4131d9,'881e'),
    (0x4131db,'885e79'), (0x4131de,'895e7c'), (0x4131e1,'899e80000000'),
    (0x4131e7,'e8dd300000'))
LOCAL_WINDOW = '0550881e885e79895e7c899e80000000e8dd3000003bc389450874136831634100576a2050e84fd4c0ff8b4508eb0233c00fb64e7a8986e00000008a450c8846'

def local_descriptor():
    return dict(kind='stock_object_80_store_pre_alloc',writer=0x4131e1,
                post_pc=0x4131e7,width=4,object=0x4908b0,ea=0x490930,
                direct_call=0x412d96,direct_return=0x412d9b,
                window_address=0x4131d7,window=LOCAL_WINDOW,
                xbe_sha256=HASHES['xbe'],instructions=list(LOCAL_INSTRUCTIONS))

class Refusal(RuntimeError): pass

def need(ok, msg):
    if not ok: raise Refusal(msg)

def sha(data): return hashlib.sha256(data).hexdigest()
def u32(data, off=0): return struct.unpack_from('<I',data,off)[0]
def signed(v): return v if v < 0x80000000 else v-0x100000000

def disassemble(args):
    out = subprocess.run(args,check=True,capture_output=True,text=True).stdout
    instructions = {}
    for line in out.splitlines():
        m = re.match(r'^\s*([0-9a-f]+):\s*((?:[0-9a-f]{2}\s+)+)\s*(.*)$',line)
        if m:
            b=bytes.fromhex(m[2]); instructions[int(m[1],16)]={'bytes':b.hex(),'asm':m[3]}
    return instructions, out

def elf_sections(data):
    off=u32(data,32); size,n,strings=struct.unpack_from('<HHH',data,46)
    sh=[struct.unpack_from('<10I',data,off+i*size) for i in range(n)]
    st=sh[strings]; names=data[st[4]:st[4]+st[5]]
    result={}
    for s in sh:
        name=names[s[0]:].split(b'\0',1)[0].decode()
        result[name]=s
    return result

def prepare() -> dict:
    files={'dump':DUMP,'elf':ELF,'layout':LAYOUT,'xbe':XBE}
    blobs={k:p.read_bytes() for k,p in files.items()}
    for k,b in blobs.items(): need(sha(b)==HASHES[k],f'{k} identity mismatch')
    layout=json.loads(blobs['layout']); need(layout['elf_sha256']==HASHES['elf'],'layout ELF mismatch')
    sd,stock_dis=disassemble(['objdump','-D','-w','-b','binary','-m','i386','--adjust-vma=0x412000','--start-address=0x416343','--stop-address=0x4170cc',str(DUMP)])
    md,module_dis=disassemble(['llvm-objdump','-d',str(ELF)])
    sections=elf_sections(blobs['elf']); text=sections['.text']; textbytes=blobs['elf'][text[4]:text[4]+text[5]]
    need(text[3]==0,'unexpected text address')
    # Independent frozen XBE mapping: every stock pin must also match this code.
    xb=blobs['xbe']; bas=u32(xb,0x104); table=u32(xb,0x120)-bas
    xs=[struct.unpack_from('<4I',xb,table+i*56+4) for i in range(u32(xb,0x11c))]
    def frozen(addr,n):
        for va,vs,raw,rs in xs:
            if va<=addr and addr+n<=va+rs: return xb[raw+addr-va:raw+addr-va+n]
        raise Refusal('stock address not in frozen XBE')
    # Authenticated mapped stock code; no live observation is supplied by this.
    for addr,encoded in LOCAL_INSTRUCTIONS:
        need(frozen(addr,len(bytes.fromhex(encoded))).hex()==encoded,
             f'local descriptor static edge mismatch {addr:#x}')
    need(frozen(0x4131d7,64).hex()==LOCAL_WINDOW,'local descriptor window mismatch')
    pins=[]
    def add(addr,name,relative=False):
        dec=md if relative else sd
        need(addr in dec, f'not instruction boundary: {addr:#x}')
        ins=dec[addr]; b=bytes.fromhex(ins['bytes'])
        source=textbytes[addr:addr+len(b)] if relative else blobs['dump'][addr-0x412000:addr-0x412000+len(b)]
        need(b==source,'disassembler byte mismatch')
        if not relative: need(b==frozen(addr,len(b)),f'XBE/dump code mismatch {addr:#x}')
        pins.append(dict(offset=addr,relative=relative,event=name,**ins))
    for a,n in STOCK.items(): add(a,n)
    for a,n in MODULE.items(): add(a,n,True)
    # All enum timer imports in the decoded region, including initial arm, not just EnumNext.
    for addr,ins in sd.items():
        b=ins['bytes']
        if b in ('ff15f8b64100','ff1588b74100'):
            name='timer_arm' if b=='ff15f8b64100' else 'timer_cancel'
            add(addr,name); add(addr+6,name+'_return')
    # Pin BOTH known current writers and their post-write PCs; watch report is post-write.
    writers={}
    for addr,ins in sd.items():
        if ins['bytes'] in ('893530094900','891d30094900','a330094900'):
            add(addr,'current_writer'); end=addr+len(bytes.fromhex(ins['bytes']))
            add(end,'current_write_post'); writers[end]=addr
    need(0x41672e not in sd and sd[0x41672d]['bytes']=='6800094900','legacy RED boundary oracle')
    nm=subprocess.run(['llvm-nm','-n',str(ELF)],check=True,capture_output=True,text=True).stdout
    symbols={p[2]:int(p[0],16) for l in nm.splitlines() if len(p:=l.split())==3}
    need(symbols['ogx_g_module']==0x3978,'module symbol mismatch')
    need(symbols['ogx_gip_attach']==0xa0a and symbols['ogx_gip_remove']==0xd13,'callback offsets mismatch')
    # All callers and possible tail transfers remain available for exact return decoding.
    live_header=bytearray(xb[:0x178])
    for off,key in ((0x128,0xa8fc57ab),(0x158,0x5b6d40b6)):
        struct.pack_into('<I',live_header,off,u32(live_header,off)^key)
    return dict(pins=pins,stock=sd,module=md,text=textbytes.hex(),writers=writers,live_header=live_header.hex(),
                local_observer=local_descriptor(),
                symbols=symbols,hashes=HASHES,legacy_red={'address':0x41672e,'containing_start':0x41672d,'bytes':'6800094900'},
                stock_dis=stock_dis,module_dis=module_dis)

def validate_identity(identity, actual):
    for key in ('boot_id','pid','start_ticks','elf_sha256','layout_sha256'):
        need(identity.get(key)==actual.get(key),f'stale {key}')
    need(identity['elf_sha256']==HASHES['elf'],'stale ELF')
    need(identity['layout_sha256']==HASHES['layout'],'stale layout')
    need(isinstance(identity['base'],int) and identity['base']%4096==0,'invalid module base')
    need(identity['module']==identity['base']+0x3978,'wrong module instance')

def verify_pins(r,plan,base):
    if 'local_observer' in plan:
        need(plan['local_observer']==local_descriptor(),'mutated local observer descriptor')
    need(r.read(0x10000,0x178).hex()==plan['live_header'],'live TU header mismatch before address use')
    # Reject malformed/mutated manifests against independent instruction maps
    # BEFORE any breakpoint/watch command, not only against a cooperative backend.
    for p in plan['pins']:
        code=plan['module'] if p['relative'] else plan['stock']
        need(p['offset'] in code,f"not instruction boundary: {p['offset']:#x}")
        need(p['bytes']==code[p['offset']]['bytes'],'mutated expected pin')
    need(r.read(0x10114,4)==bytes.fromhex('2ba60046'),'wrong title')
    need(r.read(base,len(bytes.fromhex(plan['text']))).hex()==plan['text'],'live ELF text mismatch')
    for p in plan['pins']:
        a=p['offset']+(base if p['relative'] else 0)
        need(r.read(a,len(bytes.fromhex(p['bytes']))).hex()==p['bytes'],f'pin mismatch {a:#x}')

class Journal:
    def __init__(self,path,max_events=4096):
        self.f=Path(path).open('x'); self.seq=0; self.maximum=max_events; self.last=0
        fcntl.flock(self.f,fcntl.LOCK_EX|fcntl.LOCK_NB)
    @classmethod
    def resume(cls,path,checkpoint):
        obj=cls.__new__(cls);obj.f=Path(path).open('a+')
        try:
            fcntl.flock(obj.f,fcntl.LOCK_EX|fcntl.LOCK_NB)
            obj.f.seek(0);rows=[json.loads(line) for line in obj.f]
            need(rows and rows[-1]==checkpoint,'capture continuity checkpoint changed')
            need(checkpoint['event']=='outgoing_checkpoint','not a sealed outgoing recorder')
            need([row['seq'] for row in rows]==list(range(1,len(rows)+1)),'capture continuity sequence broken')
            obj.seq=checkpoint['seq'];obj.last=checkpoint['monotonic_ns'];obj.maximum=None
            obj.f.seek(0,2)
            return obj
        except BaseException:obj.f.close();raise
    def emit(self,event,**fields):
        need(self.maximum is None or self.seq<self.maximum,'event bound reached: attribution unknown')
        now=time.monotonic_ns(); need(now>self.last,'nonmonotonic logger')
        self.last=now; self.seq+=1
        row=dict(seq=self.seq,monotonic_ns=now,event=event,**fields)
        self.f.write(json.dumps(row,sort_keys=True)+'\n'); self.f.flush(); os.fsync(self.f.fileno())
        return row
    def close(self): self.f.close()

def snapshot(r):
    regs=r.regs(); esp=regs['esp']; state=r.read(0x4908b0,0x84)
    memory=[{'address':0x4908b0,'hex':state.hex()}, {'address':esp,'hex':r.read(esp,64).hex()}]
    if regs.get('ebp',0):
        try: memory.append({'address':regs['ebp'],'hex':r.read(regs['ebp'],16).hex()})
        except Exception: pass
    if regs['eip']==0x4131e7:
        # Ordinary stopped read only. A reader without it must remain held.
        try: memory.append({'address':regs['eip']-16,'hex':r.read(regs['eip']-16,64).hex()})
        except Exception: pass
    return {'regs':regs,'memory':memory}

def read_snapshot(s,a,n):
    for b in s['memory']:
        data=bytes.fromhex(b['hex']); start=b['address']
        if start<=a and a+n<=start+len(data): return data[a-start:a-start+n]
    raise Refusal(f'missing snapshot bytes {a:#x}+{n}')

class Decoder:
    def __init__(self,plan,base):
        self.plan=plan; self.base=base; self.arm=None; self.tail=None
        self.attempt=None
        self.events={}
        for p in plan['pins']:
            a=p['offset']+(base if p['relative'] else 0)
            self.events.setdefault(a,[]).append(p['event'])
    def decode(self,s,why):
        g=s['regs']; pc=g['eip']
        try: stack=read_snapshot(s,g['esp'],64)
        except Refusal: stack=None
        st=read_snapshot(s,0x4908b0,0x84)
        cur=u32(st,0x80); names=self.events.get(pc,[])
        row={'eip':pc,'regs':g,'stop_reason':why,'raw_snapshot':s,'events':names,
             'current':cur,'pending':u32(st,0x7c),'stage':st[0x78],'marker':st[3],
             'abort':st[1], 'timer_raw':st[0x50:0x78].hex(),
             'timer_signal_state':u32(st,0x54),'timer_inserted':st[0x53],
             'device':None,'status':None,'return_candidate':u32(stack) if stack else None,'caller':'unknown',
             'timer_arm_device':self.arm,'attribution':'unknown'}
        if pc==0x4131e7:
            # Attribution alone never grants this exception. Default hold even
            # if someone inserted this post-PC into the ordinary writer map.
            row['unclassified']=True
            row['writer']=None; row['writer_kind']='unknown'
            try:
                need(self.plan.get('local_observer')==local_descriptor(),'missing/authentication-invalid local descriptor')
                need(why=='T05thread:01;watch:490930;','ambiguous local hardware stop reason')
                # All overlapping captured spans must agree, not first-match wins.
                seen={}
                for block in s['memory']:
                    for i,value in enumerate(bytes.fromhex(block['hex'])):
                        address=block['address']+i
                        need(address not in seen or seen[address]==value,'conflicting local snapshot overlaps')
                        seen[address]=value
                need(read_snapshot(s,pc-16,64).hex()==LOCAL_WINDOW,'missing/mismatched stopped code window')
                need(g['esi']==g['ecx']==0x4908b0 and g['esi']+0x80==0x490930,'local object/EA mismatch')
                need(g['ebx']==0 and cur==g['ebx'],'local stored value mismatch')
                row.update(writer=0x4131e1,writer_kind='stock_object_80_store_pre_alloc',
                           writer_width=4,writer_ea=0x490930,stored_value=cur)
                need(g['esp']==g['ebp']-20,'local frame relation mismatch')
                frame=read_snapshot(s,g['ebp'],16)
                need(u32(frame,4)==0x412d9b,'local direct caller mismatch')
                need(u32(frame,8)==29 and u32(frame,12)==2,'local frame args mismatch')
                need(g['edi']==29 and st[0x7a]==29,'local argument/object byte mismatch')
                need(stack is not None and g['eax']==u32(stack)==0x3a0,'local allocation size mismatch')
                need(u32(stack,4)==0x44425355,'local allocation tag mismatch')
                row.update(direct_caller=0x412d96,direct_return=0x412d9b,
                           local_observer_qualified=True)
                row.pop('unclassified')
            except (Refusal,KeyError,ValueError,struct.error) as ex:
                row['local_observer_failure']=str(ex)
        elif 'watch:' in why:
            if 'watch:490930;' in why:
                row['writer']=self.plan['writers'].get(pc)
                row['writer_kind']='verified_post_write_pc' if row['writer'] else 'unknown'
                if row['writer'] is None: row['unclassified']=True
            elif 'watch:490928;' in why: row['writer_kind']='stage_watch_post_pc_not_writer'
            else: row['unclassified']=True
        elif not names: row['unclassified']=True
        if stack is None:
            row['unclassified']=True
            row['stack_unavailable']=True
            return row
        # Entry ABIs only; never infer a return address from arbitrary mid-function ESP.
        if pc in (0x416992,0x4165c6,0x4167f9): row['device']=g['ecx']
        if pc==0x416992: row['status']=signed(u32(stack,4))
        if pc in (0x41688d,0x4168c0,0x41668e): row['device']=u32(stack,8)
        if pc==0x41688d: row['status']=signed(u32(stack,4))
        if pc in (0x416375,0x41673d):
            row['hub']=g['ecx']; row['port']=u32(stack,4)
        if pc in (self.base+0xa0a,self.base+0xd13,self.base+0xee7,self.base+0xf32):
            row['device']=u32(stack,4)
        if pc==self.base+0xee7: row['status']=signed(u32(stack,8))
        if pc==self.base+0x2ada:
            row['attach_ctx']=g['ecx']; row['status']=signed(g['edx'])
        if pc in (self.base+0xab1,self.base+0x2bbc):
            row['device']=u32(stack); row['status']=signed(u32(stack,4))
        if pc==self.base+0xf06:
            row['device']=g['ecx']; row['status']=signed(u32(stack))
        # Native AddComplete's wrapper has NOT tail-called: authenticate exact saved frame return.
        if pc==0x416992 and u32(stack)==self.base+0xf08:
            try:
                origin=u32(read_snapshot(s,g['ebp']+4,4))
                row['wrapper_return']=origin
                if origin==self.base+0xab7: row['caller']='module_refused_attach_transport_c_202'
                elif origin==self.base+0x2bbe: row['caller']='module_signal_add_complete'
            except Refusal: pass
        elif pc in (0x416992,0x4165c6,0x4167f9,0x41668e,0x41688d,0x4168c0):
            ret=u32(stack)
            candidates=[]
            for a,i in self.plan['stock'].items():
                b=bytes.fromhex(i['bytes'])
                if a+len(b)==ret and len(b)==5 and b[0]==0xe8:
                    target=(ret+struct.unpack_from('<i',b,1)[0])&0xffffffff
                    if target==pc: candidates.append(a)
            if len(candidates)==1: row['caller']='stock_call'; row['callsite']=candidates[0]
        if pc==self.base+0xf4f:
            self.tail={'device':g['ecx'],'esp':g['esp'],'return':u32(stack)} if g['eax']==0x4165c6 else None
            row['device']=g['ecx']; row['tail_target']=g['eax']
        elif pc==0x4165c6 and self.tail:
            if self.tail=={'device':g['ecx'],'esp':g['esp'],'return':u32(stack)}:
                row['caller']='module_remove_tail'; row['tail_site']=self.base+0xf4f
            self.tail=None
        elif self.tail: self.tail=None
        if 'timer_arm' in names:
            row['timer_argument']=u32(stack); row['due_time_hex']=stack[4:12].hex(); row['dpc_argument']=u32(stack,12)
            self.attempt={'device':cur,'callsite':pc}
        if 'timer_arm_return' in names:
            self.arm=self.attempt
            row['timer_arm_device']=self.arm; row['previous_timer_inserted']=bool(g['eax']&255)
        if 'timer_cancel_return' in names:
            row['cancel_result']=bool(g['eax']&255)
            if row['cancel_result']: self.arm=None
        if pc==0x417078:
            row['expiry_arm_device']=self.arm; self.arm=None
        if pc in (0x416568,0x4170b1) and (g.get('esi')==0 if pc==0x416568 else g['eax']==0):
            row['pre_fault_hold']=True
        return row

class CaptureDecoder:
    """Ordered raw ring and actually returned virtual-slot packets.

    Cursor transfers durably; loss refuses. Zero reports is untested, not input.
    """
    def __init__(self,layout,head=None):
        self.v=layout['values'];self.head=head
    def decode(self,module,*,returned=None):
        v=self.v;need(len(module)==v['module_size'],'short module capture')
        head=u32(module,v['ring_head']); rows=[]
        if self.head is not None:
            delta=(head-self.head)&0xffffffff
            need(delta<=v['ring_cap'],'raw ring overwritten; capture continuity lost')
            for i in range(delta):
                index=(self.head+i)%v['ring_cap'];off=v['ring']+index*v['evt_size']
                event=module[off:off+v['evt_size']];kind=u32(event,v['evt_type']);n=u32(event,20)
                need(n<=v['evt_size']-v['evt_data'],'invalid raw event length')
                rows.append(dict(event='raw_report' if kind==8 else 'transport_event',kind=kind,
                    ring_index=(self.head+i)&0xffffffff,req_id=u32(event,28),tick=u32(event,32),
                    status=u32(event,4),data=event[v['evt_data']:v['evt_data']+n].hex(),raw=event.hex()))
        self.head=head
        state=dict(input_reports=u32(module,v['gip_reports']),snapshot_valid=bool(u32(module,v['gip_valid'])),
                   served_packet=u32(module,v['served']),served_seq=u32(module,v['served_seq']),
                   gamepad=module[v['gamepad']:v['gamepad']+18].hex(),
                   native_mask=u32(module,v['native_mask']),ring_head=head,
                   ring_tail=u32(module,v['ring_tail']),overflow=u32(module,v['ring_overflow']))
        need(state['overflow']==0,'transport overflow; lossless capture unsupported')
        if returned is not None:
            packet=bytes.fromhex(returned['packet'])
            need(returned['status']==0 and returned['virtual_port']==1,'not successful virtual slot')
            need(state['snapshot_valid'] and module[v['port_valid']]!=0 and not state['native_mask']&2,'virtual slot not valid/exclusive')
            need(len(packet)>=22 and u32(packet)==state['served_packet'] and packet[4:22].hex()==state['gamepad'],'served packet differs from module snapshot')
            rows.append(dict(event='served_slot',returned=returned,**state))
        return dict(events=rows,state=state,cursor=dict(ring_head=head))

def observe(r,plan,identity,actual,journal,*,seconds=120,max_stops=2048,was_running=False):
    """Existing stopped RSP, caller retains QMP. Does NOT open/close either client.
    Returns explicit state obligation. Refusal before arming never resumes.
    Caller must restore QMP to prior state, except safety holds require quit/owned handoff.
    """
    validate_identity(identity,actual)
    base=identity['base']; verify_pins(r,plan,base)
    need(r.regs()['eip']==0x2da9de,'not decoded pre-XInitDevices entry')
    armed=[]; hold=False; decoder=Decoder(plan,base); result={'state':'paused','hold':False}
    try:
        for p in plan['pins']:
            a=p['offset']+(base if p['relative'] else 0); item=(0,a,1)
            if item in armed: continue
            need(r.cmd(f'Z0,{a:x},1')=='OK','partial breakpoint arm failure'); armed.append(item)
        for a,n in WATCHES:
            need(r.cmd(f'Z2,{a:x},{n:x}')=='OK','partial watch arm failure'); armed.append((2,a,n))
        journal.emit('armed',fixture=getattr(r,'fixture',False),identity=identity,pins=len(armed),was_running=was_running)
        end=time.monotonic()+seconds
        for _ in range(max_stops):
            if time.monotonic()>=end: break
            try: why=r.continue_wait(timeout=min(60,max(0.01,end-time.monotonic())))
            except TimeoutError:
                journal.emit('timeout_paused',fixture=getattr(r,'fixture',False)); break
            need(r.read(0x10000,0x178).hex()==plan['live_header'],'live TU header changed before snapshot')
            raw=snapshot(r)
            row=decoder.decode(raw,why); journal.emit('stop',fixture=getattr(r,'fixture',False),**row)
            if row.get('pre_fault_hold') or row.get('unclassified'):
                hold=True; break
            pc=raw['regs']['eip']
            if 'watch:' not in why:
                need(r.cmd(f'z0,{pc:x},1')=='OK','remove hit breakpoint failed')
                why_step=r.step()
                # A write can trap during the step; never drop that transition.
                if 'watch:' in why_step or r.regs()['eip']==0x4131e7:
                    need(r.read(0x10000,0x178).hex()==plan['live_header'],'live TU header changed during step')
                    row=decoder.decode(snapshot(r),why_step)
                    journal.emit('step_watch',fixture=getattr(r,'fixture',False),**row)
                    if row.get('unclassified') or row.get('pre_fault_hold'): hold=True; break
                need(r.cmd(f'Z0,{pc:x},1')=='OK','rearm hit breakpoint failed')
        else:
            hold=True; journal.emit('stop_bound_unknown')
    except Exception as e:
        hold=True; result['error']=str(e)
        journal.emit('exception_hold',message=str(e))
        raise
    finally:
        errors=[]
        for kind,a,n in reversed(armed):
            try: need(r.cmd(f'z{kind},{a:x},{n:x}')=='OK','cleanup refused')
            except Exception as e: errors.append(str(e))
        hold=hold or bool(errors)
        result.update(hold=hold,cleanup_errors=errors,state='paused',restore_running=was_running and not hold)
        # No unconditional continue. Parent/QMP must explicitly restore state after clients close.
        journal.emit('cleanup',**result)
    return result

def finish_clients(q,r,*,prior_running,hold):
    """Same parent-owned clients only; never opens a second QMP session.
    Refusal/safety hold overrides ordinary restoration. Parent owns QMP quit.
    """
    wanted=bool(prior_running and not hold)
    try:
        q.cmd('cont' if wanted else 'stop')
        state=q.cmd('query-status')
        need(state['running']==wanted,'QMP state restoration failed')
        return {'running':wanted,'safety_hold':hold,'clients_closed':True}
    finally:
        try: r.close()
        finally:
            try: q.f.close()
            finally:
                try: q.s.close()
                finally: q.close()

class FixtureQMP:
    """Synthetic closure/state contract only, not an emulator."""
    def __init__(self,running):
        self.running=running; self.calls=[]; self.f=self.Endpoint(); self.s=self.Endpoint(); self.closed=False
    class Endpoint:
        def __init__(self): self.closed=False
        def close(self): self.closed=True
    def cmd(self,name):
        self.calls.append(name)
        if name=='cont': self.running=True
        if name=='stop': self.running=False
        return {'running':self.running}
    def close(self): self.closed=True

class Fixture:
    fixture=True
    def __init__(self,data,plan):
        self.data=data; self.plan=plan; self.index=-1; self.calls=[]; self.active=set()
        self.mem=[]; self.current={'regs':{'eip':0x2da9de},'memory':[]}
        self.base=data['identity']['base']; self.mutation=data.get('mutate_pin')
    def read(self,a,n):
        if a==0x10000 and n==0x178:return bytes.fromhex(self.plan['live_header'])
        if a==0x10114: return bytes.fromhex('2ba60046')
        if self.base<=a and a+n<=self.base+len(bytes.fromhex(self.plan['text'])):
            b=bytes.fromhex(self.plan['text'])[a-self.base:a-self.base+n]
        elif 0x412000<=a and a+n<=0x41c000: b=DUMP.read_bytes()[a-0x412000:a-0x412000+n]
        else: return read_snapshot(self.current,a,n)
        if self.mutation is not None and a<=self.mutation<a+n:
            b=bytearray(b); b[self.mutation-a]^=1; b=bytes(b)
        return b
    def regs(self): return self.current['regs']
    def cmd(self,c):
        self.calls.append(c); need(c[0] in 'Zz','fixture rejects write/control command')
        if c[0]=='Z':
            if len(self.active)==self.data.get('fail_arm_after',-1): return 'E01'
            self.active.add(c[1:])
        else: self.active.discard(c[1:])
        return 'OK'
    def continue_wait(self,timeout):
        self.index+=1
        if self.index>=len(self.data['stops']): raise TimeoutError('synthetic timeout; paused')
        self.current=self.data['stops'][self.index]['snapshot']
        return self.data['stops'][self.index]['why']
    def step(self): return 'T05'  # synthetic step; not CPU execution
    def close(self): self.closed=True

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    mode=ap.add_mutually_exclusive_group(required=True)
    mode.add_argument('--fixture',type=Path)
    mode.add_argument('--archive',action='store_true',help='decode actual W35 saved final state only')
    ap.add_argument('--log',type=Path,required=True)
    ap.add_argument('--pins-out',type=Path)
    a=ap.parse_args(); plan=prepare()
    for output in (a.log, a.pins_out):
        if output is not None: need(output.resolve().is_relative_to(ROOT), 'output outside W45')
    if a.pins_out:
        a.pins_out.write_text(json.dumps({k:v for k,v in plan.items() if k not in ('text','stock_dis','module_dis')},indent=2)+'\n')
    if a.archive:
        saved=WORK/'35-loading-stop/probe3'
        state=(saved/'mem_00490000_1000.bin').read_bytes()
        need(sha(state)=='657ef96f85f11e6db9985e653e3b04d21d41bd50542d4b646b42d47748b8a891','archived state mismatch')
        record=json.loads((saved/'probe-1795588560.json').read_text())
        raw={'regs':record['regs'],'memory':[{'address':0x4908b0,'hex':state[0x8b0:0x934].hex()}]}
        decoder=Decoder(plan,0)  # no module base asserted by this archive
        j=Journal(a.log)
        try:
            j.emit('archived_final_state',fixture=False,live=False,provenance=str(saved),
                   **decoder.decode(raw,'ARCHIVE_POST_HALT_STACK_UNAVAILABLE'))
        finally: j.close()
        print('Decoded archived final state only; chronology and caller unknown; no guest access')
        return 0
    data=json.loads(a.fixture.read_text()); r=Fixture(data,plan); j=Journal(a.log)
    if data.get('legacy_pin'):
        for p in plan['pins']:
            if p['offset']==0x416732:
                p.update(offset=0x41672e,bytes='ff15f8b64100')
    if data.get('mutate_expected_pin'):
        plan['pins'][0]['bytes']='90'
    result: dict = {}
    try:
        result=observe(r,plan,data['identity'],data['actual'],j,was_running=data.get('was_running',False))
        result['outcome']='fixture_complete'
    except Exception as e:
        result={'outcome':'refused','reason':str(e)}
    finally:
        q=FixtureQMP(data.get('was_running',False))
        state=finish_clients(q,r,prior_running=data.get('was_running',False),hold=result.get('hold',False) or result.get('outcome')=='refused')
        result['restored_state']=state
        result['qmp_commands']=q.calls
        need(q.f.closed and q.s.closed and q.closed and r.closed,'fixture clients leaked')
        j.emit('clients_closed',fixture=True,**state)
        j.close()
    result.update(fixture=True,arm_commands=sum(c.startswith('Z') for c in r.calls),active_after_cleanup=sorted(r.active),commands=r.calls)
    a.log.with_suffix('.result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='commands'},sort_keys=True))
    return 2 if result['outcome']=='refused' else 0

if __name__=='__main__': raise SystemExit(main())
