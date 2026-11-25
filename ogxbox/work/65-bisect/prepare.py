#!/usr/bin/python3
import os, sys, json, hashlib, shutil, subprocess
from pathlib import Path
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent
R=W.parents[2]
S=W.parent/'63-wake-rumble'
EXPECTED='7bbfdafaa91920269876aa54e02efe278b738c0298aeb7bd629b1aaf8a1a08b8'
# All compiler temporary files and bytecode stay in the owned directory.
(W/'tmp').mkdir(exist_ok=True)
os.environ['TMPDIR']=str(W/'tmp');os.environ['PYTHONDONTWRITEBYTECODE']='1'
def state(step,**kw):
 (W/'RESULT.json').write_text(json.dumps(dict(status='INCOMPLETE',step=step,**kw),indent=2)+'\n')
 (W/'REPORT.md').write_text('INCOMPLETE\n\n'+step+'\n'+json.dumps(kw,indent=2)+'\n')
(W/'tools').mkdir(exist_ok=True)
for f in ['apply_w63.py','make_packaging.py','gen_layout.py']:
 shutil.copyfile(S/'tools'/f,W/'tools'/f)
# W63 orig is its self-contained unmodified W43 build-input snapshot.
shutil.copytree(S/'orig',W/'baseline'/'src',ignore=shutil.ignore_patterns('out','__pycache__'))
cmd=['bash',str(W/'baseline/src/ogxbox/integration/build_pic.sh')]
p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
(W/'baseline/build.log').write_text('$ '+' '.join(cmd)+'\n'+p.stdout+f'\nexit={p.returncode}\n')
print(p.stdout);assert p.returncode==0
elf=W/'baseline/src/ogxbox/integration/out/pic.elf'
h=hashlib.sha256(elf.read_bytes()).hexdigest()
state('Step 0 baseline built',baseline_elf_sha256=h,expected_elf_sha256=EXPECTED,match=h==EXPECTED)
assert h==EXPECTED, 'BASELINE MISMATCH: stop; compare baseline inputs to W43 frozen source before variants'
print('BASELINE EXACT',h)
print('ORIG INPUTS',*[str(p.relative_to(W/'baseline/src')) for p in (W/'baseline/src').rglob('*') if p.is_file() and '/out/' not in str(p)],sep='\n')
