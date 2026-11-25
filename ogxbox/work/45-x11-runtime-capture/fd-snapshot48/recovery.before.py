#!/usr/bin/env python3
"""Exact existing-invocation recovery. No launch, claim or offline HDD path."""
import sys
sys.dont_write_bytecode=True
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time
import live_adapter as a
import enum_watch as e
import runtime_effects as f
import parent_launch as w
R=a.ROOT
OUT='continuation-2/recovery/live/'
PIN=dict(pid=2615613,start_ticks=19255692,boot_id='6c1c7a00-204d-4091-b6f5-caf6e5097ff8',
    invocation='47eda205a040482c8114303de677cd11',unit='ampjack-parent45-devkit.service',
    cgroup='/user.slice/user-1000.slice/user@1000.service/app.slice/ampjack-parent45-devkit.service',
    claim_sha256='f54e2b26b1284e0316939b6b752f6d48926e8b169cf8e45e75a3bf17660684db',socket_inode='34276870')

def authorize(c,session,pin=PIN):
    b=c.get('runtime_binding',{})
    e.need(c.get('owner_hold') is False and c.get('resume_authorized') is True
        and c.get('runtime_card')=='t_af7623e9'
        and c.get('runtime_owner')=='45-x11-runtime-capture exclusive conditional lease; no parent clients or competing writer'
        and b.get('state')=='verified' and session and b.get('session')==session
        and b.get('card')=='t_af7623e9' and b.get('owner')==R.name
        and b.get('provider')=='openai-codex' and b.get('model')=='gpt-6.1-sol' and b.get('route_verified') is True
        and b.get('mode')=='existing_invocation_recovery_only' and b.get('new_launch_authorized') is False
        and b.get('remaining_commands')==0 and b.get('read_only_admin_metadata_allowed') is True
        and b.get('receipt_sha256')==w.DIGEST and b.get('claim_sha256')==pin['claim_sha256']
        and b.get('native_pid')==pin['pid'] and b.get('native_start_ticks')==pin['start_ticks']
        and b.get('invocation')==pin['invocation'] and b.get('host_boot')==pin['boot_id'],
        'existing recovery binding/route/identity mismatch')
    return b

