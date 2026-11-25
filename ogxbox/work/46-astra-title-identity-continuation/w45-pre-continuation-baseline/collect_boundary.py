#!/usr/bin/env python3
"""Read-only boundary/cleanup receipts; never executes a guest/helper."""
import sys
sys.dont_write_bytecode = True
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
from parent_launch import ROOT, GUEST, DIGEST, receipt, environment, command

def run(args):
    p = subprocess.run(args, capture_output=True, text=True, timeout=30)
    return {'command': args, 'returncode': p.returncode, 'stdout': p.stdout, 'stderr': p.stderr}

def main():
    lease = receipt()
    evidence = {'epoch': time.time(), 'host_boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(), 'receipt_sha256': hashlib.sha256((ROOT/'PARENT-RUNTIME-LEASE.json').read_bytes()).hexdigest(), 'receipt_unmodified': True, 'claim_paths': [str(p) for p in ROOT.rglob('*') if 'claim' in p.name.lower()], 'qmp_path_exists': Path(lease['socket']).exists(), 'processes': [], 'guest_disk_fds': [], 'inaccessible_proc_fd_dirs': []}
    for p in Path('/proc').iterdir():
        if not p.name.isdigit():
            continue
        try:
            exe = (p/'exe').resolve(strict=True)
            argv = (p/'cmdline').read_bytes().split(b'\0')[:-1]
            if exe.name in ('Xwayland','weston','xemu','xemu-network') or str(GUEST).encode() in b' '.join(argv[:5]):
                evidence['processes'].append({'pid': int(p.name), 'exe': str(exe), 'argv': [a.decode(errors='replace') for a in argv], 'stat': (p/'stat').read_text()})
        except OSError:
            pass
        try:
            for fd in (p/'fd').iterdir():
                try:
                    if fd.resolve(strict=True) == GUEST/'iguana-dev.qcow2':
                        evidence['guest_disk_fds'].append(str(fd))
                except OSError:
                    pass
        except PermissionError:
            evidence['inaccessible_proc_fd_dirs'].append(int(p.name))
        except OSError:
            pass
    fixture_record = json.loads((ROOT/'fixture-result.json').read_text())
    fixture_pid = json.loads(fixture_record['stdout'])['pid']
    evidence['fixture_pid'] = fixture_pid
    evidence['fixture_pid_absent'] = not (Path('/proc')/str(fixture_pid)).exists()
    for name,args in {
        'old-unit-journal': ['journalctl','--user','-u','ampjack-parent42-devkit.service','--no-pager','-n','400'],
        'helper-disassembly': ['objdump','-d','-M','intel','/usr/local/bin/xemu-network'],
        'helper-capabilities': ['getcap','/usr/local/bin/xemu-network'],
        'helper-stat': ['stat','/usr/local/bin/xemu-network'],
        'native-dependencies': ['ldd',str(GUEST/'xemu')],
        'new-unit': ['systemctl','--user','show',lease['unit'],'-p','LoadState','-p','ActiveState','-p','MainPID','-p','InvocationID'],
        'tcp-listeners': ['ss','-ltnp'],
        'unix-listeners': ['ss','-xlpn'],
        'systemd-manager-env': ['systemctl','--user','show-environment'],
    }.items():
        rec = run(args)
        if name == 'systemd-manager-env':
            rec['stdout'] = '\n'.join(l for l in rec['stdout'].splitlines() if l.split('=',1)[0] in ('DISPLAY','WAYLAND_DISPLAY','XDG_RUNTIME_DIR','XAUTHORITY','SDL_VIDEO_DRIVER','LIBGL_ALWAYS_SOFTWARE','VK_ICD_FILENAMES','VK_DRIVER_FILES','DRI_PRIME'))+'\n'
        (ROOT/(name+'.json')).write_text(json.dumps(rec,indent=2)+'\n')
    evidence['nonlaunch_command'] = command(lease,environment(lease))
    (ROOT/'boundary-cleanup.json').write_text(json.dumps(evidence,indent=2)+'\n')
    print(json.dumps({k:v for k,v in evidence.items() if k not in ('processes','inaccessible_proc_fd_dirs','nonlaunch_command')},indent=2))
    print('Relevant processes:', json.dumps(evidence['processes'],indent=2))

if __name__ == '__main__':
    main()
