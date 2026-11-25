"""Record the fresh image review; no runtime protocol client."""
from pathlib import Path
import hashlib,json,os,subprocess
W=Path('/home/roasted/Desktop/Xbox/AmpJack-OG/ogxbox/work');S=W/'45-x11-runtime-capture/post-entry-59';OUT=W/'59-sol-bounded-preparation/live-run/preissue-97zbuuox'
ready=json.loads((S/'live/dashboard-review-ready.json').read_text());discovery=json.loads((S/'live/first-native-discovery.json').read_text());handle=json.loads((S/'live/launch-handle.json').read_text())
identity=ready['identity'];image=S/'live/dashboard-before.png'
digest=hashlib.sha256(image.read_bytes()).hexdigest()
assert digest==ready['sha256'] and identity==discovery['identity']
assert discovery['pin']['invocation']==handle['invocation_id']
assert hashlib.sha256((S/'runtime-claim.json').read_bytes()).hexdigest()==handle['claim_sha256']
fields=Path(f"/proc/{identity['pid']}/stat").read_text().rsplit(')',1)[1].split()
assert int(fields[19])==identity['start_ticks']
assert Path('/proc/sys/kernel/random/boot_id').read_text().strip()==identity['boot_id']
env=dict(os.environ,DISPLAY=':2',LD_LIBRARY_PATH='/home/roasted/.local/lib')
cmd=['/home/roasted/.local/bin/xdotool','getwindowpid',ready['window']]
p=subprocess.run(cmd,env=env,capture_output=True,text=True)
assert p.returncode==0 and int(p.stdout.strip())==identity['pid']
decision=dict(sha256=digest,native_pid=identity['pid'],start_ticks=identity['start_ticks'],retail_parent_row_verified=True,source_image=str(image),window=ready['window'],invocation_id=handle['invocation_id'],review='Fresh image viewed with vision: green highlight is Audio Console App; next top-level row is Halo 2 (1.29 GB). Downloader, Halo 2 and updater entries are indented children underneath. Exactly one Down selects the normal Halo 2 parent, not an indented child. No alignment input issued.',window_pid_check=dict(argv=cmd,exit_code=p.returncode,stdout=p.stdout,stderr=p.stderr))
with (OUT/'NAVIGATION-REVIEW.json').open('x') as f:json.dump(decision,f,indent=2);f.write('\n')
with (S/'navigation-reviewed.json').open('x') as f:json.dump(decision,f,indent=2);f.write('\n')
print(json.dumps(decision,indent=2))