class ReadOnlyMetadata:
    """Existing sudo -n READS only; never launches worker/emulator as root."""
    def __init__(self,pin=PIN,*,binding_check=None,claim_path=None,lease=None):
        self.pin=dict(pin);self.binding_check=binding_check;self.claim_path=claim_path;self.lease=lease
    def guard(self,pid):
        p=self.pin;e.need(pid==p['pid'],'metadata wrong PID')
        check=authorize if self.binding_check is None else self.binding_check
        check(f.canonical(),os.environ.get('HERMES_SESSION_ID'),p)
        claim_path=R/'runtime-claim.json' if self.claim_path is None else self.claim_path
        e.need(e.sha(claim_path.read_bytes())==p['claim_sha256'],'original claim changed')
        e.need(Path('/proc/sys/kernel/random/boot_id').read_text().strip()==p['boot_id'],'host boot changed')
        proc=Path('/proc')/str(pid)
        e.need(int((proc/'stat').read_text().rsplit(')',1)[1].split()[19])==p['start_ticks'],'native start changed')
        e.need((proc/'cgroup').read_text().strip()=='0::'+p['cgroup'],'native cgroup changed')
        q=subprocess.run(['systemctl','--user','show',p['unit'],'--no-pager','--property=InvocationID,ControlGroup,Restart'],capture_output=True,text=True,check=True)
        props=dict(line.split('=',1) for line in q.stdout.splitlines() if '=' in line)
        e.need(props.get('InvocationID')==p['invocation'] and props.get('ControlGroup')==p['cgroup'] and props.get('Restart')=='no','unit invocation changed')
        return proc
    def sudo_read(self,pid,args):
        self.guard(pid)
        p=subprocess.run(['sudo','-n','--',*args],capture_output=True)
        e.need(p.returncode==0,'authorized metadata read failed: '+repr(args)+': '+p.stderr.decode(errors='replace'))
        # Recheck public boot/start/invocation after the privileged read as well.
        self.guard(pid)
        return p.stdout
    def read(self,pid,name):
        e.need(name in ('status','maps','auxv','environ'),'metadata proc path outside allowlist')
        proc=self.guard(pid)
        try:raw=(proc/name).read_bytes()
        except PermissionError:raw=self.sudo_read(pid,['/usr/bin/cat',str(proc/name)])
        if name=='environ':
            allowed={'DISPLAY','SDL_VIDEO_DRIVER','SDL_VIDEODRIVER','WAYLAND_DISPLAY','XAUTHORITY','XDG_RUNTIME_DIR','LIBGL_ALWAYS_SOFTWARE','GALLIUM_DRIVER','VK_ICD_FILENAMES','VK_DRIVER_FILES','MESA_LOADER_DRIVER_OVERRIDE'}
            raw=b'\0'.join(x for x in raw.split(b'\0') if x.split(b'=',1)[0].decode(errors='replace') in allowed)+b'\0'
        return raw
    def fds(self,pid):
        self.guard(pid)
        # A narrowly bound reader of THIS native's symlinks, never file contents.
        code="import os,json; p='/proc/"+str(self.pin['pid'])+"/fd'; print(json.dumps({n:os.readlink(p+'/'+n) for n in os.listdir(p)}))"
        return json.loads(self.sudo_read(pid,['/usr/bin/python3','-c',code]))
    def native(self,pid):
        proc=self.guard(pid)
        exe=self.sudo_read(pid,['/usr/bin/readlink',str(proc/'exe')]).decode().strip()
        digest=self.sudo_read(pid,['/usr/bin/sha256sum',str(proc/'exe')]).decode().split()[0]
        argv=(proc/'cmdline').read_bytes().decode().split('\0')[:-1]
        lease=w.receipt() if self.lease is None else self.lease
        e.need(exe==str(w.GUEST/'xemu') and digest==lease['xemu_sha256'],'native executable mismatch')
        return dict(pid=pid,start_ticks=self.pin['start_ticks'],boot_id=self.pin['boot_id'],native_exe=exe,native_sha256=digest,argv=argv)
    def endpoint(self,target,pid,unix=False):
        if unix:
            matches={fd:t for fd,t in self.fds(pid).items() if t=='socket:['+self.pin['socket_inode']+']'}
            e.need(str(target)==str(w.GUEST/'runtime/qmp.sock') and matches,'native monitor socket inode mismatch')
            return dict(socket_inode=self.pin['socket_inode'],fds=matches)
        raw=self.sudo_read(pid,['/usr/bin/ss','-ltnpH','sport = :1242']).decode()
        rows=raw.splitlines()
        e.need(int(target)==1242 and len(rows)==1 and re.search(r'pid='+str(pid)+r',',rows[0]) and '127.0.0.1:1242' in rows[0],'RSP endpoint owner mismatch')
        return rows[0]

