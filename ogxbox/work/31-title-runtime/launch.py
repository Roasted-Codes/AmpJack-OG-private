#!/usr/bin/env python3
"""Boot only the prepared experimental guest through its copied launcher."""
import json,os,subprocess,time
from pathlib import Path
root=Path(__file__).resolve().parent
guest=root/'guest'
env=json.loads(Path('/home/roasted/Desktop/_Parked/halo2-system-link-bridge/network-lab/isolated-desktop/environment.json').read_text())
assert env['DISPLAY'] not in (':0',':1')
assert Path(env['WAYLAND_DISPLAY']).is_socket()
command=['systemd-run','--user','--unit=ampjack-parent31-devkit','--property=Restart=no','--setenv=XAUTHORITY=']
for key,value in env.items():command.append(f'--setenv={key}={value}')
command+=['--working-directory='+str(guest),'/usr/bin/python3',str(guest/'.start-xemu.py')]
(root/'launch.json').write_text(json.dumps({'epoch':time.time(),'env':env,'command':command},indent=2))
subprocess.run(command,check=True)
