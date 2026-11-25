#!/usr/bin/env python3
import sys
sys.dont_write_bytecode=True
import json
import hashlib
import os
from pathlib import Path
import struct
import subprocess
import time
import live_adapter as a
R=a.ROOT
sys.path.insert(0,str(R))
from parent_launch import receipt, environment
TITLE_DIGEST='14d63216b423a8fe61098f0fec6c73476dec54739a4b4ac026f86093e8f206c6'

def title_attestation():
    raw=(R/'PARENT-TITLE-IDENTITIES.json').read_bytes()
    a.obs.need(a.obs.sha(raw)==TITLE_DIGEST,'changed parent title attestation')
    return json.loads(raw)['per_path']

def xbe_identity(path, data):
    a.obs.need(data[:4]==b'XBEH','not XBEH')
    u=lambda off:struct.unpack_from('<I',data,off)[0]
    base=u(0x104); cert=u(0x118)-base
    a.obs.need(0<=cert<=len(data)-0xb0,'certificate out of bounds')
    return dict(guest_path=path,sha256=a.obs.sha(data),size=len(data),xbe_base=hex(base),
                certificate_title_id=hex(u(cert+8)),certificate_version=u(cert+0xac),
                header_timestamp=hex(u(0x114)),title_name=data[cert+12:cert+92].decode('utf-16le').rstrip('\0'))

def verify_titles(observed, expected):
    for path, pin in expected.items():
        a.obs.need(path in observed,'missing title path '+path)
        a.obs.need(observed[path]==pin,'path-specific title identity mismatch '+path)

def resources(lease):
    """Read-only inventory, including unidentified processes and readable FDs."""
    disk=Path(lease['identities']['hdd_path']['path']).resolve()
    procs=[]; fds=[]
    for p in Path('/proc').iterdir():
        if not p.name.isdigit():continue
        try:
            argv=(p/'cmdline').read_bytes().decode(errors='replace').split('\0')
            target=any(arg in (str(Path(lease['fresh_clone'])/name) for name in ('xemu','.start-xemu.py','xemu.toml')) for arg in argv)
            try:exe=(p/'exe').resolve(strict=True)
            except PermissionError:
                if target:procs.append(dict(pid=int(p.name),argv=argv,exe_error='EACCES; candidate cannot be ignored'))
                continue
            if exe.name.lower()=='xemu' or 'xemu.appimage' in exe.name.lower() or exe.name.startswith('qemu-system') or target:
                procs.append(dict(pid=int(p.name),exe=str(exe),argv=argv))
        except OSError:pass
        for fd in (p/'fd').glob('*'):
            try:
                if fd.resolve(strict=True)==disk:fds.append(str(fd))
            except OSError:pass
    unit=subprocess.run(['systemctl','--user','show',lease['unit'],'--no-pager',
                         '--property=LoadState,ActiveState,SubState,MainPID,ControlGroup'],capture_output=True,text=True)
    tcp=subprocess.run(['ss','-ltnpH','sport = :1242'],capture_output=True,text=True,check=True).stdout
    unix=subprocess.run(['ss','-xlpnH'],capture_output=True,text=True,check=True).stdout
    return dict(processes=procs,disk_fds=fds,unit=unit.stdout,tcp=tcp,
                qmp_listeners=[line for line in unix.splitlines() if lease['socket'] in line],
                qmp_path_exists=Path(lease['socket']).exists())

