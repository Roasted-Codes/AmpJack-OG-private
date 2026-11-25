#!/usr/bin/env python3
"""One authorized W45 cold boot -> same-client entry/load/observe/cleanup."""
import sys
sys.dont_write_bytecode=True
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback
import live_adapter as a
import enum_watch as e
R=a.ROOT

def status(**kw):
    p=R/'status.json'; d=json.loads(p.read_text());d.update(kw);a.save('status.json',d)

def owned_pid(guest):
    found=[]
    for p in Path('/proc').iterdir():
        if not p.name.isdigit():continue
        try:
            argv=(p/'cmdline').read_bytes().decode().split('\0')[:-1]
            if '-config_path' in argv and argv[argv.index('-config_path')+1]==str(guest/'xemu.toml'):
                if (p/'exe').resolve().name=='xemu':found.append(int(p.name))
        except OSError:pass
    e.need(len(found)<=1,'multiple native guest writers')
    return found[0] if found else None

def main():
    sys.path.insert(0,str(R))
    from parent_launch import receipt, authority
    lease=receipt();authority(lease);guest=Path(lease['fresh_clone'])
    e.need(lease['boot_launch_commands']==0,'boot already consumed')
    e.need(json.loads((R/'continuation/adapter-tests.json').read_text())['partial_arm_removed'],'adapter tests missing')
    plan=e.prepare()
    # Recheck administrative gates immediately before the one launch; no disk read after this.
    subprocess.run([sys.executable,'-B',str(R/'tools/live_preflight.py')],check=True,stdout=(R/'continuation/prelaunch-check.log').open('w'))
    pre=json.loads((R/'continuation/preflight.json').read_text())
    e.need(pre['hashes']['E:/TDATA/4d530064/$u/default.xbe']['sha256']==e.HASHES['xbe'],'chosen disk wrong title')
    subprocess.run([sys.executable,'-B',str(R/'parent_launch.py'),'--check'],check=True)
    status(phase='guarded_launch_requested_not_yet_claimed',boots_consumed=0,runtime_spent=False)
    subprocess.run([sys.executable,'-B',str(R/'parent_launch.py')],check=True)
    end=time.monotonic()+45;pid=None
    while time.monotonic()<end:
        pid=owned_pid(guest)
        if pid and Path(lease['socket']).is_socket():break
        time.sleep(.25)
    e.need(pid is not None,'native launch did not materialize')
    ident=a.native(pid);a.check_native(ident,lease)
    a.save('live/native-identity.json',dict(ident,lease=lease,config_sha256=e.sha((guest/'xemu.toml').read_bytes()),qmp=lease['socket'],gdb_port=1242,preflight=str(R/'continuation/preflight.json')))
    q=None;r=None;healthy=False;held=True;result={}
    try:
        q=a.QMP(lease['socket'],timeout=10)
        a.save('live/qmp-initial.json',dict(greeting=q.greeting,status=q.cmd('query-status'),qtree=q.hmp('info qtree'),usb=q.hmp('info usb')))
        response=q.hmp('gdbserver tcp:127.0.0.1:1242');e.need('Error' not in response,response)
        r=a.RSP(port=1242,timeout=10);r.reason()
        a.save('live/register-schema.json',a.register_schema(r))
        # Stops must precede XInitDevices; the guard is not the rejected main stop.
        bps=(0x2da9de,0x1273f4,0x4139a0,0x412d37)
        for b in bps:r.bp(b)
        a.save('live/armed-prelaunch.json',dict(identity=ident,breakpoints=[hex(x) for x in bps],port=1242,pad='attach at authenticated entry before first title instruction'))
        status(phase='waiting_for_normal_title_launch',qmp_rsp_connections_opened=2,native_pid=pid,native_start_ticks=ident['start_ticks'])
        print('READY: entry hold armed; normal dashboard navigation may proceed',flush=True)
        deadline=time.monotonic()+240;hits=[]
        while time.monotonic()<deadline:
            a.check_native(ident,lease)
            try:why=r.continue_wait(timeout=min(10,deadline-time.monotonic()))
            except TimeoutError:continue
            g=r.regs();ts=r.read(0x10114,4).hex();hit=dict(why=why,regs=g,title_ts=ts);hits.append(hit);a.save('live/entry-hits.json',hits)
            e.need(g['eip'] in bps,'unclassified pre-entry stop')
            if ts=='2ba60046':
                e.need(g['eip']==0x2da9de,'XInitDevices preceded entry hold')
                break
            r.bp(g['eip'],False);r.step();r.bp(g['eip'])
        else:raise RuntimeError('normal title navigation/entry timeout')
        for b in bps:r.bp(b,False)
        a.save('live/entry-verified.json',dict(a.check_entry(r),identity=ident,regs=r.regs()))
        status(phase='at_authenticated_preinit_entry',live_evidence=True)
        rec=a.allocate(r,ident)
        installation=a.install(r,rec)
        ident.update(base=rec['base'],module=installation['module'],elf_sha256=e.HASHES['elf'],layout_sha256=e.HASHES['layout'])
        # Rediscover physical identity immediately before passthrough; no stale hostaddr.
        pad=Path(pre['usb'][0]['sysfs']);e.need((pad/'idVendor').read_text().strip()=='045e' and (pad/'idProduct').read_text().strip()=='0b12','pad identity changed')
        hostbus=int((pad/'busnum').read_text());hostaddr=int((pad/'devnum').read_text())
        tree=q.hmp('info qtree');usb_before=q.hmp('info usb')
        e.need('1.4' not in usb_before,'intended direct port already occupied')
        q.cmd('device_add',driver='usb-host',id='pt_pad3',bus='usb-bus.1',port='1.4',hostbus=hostbus,hostaddr=hostaddr,vendorid=0x045e,productid=0x0b12)
        usb_after=q.hmp('info usb');a.save('live/usb-verified.json',dict(before=usb_before,after=usb_after,qtree=q.hmp('info qtree'),hostbus=hostbus,hostaddr=hostaddr,sysfs=str(pad)))
        e.need('12 Mb/s' in usb_after or '12 Mb' in usb_after,'real pad speed not verified')
        a.check_native(ident,lease);a.check_entry(r)
        actual=dict(a.check_native(ident,lease),elf_sha256=e.sha(e.ELF.read_bytes()),layout_sha256=e.sha(e.LAYOUT.read_bytes()))
        a.save('live/observer-identity.json',dict(expected=ident,actual=actual))
        j=e.Journal(R/'trace.jsonl',max_events=4096)
        try:result=e.observe(r,plan,ident,actual,j,seconds=120,max_stops=2048,was_running=False)
        finally:j.close()
        a.save('live/observer-result.json',result)
        held=result['hold']
        if not held:
            # Capture repeated real execution and pixels, then require explicit health inspection.
            a.save('live/post-observer.json',dict(regs=r.regs(),status=q.cmd('query-status')))
            samples=[]
            for index in range(3):
                r.cont();time.sleep(2);r.stop()
                g=r.regs();samples.append(dict(regs=g,near_eip=r.read(max(0,g['eip']-8),24).hex(),title_ts=r.read(0x10114,4).hex()))
                subprocess.run([sys.executable,'-B',str(R/'tools/ui.py'),'shot',f'health-{index}.png'],check=True)
            a.save('live/health-samples.json',samples)
            status(phase='paused_for_same_boot_health_inspection')
            print('HEALTH INSPECTION READY; paused, clients owned; decision deadline 180s',flush=True)
            end=time.monotonic()+180
            while time.monotonic()<end:
                if (R/'live/accept-healthy.json').exists():
                    e.need(all(x['title_ts']=='2ba60046' and 0x10000<=x['regs']['eip']<0x80000000 for x in samples),'CPU health unsupported')
                    healthy=True;r.cont()
                    a.save('live/healthy-handoff.json',dict(identity=ident,qmp=lease['socket'],gdb_port=1242,module=installation['module'],running=True,parent_cleanup_accepted=True,clients_closed=True,physical_input='untested'))
                    break
                time.sleep(.5)
        status(phase='observer_window_complete',observer=result)
        # Healthy ownership requires separately observed moving menu; no inference from timeout.
    except Exception as ex:
        a.save('live/error.json',dict(error=str(ex),traceback=traceback.format_exc(),identity=ident))
        status(phase='runtime_boundary_stopped',error=str(ex),live_evidence=True)
        print('STOP:',str(ex),flush=True)
    finally:
        if r and not healthy:
            try:a.save('live/final-context.json',dict(regs=r.regs(),raw_g=r.raw_regs(),stack=r.read(r.regs()['esp'],128).hex()))
            except Exception as ex:a.save('live/final-context-error.json',dict(error=str(ex)))
            r.close();r=None
        elif r:r.close();r=None
        if q and not healthy:
            try:
                a.check_native(ident,lease)
                a.save('live/pre-quit.json',dict(status=q.cmd('query-status')))
                q.cmd('quit')
            finally:a.close_q(q);q=None
            end=time.monotonic()+20
            while time.monotonic()<end:
                try:
                    current=a.native(pid)
                    if current['start_ticks']!=ident['start_ticks']:break
                except (FileNotFoundError,ProcessLookupError):break
                time.sleep(.2)
            else:raise RuntimeError('QMP quit did not produce verified process exit')
            a.save('live/cleanup.json',dict(pid=pid,start_ticks=ident['start_ticks'],process_exit_verified=True,clients_closed=True,stop='QMP quit',boot_budget='1/1'))
            status(cleanup='owned native exit verified after QMP quit; both clients closed',qmp_rsp_connections_opened=2)
        elif q:a.close_q(q)
    print('W45 runtime finished; evidence under '+str(R/'live'),flush=True)

if __name__=='__main__':main()