class RecoveryEffects(f.LiveEffects):
    def __init__(self):
        # Intentionally not super(): original initializer is a cold-boot path.
        self.lease=w.receipt();self.env=w.environment(self.lease)
        self.meta=ReadOnlyMetadata();a.METADATA=self.meta
        a.EVIDENCE_PREFIX='continuation-2/recovery/';f.OUT=OUT
        self.ident=None;self.claimed=True;self.j=None;self.capture_j=None;self.handoff=False;self.q_attempted=False
        self.pin=PIN;self.launcher_pin=(2615602,19255630);self.evidence_root=R/'continuation-2/recovery'
        self.plan=e.prepare()
        self.layout=json.loads((R/'continuation-2/capture-abi/layout.json').read_text())
        e.need(self.layout['elf_sha256']==e.HASHES['elf'],'saved capture ABI wrong ELF')
        self.pre=None;self.unit_cgroup=None
    def launch(self):raise RuntimeError('existing mode can never launch')
    def existing(self):
        authorize(f.canonical(),os.environ.get('HERMES_SESSION_ID'))
        raw=(R/'runtime-claim.json').read_bytes();e.need(e.sha(raw)==PIN['claim_sha256'],'original claim changed')
        claim=json.loads(raw);handle=json.loads((R/'continuation-2/live/launch-handle.json').read_text())
        e.need(handle['invocation_id']==PIN['invocation'] and handle['unit']==PIN['unit'] and handle['claim_sha256']==PIN['claim_sha256'],'existing handle mismatch')
        e.need(claim['receipt_sha256']==w.DIGEST and claim['binding']['session']==os.environ.get('HERMES_SESSION_ID'),'claim session/receipt mismatch')
        self.pre=json.loads((R/'continuation-2/preflight.json').read_text())
        e.need(self.pre==claim['stopped_proof'],'stored preflight differs from immutable claimed proof')
        e.need(self.pre['live_headers']['E:/TDATA/4d530064/$u/default.xbe']==self.plan['live_header'],'stored TU header differs from frozen')
        # No disk preflight, roqfatx, qemu-img, claim or launch here.
        self.ident=self.meta.native(PIN['pid']);a.save(OUT+'native-identity.json',self.ident)
        return handle,self.ident
    def endpoint(self,target,pid,unix=False):return self.meta.endpoint(target,pid,unix)
    def open_q(self):
        self.q_attempted=True
        pin=getattr(self,'pin',PIN)
        self.meta.guard(pin['pid'])
        return a.open_qmp(self.lease['socket'],expected_peer=(pin['pid'],1000,1000))
    def cleanup_if_unopened(self):
        if self.q_attempted:return dict(attempted=False,reason='original pair already attempted; no retry')
        ident=self.meta.native(getattr(self,'pin',PIN)['pid']);self.endpoint(self.lease['socket'],ident['pid'],unix=True)
        q=self.open_q()
        try:
            self.reauthenticate(ident);q.cmd('quit')
            return dict(attempted=True,authenticated=True,method='QMP quit')
        finally:a.close_q(q)
    def ui(self,*args):
        self.meta.guard(self.pin['pid'])
        env=dict(self.env,LD_LIBRARY_PATH='/home/roasted/.local/lib');xd='/home/roasted/.local/bin/xdotool'
        def cmd(*argv):return subprocess.check_output(argv,env=env,text=True).strip()
        e.need(int(cmd(xd,'getwindowpid',self.window))==self.pin['pid'],'UI PID changed')
        if args[0]=='shot':
            prefix=f.OUT if self.evidence_root.name=='post-entry-47' else OUT
            path=R/prefix/args[1];e.need(path.parent==R/prefix,'UI output outside owned evidence')
            subprocess.run(['import','-display',':2','-window',self.window,str(path)],env=env,check=True)
        elif args[0]=='key':
            cmd(xd,'windowactivate','--sync',self.window);cmd(xd,'windowfocus','--sync',self.window)
            e.need(cmd(xd,'getwindowfocus')==self.window,'UI focus mismatch')
            for key in args[1:]:
                e.need(key in ('Up','Down','Left','Right','a','b','Return'),'unsupported UI key')
                cmd(xd,'keydown',key);time.sleep(.1);cmd(xd,'keyup',key);time.sleep(.8)
        else:raise ValueError('unsupported UI action')
    def review_dashboard(self,ident):
        prefix=f.OUT if self.evidence_root.name=='post-entry-47' else OUT
        path=R/prefix/'dashboard-before.png';digest=e.sha(path.read_bytes())
        a.save(prefix+'dashboard-review-ready.json',dict(identity=ident,sha256=digest,window=self.window,route='one Down -> parent retail Halo 2 row; never debug child'))
        deadline=time.monotonic()+240
        while time.monotonic()<deadline:
            decision=self.evidence_root/'navigation-reviewed.json'
            if decision.exists():
                d=json.loads(decision.read_text())
                e.need(d.get('sha256')==digest and d.get('native_pid')==ident['pid'] and d.get('start_ticks')==ident['start_ticks'] and d.get('retail_parent_row_verified') is True,'dashboard review stale/wrong')
                return
            time.sleep(.25)
        raise RuntimeError('no reviewed dashboard; authenticated cleanup without navigation')
    def verify_release(self):
        end=time.monotonic()+20
        while True:
            alive=[]
            for pid,start in ((self.pin['pid'],self.pin['start_ticks']),self.launcher_pin):
                try:
                    if int(Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split()[19])==start:alive.append(pid)
                except FileNotFoundError:pass
            unit=subprocess.run(['systemctl','--user','show',self.pin['unit'],'--no-pager','--property=ActiveState,SubState,MainPID,ControlGroup'],capture_output=True,text=True).stdout
            unix=subprocess.run(['ss','-xlpnH'],capture_output=True,text=True,check=True).stdout
            unix=[line for line in unix.splitlines() if self.lease['socket'] in line]
            tcp=subprocess.run(['ss','-ltnpH','sport = :1242'],capture_output=True,text=True,check=True).stdout
            released=not alive and not unix and not tcp and 'ActiveState=active' not in unit and 'ActiveState=activating' not in unit
            result=dict(released=released,owned_alive_pids=alive,unit=unit,qmp_listeners=unix,rsp=tcp,
                disk_usb_fds_released_by_verified_owned_process_exit=not alive,claim_sha256=e.sha((self.evidence_root/'runtime-claim.json' if self.evidence_root.name=='post-entry-47' else R/'runtime-claim.json').read_bytes()))
            if released or time.monotonic()>=end:return result
            time.sleep(.2)
    def record(self,result):
        if self.capture_j is not None:self.capture_j.close();self.capture_j=None
        a.save(OUT+'session-result.json',result)
        path=R/'continuation-2/recovery/status.json';d=json.loads(path.read_text())
        d.update(phase='existing_session_finished',result=result,cleanup_complete=result.get('remaining_resources',{}).get('released',False))
        a.save('continuation-2/recovery/status.json',d)

