"""Launch only the new focused offline module with atomic per-run outputs."""
import hashlib,json,os,pathlib,subprocess,tempfile,sys
D=pathlib.Path(__file__).resolve().parent
R=D.parent/'45-x11-runtime-capture/tools'
run=pathlib.Path(tempfile.mkdtemp(prefix=sys.argv[1]+'-',dir=D))
env=dict(os.environ,USB57_RUN=str(run))
for key,name in [('TMPDIR','tmp'),('XDG_CACHE_HOME','cache'),('PYTHONPYCACHEPREFIX','pycache')]:
    path=run/name;path.mkdir();env[key]=str(path)
cmd=['/usr/bin/python3','-B','-m','unittest','-v','test_usb_target57']
hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [R/'runtime_effects.py',R/'test_usb_target57.py',R/'usb_target57.py'] if p.exists()}
p=subprocess.run(cmd,cwd=R,env=env,capture_output=True,text=True)
(run/'stdout.log').write_text(p.stdout);(run/'stderr.log').write_text(p.stderr)
(run/'execution.json').write_text(json.dumps(dict(argv=cmd,cwd=str(R),environment={k:env[k] for k in ['USB57_RUN','TMPDIR','XDG_CACHE_HOME','PYTHONPYCACHEPREFIX']},exit=p.returncode,tested_sha256=hashes),indent=2))
print(run);print(p.stdout);print(p.stderr);print('EXIT',p.returncode)
sys.exit(p.returncode)
