"""One-use blocking IPC rendezvous; no guest or authority changes."""
import os,json,stat,select,time
from pathlib import Path
O=Path(__file__).resolve().parents[1]
info=json.loads((O/'live-run/PARENT-RENDEZVOUS.json').read_text())
fifo=Path(info['fifo']);s=fifo.lstat()
if fifo.is_symlink() or not stat.S_ISFIFO(s.st_mode) or s.st_uid!=os.getuid():raise RuntimeError('invalid owned publication FIFO')
fd=os.open(fifo,os.O_RDONLY|os.O_NONBLOCK)
try:
 ready,_,_=select.select([fd],[],[],180)
 if not ready:raise TimeoutError('parent did not publish binding; no launch attempted')
 packet=json.loads(os.read(fd,4096))
finally:os.close(fd)
if packet.get('nonce')!=info['nonce'] or packet.get('session')!=info['session'] or packet.get('published') is not True:raise RuntimeError('wrong publication packet')
# This packet is readiness, NOT permission. Actual source/authority checks follow.
result=dict(parent_binding_published=True,session=packet['session'],process=packet['process'],pid=packet['pid'],nonce=packet['nonce'],received_ns=time.monotonic_ns(),native_commands=0)
path=O/'live-run'/('publication-ack-'+info['nonce']+'.json')
with path.open('x') as f:json.dump(result,f,indent=2);f.write('\n')
print(json.dumps(result))
