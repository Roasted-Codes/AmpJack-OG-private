"""Publish already-written parent metadata through an owned FIFO."""
import os,json,stat,signal
from pathlib import Path
O=Path(__file__).resolve().parents[1]
info=json.loads((O/'live-run/PARENT-RENDEZVOUS.json').read_text());track=json.loads(Path(info['tracking']).read_text());b=json.loads((O.parent/'sol-audit/COORDINATOR_STATE.json').read_text())['runtime_binding']
assert track['process']==b['process'] and track['pid']==b['pid'] and b['session']==info['session'] and b['new_launch_authorized'] is True and b['route_api_calls']>info['baseline_api_calls']
fifo=Path(info['fifo']);s=fifo.lstat();assert not fifo.is_symlink() and stat.S_ISFIFO(s.st_mode) and s.st_uid==os.getuid()
packet=json.dumps(dict(published=True,nonce=info['nonce'],session=info['session'],process=b['process'],pid=b['pid'])).encode()+b'\n';assert len(packet)<4096
signal.alarm(120)
fd=os.open(fifo,os.O_WRONLY)
try:assert os.write(fd,packet)==len(packet)
finally:os.close(fd)
signal.alarm(0);print('Published actual parent binding to one-use rendezvous; no native command issued by sender.')
