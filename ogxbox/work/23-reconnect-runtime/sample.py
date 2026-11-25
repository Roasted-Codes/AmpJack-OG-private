#!/usr/bin/env python3
"""Read exact i386-probe counters; bind every sample to its code image."""
import sys,struct,json,time
from pathlib import Path
sys.path.insert(0,str(Path.home()/'Desktop/Xbox/LAN_Stats/tools/xemu'))
from gdbrsp import RSP
root=Path(__file__).resolve().parent
blob=(root/'layout.obj').read_bytes();n=struct.unpack_from('<H',blob,2)[0];opt=struct.unpack_from('<H',blob,16)[0]
for i in range(n):
 at=20+opt+i*40
 if blob[at:at+8].rstrip(b'\0')==b'.data':
  size,pos=struct.unpack_from('<II',blob,at+16);data=blob[pos:pos+size];break
else:raise RuntimeError('Missing actual-target layout')
keys=['size','device','rx_events','tx_events','in_flight','state','failed','generation','lifecycle','pending','detached','close_stage','close_pending','close_count','close_submit_fail','remove_complete_called','in_handle','out_handle','control_handle']
vals=struct.unpack('<'+str(len(keys))+'I',data[:4*len(keys)]);layout=dict(zip(keys,vals));(root/'layout.json').write_text(json.dumps(layout,indent=2))
exe=root.parents[1]/'gipdriver/bin/default.xbe';b=exe.read_bytes();base=struct.unpack_from('<I',b,0x104)[0];s=struct.unpack_from('<I',b,0x120)[0]-base;va,raw=struct.unpack_from('<I',b,s+4)[0],struct.unpack_from('<I',b,s+12)[0]
r=RSP(port=1238)
try:
 if not r.last_stop:r.reason()
 assert r.read(0x10000,4)==b'XBEH','Not XBE image'
 assert r.read(va,64)==b[raw:raw+64],'Unexpected active title/code'
 mem=r.read(0x2b40c,layout['size'])
 result={k:struct.unpack_from('<I',mem,v)[0] for k,v in layout.items() if k!='size'}
 result.update(input_seen=struct.unpack('<I',r.read(0x2b950,4))[0],utc_epoch=time.time(),code_prefix_verified=True)
 (root/(sys.argv[1]+'.json')).write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
finally:
 r.cont();r.close()
