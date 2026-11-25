#!/usr/bin/env python3
"""OS/protocol effects for the W45 production session. No launch on import."""
import sys
sys.dont_write_bytecode=True
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import threading
import time
import live_adapter as a
import enum_watch as e
import live_preflight as preflight
import capture_layout
sys.path.insert(0,str(a.ROOT))
import parent_launch as launch
R=a.ROOT
OUT='continuation-2/live/'

def run(cmd,**kw):
    return subprocess.run(cmd,capture_output=True,text=True,**kw)

def canonical():
    return json.loads((R.parent/'sol-audit/COORDINATOR_STATE.json').read_text())

class LiveEffects:
    def __init__(self):
        self.lease=launch.receipt();self.env=launch.environment(self.lease)
        self.ident=None;self.claimed=False;self.j=None;self.capture_j=None;self.handoff=False
        self.plan=e.prepare();self.layout=capture_layout.prepare()
        self.pre=None;self.unit_cgroup=None
    def launch(self):
        def gates(lease,env):
            self.pre=preflight.stopped_gates(lease,env)
            return self.pre
        try:return launch.launch(self.lease,self.env,gates=gates)
        finally:self.claimed=(R/'runtime-claim.json').exists()
    def discover(self,handle):
        deadline=time.monotonic()+45
        while time.monotonic()<deadline:
            pid=__import__('runtime_session').owned_pid(Path(self.lease['fresh_clone']))
            if pid is not None:
                self.ident=a.native(pid)
                a.save(OUT+'native-identity.json',self.ident)
                return self.ident
            props=run(['systemctl','--user','show',self.lease['unit'],'--property=ActiveState,SubState','--no-pager']).stdout
            if 'ActiveState=failed' in props or 'ActiveState=inactive' in props:
                inventory=preflight.resources(self.lease)
                a.save(OUT+'early-exit-inventory.json',inventory)
                e.need(not inventory['processes'],'surviving unidentified process; inactive unit is not exit proof')
                return None
            time.sleep(.25)
        inventory=preflight.resources(self.lease)
        a.save(OUT+'discovery-unresolved.json',inventory)
        e.need(not inventory['processes'],'surviving unidentified process; no blind endpoint interaction')
        return None
    def authenticate(self,ident,handle):
        a.check_native(ident,self.lease)
        p=run(['systemctl','--user','show',self.lease['unit'],
               '--property=InvocationID,ControlGroup,Restart','--no-pager'])
        props=dict(l.split('=',1) for l in p.stdout.splitlines() if '=' in l)
        e.need(props.get('InvocationID')==handle['invocation_id'] and props.get('Restart')=='no','unit invocation/restart changed')
        cg=props.get('ControlGroup');e.need(bool(cg),'missing cgroup')
        proc=Path('/proc')/str(ident['pid'])
        e.need('0::'+cg in (proc/'cgroup').read_text().splitlines(),'native outside exact cgroup')
        self.unit_cgroup=cg
        deadline=time.monotonic()+10
        while not Path(self.lease['socket']).is_socket() and time.monotonic()<deadline:time.sleep(.1)
        e.need(Path(self.lease['socket']).is_socket(),'QMP missing while native survives')
        self.endpoint(self.lease['socket'],ident['pid'],unix=True)
        e.need(e.sha((Path(self.lease['fresh_clone'])/'xemu.toml').read_bytes())==self.lease['identities']['config']['sha256'],'config changed')
        fds=a.process_fds(ident['pid'])
        e.need(self.lease['identities']['hdd_path']['path'] in fds,'native disk FD not verified')
        a.save(OUT+'endpoint-authentication.json',dict(identity=ident,properties=props,fds=fds))
    def endpoint(self,target,pid,unix=False):
        p=run(['ss','-xlpnH'] if unix else ['ss','-ltnpH','sport = :1242'])
        lines=[l for l in p.stdout.splitlines() if (str(target) in l if unix else True)]
        e.need(p.returncode==0 and len(lines)==1 and re.search(r'pid='+str(pid)+r',',lines[0]),'endpoint owner unknown/mismatched')
        return lines[0]
    def open_q(self):return a.open_qmp(self.lease['socket'])
    def parity(self,ident,handle):
        proc=Path('/proc')/str(ident['pid']);evidence=dict(identity=ident)
        try:
            status=a.process_bytes(ident['pid'],'status').decode();maps=a.process_bytes(ident['pid'],'maps').decode()
            aux=a.process_bytes(ident['pid'],'auxv');auxv=dict(struct.iter_unpack('QQ',aux))
            env=dict(x.split('=',1) for x in a.process_bytes(ident['pid'],'environ').decode().split('\0') if '=' in x)
            sdl=sorted({l.split()[-1] for l in maps.splitlines() if 'libSDL3.so' in l})
            e.need(len(sdl)==1,'loaded SDL unknown')
            fixture=json.loads((R/'PARENT-RESULT-INTAKE.json').read_text())['display_fixture_reexecuted']['stdout']
            e.need(e.sha(Path(sdl[0]).read_bytes())==fixture['sdl_sha256'],'loaded SDL differs from fixture')
            caps={k:v.strip() for k,v in (l.split(':',1) for l in status.splitlines() if ':' in l) if k.startswith('Cap') or k in ('Uid','Gid','NoNewPrivs')}
            # Helper has CAP_NET_RAW only; no stronger native capability allowed.
            for name in ('CapEff','CapPrm','CapAmb'):
                e.need(int(caps[name],16)&~0x2000==0,'unexpected native capabilities')
            e.need(auxv.get(23) in (0,1),'AT_SECURE unknown')
            e.need(env.get('DISPLAY')==':2' and env.get('SDL_VIDEO_DRIVER')=='x11' and 'XAUTHORITY' not in env,'effective native X11 environment mismatch')
            self.ui_ident(ident)
            journal=run(['journalctl','--user','_SYSTEMD_INVOCATION_ID='+handle['invocation_id'],'--no-pager','-o','json'])
            rows=[json.loads(l) for l in journal.stdout.splitlines()]
            text='\n'.join(str(x.get('MESSAGE','')) for x in rows)
            selected=re.findall(r'Selected physical device: ([^\n]+)',text)
            e.need(selected and ('RX 580' in selected[-1] or 'RX580' in selected[-1]) and 'RADV' in selected[-1].upper(),'selected hardware RX580 RADV Vulkan device unverified')
            e.need('llvmpipe' not in selected[-1].lower() and 'lavapipe' not in selected[-1].lower(),'software Vulkan refused')
            evidence.update(status=status,capabilities=caps,at_secure=auxv[23],sdl=sdl,
                effective_env={k:env.get(k) for k in ('DISPLAY','SDL_VIDEO_DRIVER','WAYLAND_DISPLAY','XAUTHORITY')},
                selected_device=selected[-1],journal=rows,passed=True)
        finally:a.save(OUT+'native-parity.json',evidence)
    def ui_ident(self,ident):
        env=dict(self.env,LD_LIBRARY_PATH='/home/roasted/.local/lib')
        xd='/home/roasted/.local/bin/xdotool'
        p=run([xd,'search','--name','xemu'],env=env);wins=[]
        for w in p.stdout.split():
            if run([xd,'getwindowpid',w],env=env).stdout.strip()==str(ident['pid']):wins.append(w)
        e.need(len(wins)==1,'PID-bound X11 window missing/ambiguous')
        self.window=wins[0]
        a.save(OUT+'window.json',dict(pid=ident['pid'],window=self.window,display=':2',xauthority_present='XAUTHORITY' in env))
    def ui(self,*args):
        p=run([sys.executable,'-B',str(R/'tools/ui.py'),*args])
        e.need(p.returncode==0,'owned UI failed: '+p.stderr)
        return p.stdout
    def open_r(self,q,ident):
        response=q.hmp('gdbserver tcp:127.0.0.1:1242');e.need('Error' not in response,response)
        self.endpoint(1242,ident['pid'])
        r=a.open_rsp(1242)
        try:
            r.reason();a.save(OUT+'register-schema.json',a.register_schema(r))
        except BaseException:r.close();raise
        return r
    def load_title(self,q,r,ident):
        # Establish dashboard before the one normal retail-row selection. CPU is
        # resumed only before the generic loader breakpoint is relevant.
        r.cont();time.sleep(5);r.stop();self.ui('shot','dashboard-before.png')
        if hasattr(self,'review_dashboard'):self.review_dashboard(ident)
        a.save(OUT+'load-hold.json',a.arm_load_hold(r))
        ui_errors=[]
        def select():
            try:
                time.sleep(.5);self.ui('key','Down','a')  # parent retail row; NOT Down x3/debug child
            except Exception as error:ui_errors.append(str(error))
        nav=threading.Thread(target=select);nav.start()
        hits=[]
        try:
            for index in range(4):
                why=r.continue_wait(90)
                e.need(not ui_errors,'retail navigation failed '+repr(ui_errors))
                decision=a.dispatch_entry(r,self.pre['live_headers']['E:/DEVKIT/Tools/Halo2/default.xbe'])
                hits.append(dict(stop=why,decision=decision));a.save(OUT+'entry-hits.json',hits)
                if decision['kind']=='tu803':
                    a.save(OUT+'entry-verified.json',dict(identity=ident,generic_hold_retired=not getattr(r,'_w45_load_hold_armed',False),**a.check_entry(r)))
                    return
                a.disarm_load_hold(r);r.step();a.arm_load_hold(r)
            raise RuntimeError('retail parent row did not resolve exact TU')
        finally:
            nav.join(timeout=5)
            a.disarm_load_hold(r)
    def install(self,q,r,ident):
        rec=a.allocate(r,ident);install=a.install(r,rec)
        ident.update(base=rec['base'],module=install['module'],elf_sha256=e.HASHES['elf'],layout_sha256=e.HASHES['layout'])
        pad=Path(self.pre['usb'][0]['sysfs'])
        e.need((pad/'idVendor').read_text().strip()=='045e' and (pad/'idProduct').read_text().strip()=='0b12','pad identity changed')
        bus=int((pad/'busnum').read_text());addr=int((pad/'devnum').read_text())
        before=q.hmp('info usb');tree=q.hmp('info qtree')
        e.need('1.4' not in before and 'pt_pad3' not in tree,'passthrough slot collision')
        q.cmd('device_add',driver='usb-host',id='pt_pad3',bus='usb-bus.1',port='1.4',hostbus=bus,hostaddr=addr,vendorid=0x045e,productid=0x0b12)
        after=q.hmp('info usb');tree=q.hmp('info qtree')
        a.save(OUT+'usb-topology.json',dict(before=before,after=after,qtree=tree,bus=bus,address=addr,sysfs=str(pad)))
        e.need('pt_pad3' in tree and ('12 Mb/s' in after or '12 Mb' in after),'pad device/speed/topology unverified')
        a.check_native(ident,self.lease);a.check_entry(r)
    def observe(self,q,r,ident):
        self.j=e.Journal(R/OUT/'ordered-trace.jsonl')
        try:return e.observe(r,self.plan,ident,dict(a.check_native(ident,self.lease),elf_sha256=e.HASHES['elf'],layout_sha256=e.HASHES['layout']),self.j)
        finally:self.j.close();self.j=None
    def context(self,r):
        g=r.regs();a.save(OUT+'final-context.json',dict(regs=g,raw_g=r.raw_regs(),stack=r.read(g['esp'],128).hex(),code=r.read(max(g['eip']-16,0),64).hex()))
    def reauthenticate(self,ident):
        a.check_native(ident,self.lease);self.endpoint(self.lease['socket'],ident['pid'],unix=True)
    def verify_release(self):
        end=time.monotonic()+20 if self.claimed else time.monotonic()
        while True:
            inventory=preflight.resources(self.lease)
            inventory['released']=not any(inventory[k] for k in ('processes','disk_fds','tcp','qmp_listeners')) and ('ActiveState=active' not in inventory['unit'] and 'ActiveState=activating' not in inventory['unit'])
            if inventory['released'] or time.monotonic()>=end:return inventory
            time.sleep(.2)
    def record(self,result):
        if self.capture_j is not None:self.capture_j.close();self.capture_j=None
        a.save(OUT+'session-result.json',result)
        p=R/'continuation-2/status.json';d=json.loads(p.read_text())
        d.update(phase='runtime_finished' if self.claimed else 'offline_gate_refused',launch_commands_used=int(self.claimed),
                 observed_title_boots=int(result['title']),result=result)
        a.save('continuation-2/status.json',d)
    def capture(self,q,r,ident,handle):
        self.r=r;self.q=q;self.capture_ident=dict(ident)
        self.decoder=e.CaptureDecoder(self.layout)
        self.capture_j=e.Journal(R/OUT/'capture.jsonl',max_events=None)
        baseline=r.read(ident['module'],self.layout['values']['module_size'])
        self.capture_j.emit('capture_baseline',identity=ident,raw_module=baseline.hex(),decoded=self.decoder.decode(baseline))
        self.last_cpu=[];self.frame_hashes=[]
        # Repeated actual title execution and synchronized visible native-pad UI
        # exercise. Neither synthetic UI nor zero physical RX qualifies input.
        for index in range(3):self.capture_tick(index,navigate=index==1)
        e.need(len(set(self.last_cpu))>=2,'CPU progress not observed')
        e.need(len(set(self.frame_hashes))>=2,'responsive moving menu not observed')
        offer=dict(identity=dict(ident),unit=self.lease['unit'],invocation_id=handle['invocation_id'],
                   qmp=self.lease['socket'],gdb_port=1242,running=False,
                   capture=dict(path=str(R/OUT/'capture.jsonl'),next_seq=self.capture_j.seq+1,
                                ring_head=self.decoder.head,layout=str(R/'continuation-2/capture-abi/layout.json')),
                   cleanup_owner='Originating Discord coordinator',remaining_commands=0,
                   physical_input='untested',menu_confirmation_required=True)
        a.save(OUT+'takeover-offer.json',offer)
        return offer
    def capture_tick(self,index,navigate=False):
        r=self.r;ident=self.capture_ident
        a.check_native(ident,self.lease)
        a.loader.Pins().verify_header(r)
        nav=None;errors=[]
        if navigate:
            def action():
                try:time.sleep(.1);self.ui('key','Down','Up')
                except Exception as error:errors.append(str(error))
            nav=threading.Thread(target=action);nav.start()
        try:self.capture_interval(2 if navigate else 1)
        finally:
            if nav:nav.join(timeout=5)
        e.need(not errors,'visible action delivery failed '+repr(errors))
        g=r.regs();code=r.read(max(0,g['eip']-8),24)
        e.need(0x10000<=g['eip']<0x80000000 and b'\xf4' not in code and b'\x0f\x0b' not in code,'exception/reboot/HLT or unknown CPU health')
        a.loader.Pins().verify_header(r)
        blob=r.read(ident['module'],self.layout['values']['module_size'])
        decoded=self.decoder.decode(blob)
        name=f'capture-{index:08d}.png';self.ui('shot',name)
        pixel=e.sha((R/OUT/name).read_bytes())
        self.last_cpu.append(g['eip']);self.frame_hashes.append(pixel)
        self.capture_j.emit('synchronized_capture',identity=ident,regs=g,decoded=decoded,
                            raw_module=blob.hex(),visible=dict(path=name,sha256=pixel,native_ui_exercise=navigate),
                            interval='same stop; physical button untested')
    def capture_interval(self,seconds):
        """One owner: raw head write-watch + validated GetState entry/return.

        Every stop is decoded before stepping, including watches during steps.
        This does not write guest state, inject input, or infer returned packets
        from a counter. Dynamic return points are authenticated against the
        frozen TU/module instruction map before being armed.
        """
        r=self.r;ident=self.capture_ident;v=self.layout['values'];module=ident['module']
        entry=ident['base']+self.plan['symbols']['ogx_XInputGetState']
        extent=next(p for p in self.plan['module'] if p==entry-ident['base'])
        expected=bytes.fromhex(self.plan['module'][extent]['bytes'])
        e.need(r.read(entry,len(expected))==expected,'GetState capture entry mismatch')
        head=module+v['ring_head'];armed=set();pending=None
        def command(kind,addr,insert=True):
            e.need(r.cmd(f'{"Z" if insert else "z"}{kind},{addr:x},{4 if kind==2 else 1:x}')=='OK','capture arm/remove refused')
            if insert:armed.add((kind,addr))
            else:armed.discard((kind,addr))
        def decode(why):
            nonlocal pending
            a.loader.Pins().verify_header(r)
            g=r.regs();pc=g['eip'];returned=None
            if pending is not None and pc==pending['return']:
                returned=dict(status=g['eax'],virtual_port=1,packet=r.read(pending['output'],22).hex(),
                              handle=pending['handle'],call_return=pc)
                command(0,pc,False);pending=None
            elif pc==entry:
                stack=struct.unpack('<4I',r.read(g['esp'],16));ret,ctx,handle,out=stack
                if ctx==module+v['present'] and module+v['vh']<=handle<module+v['vh']+16*v['vh_size'] and (handle-module-v['vh'])%v['vh_size']==0:
                    h=struct.unpack('<4I',r.read(handle,16))
                    if h[0]==0x4a414b31 and h[2]==1 and h[3]==1:
                        e.need(pending is None,'overlapping GetState return; provenance unknown')
                        pins=a.loader.Pins()
                        # Return must be a known instruction boundary; byte
                        # comparison is not allowed to validate a mid-instruction.
                        if ident['base']<=ret<ident['base']+len(bytes.fromhex(self.plan['text'])):
                            off=ret-ident['base'];e.need(off in self.plan['module'],'unknown module return boundary')
                            b=bytes.fromhex(self.plan['module'][off]['bytes'])
                        else:
                            e.need(ret in self.plan['stock'],'unknown title return boundary')
                            b=pins.read(ret,len(bytes.fromhex(self.plan['stock'][ret]['bytes'])))
                        e.need(r.read(ret,len(b))==b,'GetState caller return bytes mismatch')
                        pending=dict(return_=ret,output=out,handle=handle);pending['return']=ret
                        command(0,ret)
            elif 'watch:' not in why:
                raise RuntimeError('unclassified capture stop; retained safety hold')
            blob=r.read(module,v['module_size']);decoded=self.decoder.decode(blob,returned=returned)
            self.capture_j.emit('capture_stop',reason=why,identity=ident,regs=g,raw_module=blob.hex(),decoded=decoded)
            return pc
        try:
            command(0,entry);command(2,head)
            end=time.monotonic()+seconds
            for _ in range(1024):
                if time.monotonic()>=end:break
                try:why=r.continue_wait(min(.5,max(.01,end-time.monotonic())))
                except TimeoutError:continue  # upstream already interrupted
                pc=decode(why)
                if (0,pc) in armed:
                    command(0,pc,False);step=r.step()
                    if 'watch:' in step:decode(step)
                    if pc==entry:command(0,pc)
            else:raise RuntimeError('capture stop bound; unknown progression')
            e.need(pending is None,'capture ended before authenticated GetState return')
        finally:
            for kind,addr in list(armed):command(kind,addr,False)
    def accept(self,offer):
        # Untimed inspection while recorder remains owned and exercisable. No
        # marker-file authority and no automatic accepted-health lifetime cutoff.
        index=3
        while True:
            c=canonical();binding=c.get('runtime_binding',{})
            if c.get('owner_hold') is not False:return None
            decision=binding.get('takeover',{})
            if decision.get('accepted') is False:return None
            if decision.get('accepted') is True:
                e.need(decision.get('responsive_menu_confirmed') is True,'parent did not verify moving responsive menu')
                return decision
            self.capture_tick(index);index+=1
    def seal(self,offer):
        self.checkpoint=self.capture_j.emit('outgoing_checkpoint',offer_sha256=e.sha(json.dumps(offer,sort_keys=True).encode()),
                            last_ring_head=self.decoder.head,run_state='paused')
        self.capture_j.close();self.capture_j=None
    def release(self,offer):
        # Socket peers no longer exist; parent must acquire only after this file.
        a.save(OUT+'clients-released.json',dict(offer_sha256=e.sha(json.dumps(offer,sort_keys=True).encode()),
                                               identity=offer['identity'],clients_closed=True,checkpoint=self.checkpoint))
    def continue_after_takeover(self,offer,checkpoint,q,r):
        """Parent receiver: existing new pair only, after outgoing release.

        Never launches a guest or issues gdbserver. Parent retains these clients,
        untimed recorder and cleanup duty; use capture_tick for further samples.
        Caller owns pair cleanup if authentication/continuation raises.
        """
        from runtime_session import validate_takeover
        state=canonical();decision=state.get('runtime_binding',{}).get('takeover',{})
        validate_takeover(offer,decision)
        e.need(state.get('owner_hold') is False and decision.get('responsive_menu_confirmed') is True,'parent health/ownership not accepted')
        released=json.loads((R/OUT/'clients-released.json').read_text())
        digest=e.sha(json.dumps(offer,sort_keys=True).encode())
        e.need(released.get('offer_sha256')==digest and released.get('clients_closed') is True
               and released.get('checkpoint')==checkpoint and released.get('identity')==offer['identity'],'outgoing clients not released for exact checkpoint')
        ident=offer['identity'];a.check_native(ident,self.lease)
        self.endpoint(offer['qmp'],ident['pid'],unix=True);self.endpoint(offer['gdb_port'],ident['pid'])
        e.need(q.cmd('query-status')['running']==offer['running']==False,'takeover running state mismatch')
        a.register_schema(r);a.loader.Pins().verify_header(r);e.verify_pins(r,self.plan,ident['base'])
        self.r=r;self.q=q;self.capture_ident=dict(ident)
        self.decoder=e.CaptureDecoder(self.layout,head=checkpoint['last_ring_head'])
        self.capture_j=e.Journal.resume(R/OUT/'capture.jsonl',checkpoint)
        try:
            self.capture_interval(1)
            blob=r.read(ident['module'],self.layout['values']['module_size'])
            decoded=self.decoder.decode(blob)
            self.capture_j.emit('parent_continuity',identity=ident,offer_sha256=digest,
                                previous_ring_head=checkpoint['last_ring_head'],decoded=decoded,
                                raw_module=blob.hex(),run_state='paused')
        except BaseException:self.capture_j.close();self.capture_j=None;raise
        self.last_cpu=[];self.frame_hashes=[]
        return self
    def confirm(self,offer):
        while True:
            c=canonical();receipt=c.get('runtime_binding',{}).get('capture_continuity',{})
            if receipt.get('offer_sha256')==e.sha(json.dumps(offer,sort_keys=True).encode()):
                e.need(receipt.get('identity')==offer['identity'] and receipt.get('exclusive') is True,
                       'parent continuity identity mismatch')
                rows=[json.loads(l) for l in (R/OUT/'capture.jsonl').read_text().splitlines()]
                checkpoint=getattr(self,'checkpoint',None)
                e.need(checkpoint is not None,'continuity has no outgoing checkpoint')
                e.need(rows[-1].get('event')=='parent_continuity' and rows[-1].get('identity')==offer['identity']
                       and rows[-1].get('seq',0)>checkpoint['seq']
                       and [row['seq'] for row in rows]==list(range(1,len(rows)+1))
                       and rows[-1].get('previous_ring_head')==checkpoint['last_ring_head']
                       and rows[-1].get('offer_sha256')==receipt['offer_sha256']
                       and 'decoded' in rows[-1],
                       'same-boot recorder continuation absent')
                a.save(OUT+'takeover-confirmed.json',receipt);return
            if c.get('owner_hold') is not False:raise RuntimeError('parent hold after client release: accepted cleanup duty remains parent-owned')
            time.sleep(.5)