def fresh_candidate(lease,handle,props,records,boot_id):
    """Public unit/cgroup discovery BEFORE any privileged process observation."""
    e.need(props.get('Id')==lease['unit'] and props.get('InvocationID')==handle['invocation_id']
           and handle['unit']==lease['unit'] and props.get('Restart')=='no','fresh unit/invocation mismatch')
    cg=props.get('ControlGroup','')
    e.need(cg.endswith('/'+lease['unit']),'fresh cgroup is not exact leased unit')
    found=[]
    for row in records:
        args=row['argv']
        if args and args[0]==str(w.GUEST/'xemu'):
            e.need(row['cgroup']=='0::'+cg and row['boot_id']==boot_id,'fresh native cgroup/boot mismatch')
            e.need('-config_path' in args and args[args.index('-config_path')+1]==str(w.GUEST/'xemu.toml'),'fresh config mismatch')
            e.need('-qmp' in args and args[args.index('-qmp')+1]=='unix:'+lease['socket']+',server=on,wait=off','fresh monitor argv mismatch')
            e.need(row['pid']>0 and row['start_ticks']>0,'fresh PID/start absent')
            found.append(row)
    e.need(len(found)<=1,'multiple natives in leased invocation')
    return found[0] if found else None

class FreshEffects(RecoveryEffects):
    """Fresh receipt adapter over the retained W45 state machine, not a manager."""
    def __init__(self):
        self.lease=w.receipt47();self.env=w.environment(self.lease)
        self.evidence_root=w.FRESH;self.pin=None;self.meta=None;self.launcher_pin=None
        self.ident=None;self.claimed=False;self.j=None;self.capture_j=None;self.handoff=False;self.q_attempted=False
        self.pre=None;self.unit_cgroup=None;self.plan=e.prepare()
        self.layout=json.loads((R/'continuation-2/capture-abi/layout.json').read_text())
        e.need(self.layout['elf_sha256']==e.HASHES['elf'],'saved ABI wrong ELF')
        a.METADATA=None;a.EVIDENCE_PREFIX='post-entry-47/';f.OUT='post-entry-47/live/'
    def launch(self):
        def gates(lease,env):
            self.pre=f.preflight.stopped_gates(lease,env,require_tests=False,claim_path=lease['claim_path'],evidence='post-entry-47')
            return self.pre
        try:
            return w.launch(self.lease,self.env,gates=gates,bind=w.authority47,
                claim_path=Path(self.lease['claim_path']),output=self.evidence_root/'live',digest=w.DIGEST47)
        finally:self.claimed=Path(self.lease['claim_path']).exists()
    def existing(self):raise ValueError('fresh path is not historical recovery')
    def discover(self,handle):
        end=time.monotonic()+45
        while time.monotonic()<end:
            p=f.run(['systemctl','--user','show',self.lease['unit'],'--no-pager',
                     '--property=Id,InvocationID,ControlGroup,MainPID,Restart,ActiveState,SubState'])
            props=dict(line.split('=',1) for line in p.stdout.splitlines() if '=' in line)
            e.need(p.returncode==0 and props.get('Id')==self.lease['unit'] and props.get('InvocationID')==handle['invocation_id'],'fresh unit discovery mismatch')
            cg=props.get('ControlGroup','');records=[]
            boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
            if cg:
                for value in (Path('/sys/fs/cgroup')/cg.lstrip('/')/'cgroup.procs').read_text().split():
                    proc=Path('/proc')/value
                    try:
                        records.append(dict(pid=int(value),start_ticks=int((proc/'stat').read_text().rsplit(')',1)[1].split()[19]),
                            argv=(proc/'cmdline').read_bytes().decode().split('\0')[:-1],
                            cgroup=(proc/'cgroup').read_text().strip(),boot_id=boot))
                    except FileNotFoundError:pass
            row=fresh_candidate(self.lease,handle,props,records,boot) if cg else None
            sockets=[line.split()[6] for line in Path('/proc/net/unix').read_text().splitlines()
                     if len(line.split())>=8 and line.split()[7]==self.lease['socket']]
            if row and len(sockets)==1:
                claim=Path(self.lease['claim_path'])
                e.need(e.sha(claim.read_bytes())==handle['claim_sha256'],'fresh claim/handle mismatch')
                self.pin=dict(pid=row['pid'],start_ticks=row['start_ticks'],boot_id=boot,unit=self.lease['unit'],
                    invocation=handle['invocation_id'],cgroup=cg,socket_inode=sockets[0],claim_sha256=handle['claim_sha256'])
                main=int(props['MainPID']);launcher=next(x for x in records if x['pid']==main)
                self.launcher_pin=(main,launcher['start_ticks'])
                def binding(c,session,pin):
                    b=w.authority47(self.lease,canonical=c,session=session,consumed=True)
                    e.need(b.get('read_only_admin_metadata_allowed') is True,'fresh scoped metadata not authorized')
                    e.need(pin['unit']==self.lease['unit'] and pin['invocation']==handle['invocation_id'],'fresh metadata unit changed')
                    for field,key in (('native_pid','pid'),('native_start_ticks','start_ticks'),('invocation','invocation')):
                        if field in b:e.need(b[field]==pin[key],'canonical native binding changed '+field)
                self.meta=ReadOnlyMetadata(self.pin,binding_check=binding,claim_path=claim,lease=self.lease)
                a.METADATA=self.meta
                # guard revalidates public PID/start/unit before this first sudo.
                self.ident=self.meta.native(row['pid'])
                a.save(f.OUT+'first-native-discovery.json',dict(identity=self.ident,pin=self.pin,properties=props,launcher=self.launcher_pin))
                a.save(f.OUT+'native-identity.json',self.ident)
                return self.ident
            if props.get('ActiveState') in ('inactive','failed'):return None
            time.sleep(.2)
        raise RuntimeError('fresh native discovery bound reached; no inherited PID or blind monitor interaction')
    def cleanup_if_unopened(self):
        if self.meta is None:return dict(attempted=False,reason='no authenticated fresh native binding')
        return super().cleanup_if_unopened()
    def verify_release(self):
        if self.pin is not None:return super().verify_release()
        inventory=f.preflight.resources(self.lease)
        inventory['released']=not any(inventory[k] for k in ('processes','disk_fds','tcp','qmp_listeners')) and 'ActiveState=active' not in inventory['unit']
        return inventory
    def record(self,result):
        if self.capture_j is not None:self.capture_j.close();self.capture_j=None
        a.save(f.OUT+'session-result.json',result)
        path=self.evidence_root/'status.json';d=json.loads(path.read_text())
        d.update(phase='phase2_finished' if self.claimed else 'unspent_gate_refusal',new_commands_used=int(self.claimed),result=result)
        a.save('post-entry-47/status.json',d)