def stopped_gates(lease, env, *, require_tests=True, claim_path=None, evidence='continuation-2'):
    claim_path=R/'runtime-claim.json' if claim_path is None else Path(claim_path)
    a.obs.need(not claim_path.exists(),'existing or interrupted claim')
    before=resources(lease)
    a.save(evidence+'/preflight-resources.json',before)
    a.obs.need(not before['processes'] and not before['disk_fds'],'guest/helper or disk FD already owned')
    a.obs.need('LoadState=not-found' in before['unit'],'W45 unit already exists')
    a.obs.need(not before['tcp'] and not before['qmp_listeners'] and not before['qmp_path_exists'],'endpoint conflict')
    identities={}
    for name,pin in {**lease['identities'],**lease['frozen_inputs']}.items():
        p=Path(pin['path'])
        with p.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
        a.obs.need(digest==pin['sha256'] and p.stat().st_size==pin['size'],'artifact mismatch '+name)
        stat=p.stat()
        for key,value in (('inode',stat.st_ino),('mtime_ns',stat.st_mtime_ns)):
            if key in pin:a.obs.need(value==pin[key],'stopped artifact stat mismatch '+name+' '+key)
        identities[name]=digest
    guest=Path(lease['fresh_clone']); disk=guest/'iguana-dev.qcow2'
    commands=[]
    def run(cmd):
        p=subprocess.run(cmd,capture_output=True,text=True)
        commands.append(dict(command=cmd,returncode=p.returncode,stdout=p.stdout,stderr=p.stderr))
        a.save(evidence+'/preflight-commands.json',commands)
        a.obs.need(p.returncode==0,'preflight command failed '+repr(cmd)+': '+p.stderr)
        return p.stdout
    check=json.loads(run(['qemu-img','check','--output=json',str(disk)]))
    info=json.loads(run(['qemu-img','info','--output=json',str(disk)]))
    a.obs.need(check.get('check-errors')==0 and not info.get('backing-filename'),'qcow errors/backing')
    roq=a.load_file('roq_w45','/home/roasted/.hermes/skills/xemu-development-workflow/scripts/roqfatx.py')
    dev=roq.Qcow2(str(disk)); observed={}; headers={}
    try:
        off,length=roq.PARTS['E']; fs=roq.Fatx(dev,off,length)
        expected=title_attestation()
        for path in expected:
            data=fs.read(path[2:]); observed[path]=xbe_identity(path,data)
            header=bytearray(data[:0x178])
            for offset,key in ((0x128,a.loader.RETAIL_EP_KEY),(0x158,a.loader.RETAIL_THUNK_KEY)):
                struct.pack_into('<I',header,offset,struct.unpack_from('<I',header,offset)[0]^key)
            headers[path]=header.hex()
        verify_titles(observed,expected)
    finally:dev.f.close()
    usb=[]
    for d in Path('/sys/bus/usb/devices').iterdir():
        try:
            if (d/'idVendor').read_text().strip()=='045e' and (d/'idProduct').read_text().strip()=='0b12':
                row={k:(d/k).read_text().strip() for k in ('busnum','devnum','speed')}
                node=Path(f"/dev/bus/usb/{int(row['busnum']):03d}/{int(row['devnum']):03d}")
                row.update(sysfs=str(d),node=str(node),readable=os.access(node,os.R_OK),writable=os.access(node,os.W_OK));usb.append(row)
        except OSError:pass
    a.obs.need(len(usb)==1 and usb[0]['readable'] and usb[0]['writable'],'pad inaccessible/ambiguous')
    ldd=run(['ldd',str(guest/'xemu')]);a.obs.need('not found' not in ldd,'native dependencies missing')
    guard=run(['/usr/bin/python3','-B',str(guest/'.start-xemu.py'),'--check'])
    fixture=json.loads((R/'PARENT-RESULT-INTAKE.json').read_text())['display_fixture_reexecuted']['stdout']
    a.obs.need(fixture['passed'] and fixture['driver']=='x11' and not fixture['xauthority_present'],'parent SDL fixture failed')
    dispatch=a.kernel_dispatch_pin()
    a.obs.prepare()
    if require_tests:
        tests=json.loads((R/'continuation-2/tests/result.json').read_text())
        a.obs.need(tests['all_passed'] and tests['session']==os.environ.get('HERMES_SESSION_ID'),'changed production tests absent/wrong session')
        for path,digest in tests['production_hashes'].items():
            a.obs.need(a.obs.sha((R/path).read_bytes())==digest,'production changed since tests '+path)
    after=resources(lease)
    a.obs.need(not after['processes'] and not after['disk_fds'] and not after['tcp']
               and not after['qmp_listeners'] and not after['qmp_path_exists']
               and 'LoadState=not-found' in after['unit'],'resources changed during stopped preflight')
    result=dict(epoch=time.time(),identities=identities,hashes=observed,live_headers=headers,usb=usb,
                qcow_check=check,qcow_info=info,dependencies=ldd,guard=guard,resources=before,
                kernel_dispatch=dispatch,unprivileged_fixture_only=True,commands=commands)
    a.save(evidence+'/preflight.json',result)
    return result

if __name__=='__main__':
    if sys.argv[1:]==['--active-slot']:
        from parent_launch import resolve_active_slot
        slot=resolve_active_slot(require_confirmation=False);a.EVIDENCE_ROOT=slot.path
        proof=stopped_gates(slot.lease,environment(slot.lease),require_tests=False,claim_path=slot.claim,evidence=slot.path.name)
    elif sys.argv[1:]==['--post-entry-47']:
        from parent_launch import receipt47, authority47
        lease=receipt47();authority47(lease,require_confirmation=False)
        proof=stopped_gates(lease,environment(lease),require_tests=False,claim_path=lease['claim_path'],evidence='post-entry-47')
    elif not sys.argv[1:]:
        lease=receipt();proof=stopped_gates(lease,environment(lease))
    else:raise ValueError('unsupported preflight mode')
    print(json.dumps(proof,indent=2))
