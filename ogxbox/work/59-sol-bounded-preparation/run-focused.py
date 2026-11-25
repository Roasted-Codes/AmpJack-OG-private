"""Record an isolated normal unittest CLI, no inherited test imports/caches."""
from pathlib import Path
import hashlib,json,os,subprocess,sys,tempfile
O=Path(__file__).resolve().parent
R=O.parent/'45-x11-runtime-capture'
run=Path(tempfile.mkdtemp(prefix=sys.argv[1]+'-',dir=O))
env=dict(os.environ)
for k in ('TMPDIR','TEMP','TMP','XDG_CACHE_HOME','PYTHONPYCACHEPREFIX'):
    p=run/k;p.mkdir();env[k]=str(p)
env['PYTHONDONTWRITEBYTECODE']='1'
env.pop('PYTHONPATH',None)
argv=['/usr/bin/python3','-B','-m','unittest','-v','test_active_slot59']
paths=[R/'parent_launch.py',R/'tools/test_active_slot59.py',R/'tools/recovery.py',R/'tools/runtime_session.py']
hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
p=subprocess.run(argv,cwd=R/'tools',env=env,capture_output=True,text=True)
(run/'stdout.txt').write_text(p.stdout);(run/'stderr.txt').write_text(p.stderr)
receipt=dict(argv=argv,cwd=str(R/'tools'),env={k:env.get(k) for k in ('TMPDIR','TEMP','TMP','XDG_CACHE_HOME','PYTHONPYCACHEPREFIX','PYTHONDONTWRITEBYTECODE')},exit_code=p.returncode,all_passed=p.returncode==0,run_root=str(run),source_hashes=hashes,synthetic=True,native_commands=0)
(run/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(run);print(p.stderr);sys.exit(p.returncode)
