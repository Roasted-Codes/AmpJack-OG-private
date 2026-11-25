import sys, json, time, os, subprocess
from pathlib import Path
sys.path.insert(0,str(Path('/home/roasted/Desktop/Xbox/LAN_Stats/tools/xemu')))
from qmp import QMP
ROOT=Path(__file__).resolve().parent
DK=Path('/home/roasted/Desktop/Xbox/AmpJack-OG/ogxbox/work/23-reconnect-runtime/guest')
ENV=dict(os.environ,**json.loads(Path('/home/roasted/Desktop/_Parked/halo2-system-link-bridge/network-lab/isolated-desktop/environment.json').read_text()))
ENV.pop('XAUTHORITY',None)
ENV['LD_LIBRARY_PATH']=str(Path.home()/'.local/lib')
XD=str(Path.home()/'.local/bin/xdotool')
def cmd(*args): return subprocess.check_output(args,env=ENV,text=True).strip()
def window():
    for w in cmd(XD,'search','--name','xemu').split():
        pid=cmd(XD,'getwindowpid',w)
        if str(DK) in Path('/proc/'+pid+'/cmdline').read_bytes().decode(): return w
    raise RuntimeError('no owned window')
def qcall(op,**kw):
    q=QMP(str(DK/'runtime/qmp.sock'))
    try:
        q.f.write((json.dumps({'execute':op,'arguments':kw})+'\n').encode())
        while True:
            r=q._read()
            if 'event' in r: continue
            if 'error' in r: raise RuntimeError(r['error'])
            return r.get('return')
    finally: q.close()
def hmp(s): return qcall('human-monitor-command',**{'command-line':s})
def record(name,data):
    (ROOT/name).write_text(json.dumps(data,indent=2)+'\n')
    print(json.dumps(data,indent=2))
if __name__=='__main__':
    op=sys.argv[1]
    if op=='trace':
        events=['usb_host_req_data','usb_host_req_complete','usb_host_req_control','usb_ohci_td_too_many_pending','usb_ohci_td_pkt_hdr','usb_ohci_td_pkt_short','usb_ohci_td_pkt_full','usb_ohci_async_complete']
        result={'states':{e:qcall('trace-event-get-state',name=e) for e in events}}
        result['logfile']=hmp('logfile '+str(ROOT/'usb.log'))
        result['log']=hmp('log '+','.join('trace:'+e for e in events))
        time.sleep(2)
        result['bytes']= (ROOT/'usb.log').stat().st_size if (ROOT/'usb.log').exists() else None
        result['after']={e:qcall('trace-event-get-state',name=e) for e in events}
        record('trace-preflight.json',result)
    elif op=='shot':
        p=ROOT/(sys.argv[2]+'.png'); subprocess.run(['import','-display',ENV['DISPLAY'],'-window',window(),str(p)],env=ENV,check=True); print(p)
    elif op=='key':
        w=window()
        for k in sys.argv[2:]:
            cmd(XD,'keydown','--window',w,k); time.sleep(.08); cmd(XD,'keyup','--window',w,k); time.sleep(.8)
    elif op=='hmp': print(hmp(sys.argv[2]))
    elif op=='quit': print(qcall('quit'))
