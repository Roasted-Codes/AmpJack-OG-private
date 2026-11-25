#!/usr/bin/env python3
"""Mount test DVD and update the known Cerbios cached tray state only."""
import sys,struct,json
from pathlib import Path
sys.path.insert(0,str(Path.home()/'Desktop/Xbox/LAN_Stats/tools/xemu'))
from gdbrsp import RSP
from control import hmp
root=Path(__file__).resolve().parent
print(hmp('change ide0-cd1 '+str(root/'probe.iso')+' raw read-only'))
r=RSP(port=1238)
try:
 if not r.last_stop:r.reason()
 header=r.read(0x80010000,2)
 assert header==b'MZ',header.hex()
 before=r.read(0x800423b4,4);count=r.read(0x80043858,4)
 assert struct.unpack('<I',before)[0] in (0x10,0x40,0x60),before.hex()
 r.write(0x800423b4,struct.pack('<I',0x60))
 r.write(0x80043858,struct.pack('<I',(struct.unpack('<I',count)[0]+1)&0xffffffff))
 result={'kernel_header':header.hex(),'tray_before':before.hex(),'count_before':count.hex(),'tray_after':r.read(0x800423b4,4).hex(),'count_after':r.read(0x80043858,4).hex()}
 (root/'disc-mount.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
finally:
 r.cont();r.close()
