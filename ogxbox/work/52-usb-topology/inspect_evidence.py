"""Read-only evidence inventory; all generated receipts stay beside this script."""
import hashlib,json
from pathlib import Path
O=Path(__file__).resolve().parent
W=O.parent
P=W/'50-astra-observer-topology-plan'
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
f=json.loads((P/'PARENT-FROZEN-REFERENCE.json').read_text())
p=json.loads((P/'PARENT-PINNED-INPUTS.json').read_text())
items={v['frozen_path']:v['sha256'] for v in f['source'].values()}
items.update(f['immutable_live_files']);items.update(p['read_only_hashes'])
results=[{'path':k,'expected':v,'actual':sha(k)} for k,v in items.items()]
(O/'reference-verification.json').write_text(json.dumps(results,indent=2)+'\n')
print('verified',len(results),'mismatches',sum(x['actual']!=x['expected'] for x in results))
L=W/'45-x11-runtime-capture/post-entry-49/live'
t=json.loads((L/'usb-topology.json').read_text())
(O/'qtree-readable.txt').write_text(t['qtree'])
print('LIVE FILE NAMES', '\n'.join(x.name for x in L.iterdir() if x.is_file()))
print('USB SUBTREE')
lines=t['qtree'].splitlines()
for i,s in enumerate(lines):
 if any(k in s for k in ('usb','USB','gamepad','pt_pad','hostbus','hostaddr','vendorid','productid','port =')):
  print(i+1,s)
print('FROZEN SPEED/TEST OUTPUT REFERENCES')
for k in f['source'].values():
 path=Path(k['frozen_path'])
 for n,line in enumerate(path.read_text().splitlines(),1):
  if any(v in line for v in ('12 Mb/s','usb-topology','device_add','sysfs','TemporaryDirectory','write_text','write_bytes','mkdir','/tmp','unittest.main')):
   print(path.name,n,line)
