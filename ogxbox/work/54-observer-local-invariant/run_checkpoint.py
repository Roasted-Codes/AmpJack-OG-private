"""Record exact offline test argv, environment, exits and tested-source hashes."""
import os,sys,json,hashlib,subprocess
from pathlib import Path
O=Path(__file__).resolve().parent
for p in ('tmp','cache'):(O/p).mkdir(exist_ok=True)
env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',TMPDIR=str(O/'tmp'),XDG_CACHE_HOME=str(O/'cache'))
label=sys.argv[1];argv=['/usr/bin/python3','-B',*sys.argv[2:]]
assert not (O/(label+'.receipt.json')).exists(),'receipt exists'
p=subprocess.run(argv,env=env,capture_output=True,text=True)
(O/(label+'.stdout.log')).write_text(p.stdout);(O/(label+'.stderr.log')).write_text(p.stderr)
source=O.parent/'45-x11-runtime-capture/tools'
r=dict(argv=argv,cwd=str(Path.cwd()),environment={k:env[k] for k in ('PYTHONDONTWRITEBYTECODE','TMPDIR','XDG_CACHE_HOME')},exit=p.returncode,source_hashes={str(source/n):hashlib.sha256((source/n).read_bytes()).hexdigest() for n in ('enum_watch.py','test_live_adapter.py','test_observer_local_invariant54.py')})
(O/(label+'.receipt.json')).write_text(json.dumps(r,indent=2)+'\n')
print(p.stdout,p.stderr,'EXIT='+str(p.returncode));sys.exit(p.returncode)
