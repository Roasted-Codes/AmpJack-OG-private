#!/usr/bin/env python3
from pathlib import Path
import os
import subprocess
import sys
import tomllib
import fcntl

def choose_binary(binaries, interactive=True):
    if not binaries:raise ValueError('No executable xemu AppImage (or native xemu) in this folder')
    if len(binaries)==1:return binaries[0]
    if not interactive:raise ValueError('Multiple Xemu versions in this folder; select one when launching')
    if sys.stdin.isatty():
        for i,p in enumerate(binaries,1):print(f'{i}: {p.name}')
        selection=int(input('Which Xemu? '))-1
    else:
        rows=[]
        for i,p in enumerate(binaries):rows.extend([str(i),p.name])
        r=subprocess.run(['kdialog','--title','Start Xemu','--menu','Choose emulator',*rows],capture_output=True,text=True)
        if r.returncode:raise SystemExit(0)
        selection=int(r.stdout.strip())
    if selection<0 or selection>=len(binaries):raise ValueError('Invalid selection')
    return binaries[selection]

def find_binaries(root):
    found=[]
    for p in root.iterdir():
        if not p.is_file() or not os.access(p,os.X_OK):continue
        name=p.name.lower()
        if not (name=='xemu' or ('xemu' in name and name.endswith('.appimage'))):continue
        with p.open('rb') as f:
            if f.read(4)==b'\x7fELF':found.append(p)
    return sorted(found)

def validate_config(root, cfg):
    if cfg.get('display',{}).get('renderer')!='VULKAN':
        raise ValueError("Select Vulkan in this folder's xemu.toml before launching")
    net=cfg.get('net',{})
    if net.get('enable') is not True or net.get('backend')!='pcap' or net.get('pcap',{}).get('netif')!='enp6s0':
        raise ValueError('This folder must use enabled pcap networking on enp6s0')
    for key,value in cfg.get('sys',{}).get('files',{}).items():
        if key.endswith('_path') and value:
            p=Path(value)
            if p.is_absolute() or '..' in p.parts or not (root/p).is_file():
                raise ValueError(f'{key} must point to an existing file inside this folder')

def main():
    root=Path(__file__).resolve().parent
    if sys.argv[1:] not in ([],['--check']):raise ValueError('Use Start Xemu without arguments, or --check for a no-boot check')
    cfg=tomllib.loads((root/'xemu.toml').read_text())
    validate_config(root,cfg)
    binaries=find_binaries(root)
    if not binaries:raise ValueError('No executable Xemu found in this folder')
    if not Path('/sys/class/net/enp6s0').exists():raise ValueError('Ethernet interface enp6s0 is missing')
    health=subprocess.run(['/usr/bin/python3',str(Path.home()/'.local/share/xemu-safety/guard.py'),'--health-check'],capture_output=True,text=True,timeout=10)
    if health.returncode:raise ValueError('Background crash protection is unavailable: '+health.stderr.strip())
    network=subprocess.run(['/usr/local/bin/xemu-network','--check'],capture_output=True,text=True,timeout=5)
    if network.returncode:raise ValueError('Bridged network permission unavailable: '+network.stderr.strip())
    if sys.argv[1:]==['--check']:
        print('OK: local settings, Vulkan, wired bridge, background monitor. No emulator started.')
        print('Emulators: '+', '.join(p.name for p in binaries))
        return 0
    binary=choose_binary(binaries)
    with (root/'.xemu.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        disk=cfg.get('sys',{}).get('files',{}).get('hdd_path','xbox_hdd.qcow2')
        for fd in Path('/proc').glob('[0-9]*/fd/*'):
            try:
                if fd.resolve()==(root/disk).resolve():raise ValueError('Xbox disk is already open; close the other application')
            except OSError:pass
        # Management hook: lets Hermes read/write this Xbox's memory by folder name. Harmless otherwise.
        (root/'runtime').mkdir(exist_ok=True)
        command=[str(binary),'-config_path',str(root/'xemu.toml'),'-qmp',
                 'unix:'+str(root/'runtime'/'qmp.sock')+',server=on,wait=off']
        command=['/usr/local/bin/xemu-network',*command]
        return subprocess.run(command,cwd=root).returncode

if __name__=='__main__':
    try:sys.exit(main())
    except (ValueError,OSError,subprocess.SubprocessError) as e:
        print('Xemu: '+str(e),file=sys.stderr)
        if sys.stderr.isatty() and sys.stdin.isatty():input('Press Enter to close...')
        sys.exit(1)
