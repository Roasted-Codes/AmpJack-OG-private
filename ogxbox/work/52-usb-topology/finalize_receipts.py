"""Offline final receipts; reads saved files/source and runs read-only git only."""
import hashlib,json,subprocess
from pathlib import Path
O=Path(__file__).resolve().parent; W=O.parent
def digest(data):
 return hashlib.sha256(data).hexdigest()
revision='6095054b7d02dfac25fdc4a8ba9300358046e860'
paths=['hw/usb/bus.c','hw/usb/core.c','hw/usb/host-libusb.c','hw/usb/desc.c','hw/xbox/xid-gamepad.c','ui/xemu-input.c','include/hw/usb.h','qom/object.c']
rows=[]
for name in paths:
 p=W/'astra-emu-fix/source'/name
 git=subprocess.run(['git','-C',str(W/'astra-emu-fix/source'),'show',revision+':'+name],capture_output=True,check=True)

 rows.append(dict(file=name,revision=revision,worktree_sha256=digest(p.read_bytes()),git_blob_content_sha256=digest(git.stdout),equal_to_revision=p.read_bytes()==git.stdout,reset_tree_equal=p.read_bytes()==(W/'36-reset-build/source'/name).read_bytes()))
assert all(r['equal_to_revision'] and r['reset_tree_equal'] for r in rows)
(O/'source-revision-verification.json').write_text(json.dumps(rows,indent=2)+'\n')
m=json.loads((O/'test-matrix.json').read_text())
assert m['tests_run']==len(m['matrix']) and m['errors']==m['failures']==0
print('source files equal to revision and both trees:',len(rows))
print('tests:',m['tests_run'],'matrix entries:',len(m['matrix']),'derived:',sum(r['derived'] for r in m['matrix']))
print('qualified derived cases:',[r['case'] for r in m['matrix'] if r['qualification']])
files=[p for p in O.iterdir() if p.is_file() and p.name not in ('REPORT.md','status.json','shortsummary.txt','final-hashes.json','finalize.log')]
(O/'final-hashes.json').write_text(json.dumps({str(p):digest(p.read_bytes()) for p in sorted(files)},indent=2)+'\n')
print('hashed owned artifacts:',len(files))
