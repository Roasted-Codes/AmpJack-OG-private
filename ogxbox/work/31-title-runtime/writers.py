#!/usr/bin/env python3
"""Read-only /proc inventory: emulator processes, -config_path args, open fds on primary/work23/work31 disks."""
import json,sys
from pathlib import Path
targets=[Path('/home/roasted/Desktop/_Parked/halo2-system-link-bridge/devkit--xemu--0.8.136'),Path('/home/roasted/Desktop/Xbox/AmpJack-OG/ogxbox/work/23-reconnect-runtime/guest'),Path('/home/roasted/Desktop/Xbox/AmpJack-OG/ogxbox/work/31-title-runtime/guest')]
out={'emulators':[],'config_paths':[],'open_fds':[]}
for p in Path('/proc').iterdir():
 if not p.name.isdigit():continue
 try:
  exe=str((p/'exe').readlink());cmd=(p/'cmdline').read_bytes().split(b'\0')
 except OSError:continue
 cmd=[c.decode(errors='replace') for c in cmd]
 n=Path(exe).name.lower()
 if n=='xemu' or 'xemu.appimage' in n or n.startswith('qemu-system'):out['emulators'].append({'pid':int(p.name),'exe':exe})
 if '-config_path' in cmd:out['config_paths'].append({'pid':int(p.name),'config':cmd[cmd.index('-config_path')+1]})
 try:fds=list((p/'fd').iterdir())
 except OSError:continue
 for fd in fds:
  try:t=str(fd.readlink())
  except OSError:continue
  if any(t.startswith(str(d)+'/') for d in targets):out['open_fds'].append({'pid':int(p.name),'exe':exe,'fd':fd.name,'target':t})
print(json.dumps(out,indent=1))
sys.exit(1 if (out['emulators'] or out['open_fds']) and '--require-idle' in sys.argv else 0)
