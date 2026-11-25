"""Final offline command receipts and protected-input recheck, lane51 only."""
import hashlib,json,os,subprocess,sys
from pathlib import Path
O=Path(__file__).resolve().parent;W=O.parent;R=W/'45-x11-runtime-capture';ROOT=W.parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(n,v):(O/n).write_text(json.dumps(v,indent=2,sort_keys=True)+'\n')
env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',TMPDIR=str(O),XDG_CACHE_HOME=str(O/'cache'))
commands=[]
for name,cmd,want in [('analysis-final',[sys.executable,'-B',str(O/'analyze.py')],0),('red-final',[sys.executable,'-B',str(R/'tools/test_watch_writer51.py'),'--red'],1),('focused-final',[sys.executable,'-B',str(R/'tools/test_watch_writer51.py')],0)]:
 p=subprocess.run(cmd,cwd=ROOT,env=env,capture_output=True,text=True);(O/(name+'.stdout.log')).write_text(p.stdout);(O/(name+'.stderr.log')).write_text(p.stderr);commands.append(dict(command=cmd,cwd=str(ROOT),exit=p.returncode,expected_exit=want,stdout_path=str(O/(name+'.stdout.log')),stderr_path=str(O/(name+'.stderr.log'))));assert p.returncode==want,(name,p.stdout,p.stderr)
save('commands-final.json',commands)
initial=json.loads((O/'protected-initial.json').read_text());recheck={n:dict(expected=v['expected'],actual=sha(Path(n)),ok=sha(Path(n))==v['expected']) for n,v in initial.items()};save('protected-final.json',recheck);assert all(v['ok'] for v in recheck.values())
assert (O/'original-ordered-trace.jsonl').read_bytes()==(R/'post-entry-49/live/ordered-trace.jsonl').read_bytes()
assert json.loads((O/'baseline-seq2-decoded.json').read_text())==json.loads((O/'final-seq2-decoded.json').read_text())
neg=json.loads((O/'negative-results.json').read_text());assert len(neg)==9
files=[R/'tools/enum_watch.py',R/'tools/test_watch_writer51.py',O/'authenticate.py',O/'analyze.py',O/'finalize.py',O/'original-ordered-trace.jsonl',O/'original-seq2.json',O/'baseline-seq2-decoded.json',O/'final-seq2-decoded.json',O/'real-row-replay.json',O/'negative-results.json',O/'mechanical-proof.json',O/'writer-inventory.json',O/'tu-code-section.bin',O/'tu-code-section.json',O/'xbe-sections.json',O/'pairing.json',O/'protected-initial.json',O/'protected-final.json',O/'commands-final.json',W/'50-astra-observer-topology-plan/PARENT-UPSTREAM-CHECK.json']
files+=sorted(O.glob('anchored-*.txt'))
files.append(O/'independent-entry-edge.json')
save('final-hashes.json',{str(p):sha(p) for p in files})
print(json.dumps(dict(protected_count=len(recheck),protected_ok=True,original_rows_unchanged=True,baseline_equals_final=True,negative_cases=len(neg),decoder_sha256=sha(R/'tools/enum_watch.py'),test_sha256=sha(R/'tools/test_watch_writer51.py'),all_commands_expected=True)))
