from pathlib import Path
import os,struct,json,hashlib,datetime,subprocess,collections,re
from typing import Any
O=Path(__file__).resolve().parent;R=O.parents[2]
summary: dict[str,Any]={'utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
m=json.loads((O/'input-hashes.json').read_text())
summary['input_hashes_unchanged']=all(hashlib.sha256((R/p).read_bytes()).hexdigest()==v['sha256'] for p,v in m.items())
assert summary['input_hashes_unchanged']
summary['runtime_logs']={}
for name in ('human-run.log','pad-run-2.log'):
 lines=(R/'ogxbox/work/17-sol-execution/runtime'/name).read_text().splitlines();rx=[]
 for l in lines:
  if l.startswith('RX '):
   mm=re.search(r' n=(\d+) (.*)',l);assert mm is not None
   rx.append(bytes.fromhex(mm[2]));assert len(rx[-1])==int(mm[1])
 summary['runtime_logs'][name]={'rx_count':len(rx),'command_counts':dict(collections.Counter(f'{x[0]:02x}' for x in rx)),'txdone_count':sum(l.startswith('TXDONE ') for l in lines),'state_count':sum(l.startswith('STATE ') for l in lines),'callback_lines':[l for l in lines if l.startswith('CB ')],'exit':'GIPEXIT auto' in lines}
pe=(R/'ogxbox/gipdriver/bin/AmpJackGip.exe').read_bytes();xb=(R/'ogxbox/gipdriver/bin/default.xbe').read_bytes()
p=struct.unpack_from('<I',pe,0x3c)[0];np,op=struct.unpack_from('<H',pe,p+6)[0],struct.unpack_from('<H',pe,p+20)[0];base=struct.unpack_from('<I',pe,p+52)[0]
ps=[]
for i in range(np):
 vs,va,rs,ro=struct.unpack_from('<IIII',pe,p+24+op+40*i+8);ps.append((base+va,vs,ro))
xbbase=struct.unpack_from('<I',xb,0x104)[0];n=struct.unpack_from('<I',xb,0x11c)[0];t=struct.unpack_from('<I',xb,0x120)[0]-xbbase
xs=[]
for i in range(n):
 flags,va,vs,ro,rs=struct.unpack_from('<IIIII',xb,t+56*i);xs.append((va,vs,ro))
def get(b,sections,va,n):
 for v,s,o in sections:
  if v<=va and va+n<=v+s:return b[o+va-v:o+va-v+n]
 raise ValueError(hex(va))
summary['pe_xbe_ranges']={}
for name,a,z in [('submit',0x2ef3f,0x2f265),('addcomplete',0x2f9bb,0x2fb7b),('open',0x30108,0x3027d),('program',0x32945,0x32c43)]:
 equal=get(pe,ps,a,z-a)==get(xb,xs,a,z-a);assert equal
 summary['pe_xbe_ranges'][name]={'start':hex(a),'end':hex(z),'equal':equal}
b=(O/'appimage/usr/bin/xemu').read_bytes()
summary['extracted_xemu']={'sha256':hashlib.sha256(b).hexdigest(),'bytes':len(b),'version_string_0_8_136':b'0.8.136\0' in b}
summary['binary_pins']={}
for va,hexbytes,meaning in [(0x64b948,'488d87b0070000','shared buffer = controller+0x7b0'),(0x64bb5f,'8babb0270000','single async TD = controller+0x27b0'),(0x64c14e,'e8dd950500','OUT guest memory read before busy rejection'),(0x64c5dd,'83bbb027000000','busy check after OUT copy'),(0x64c5e4,'0f85c50a0000','busy branch to too-many-pending'),(0x64d0b2,'e8e9080000','call trace too-many-pending'),(0x64c269,'e832970500','IN copy to guest uses same shared buffer')]:
 actual=b[va-0x1000:va-0x1000+len(bytes.fromhex(hexbytes))];assert actual.hex()==hexbytes
 summary['binary_pins'][hex(va)]={'bytes':hexbytes,'meaning':meaning}
summary['host']={'usbmon_module':Path('/sys/module/usbmon').exists(),'usbmon_debugfs':Path('/sys/kernel/debug/usb/usbmon').exists(),'devices':[],'xemu_processes':[]}
for d in Path('/sys/bus/usb/devices').iterdir():
 try:
  if (d/'idVendor').read_text().strip()!='045e' or (d/'idProduct').read_text().strip()!='0b12':continue
  bus=int((d/'busnum').read_text());dev=int((d/'devnum').read_text());node=f'/dev/bus/usb/{bus:03}/{dev:03}'
  summary['host']['devices'].append({'sysfs':str(d),'speed':(d/'speed').read_text().strip(),'node':node,'readable':os.access(node,os.R_OK),'writable':os.access(node,os.W_OK),'interfaces':{x.name:str((x/'driver').resolve()) for x in d.parent.glob(d.name+':*') if (x/'driver').exists()}})
 except (OSError,ValueError):continue
for d in Path('/proc').glob('[0-9]*'):
 try:
  exe=(d/'exe').resolve()
  if exe.name in ('xemu','xemu.AppImage'):summary['host']['xemu_processes'].append({'pid':d.name,'exe':str(exe)})
 except OSError:pass
summary['host']['matching_input_nodes']=[]
for d in Path('/sys/class/input').glob('event*'):
 try:
  if (d/'device/id/vendor').read_text().strip()=='045e' and (d/'device/id/product').read_text().strip()=='0b12':
   node='/dev/input/'+d.name;summary['host']['matching_input_nodes'].append({'node':node,'readable':os.access(node,os.R_OK),'name':(d/'device/name').read_text().strip()})
 except OSError:pass
(O/'verification.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2))
