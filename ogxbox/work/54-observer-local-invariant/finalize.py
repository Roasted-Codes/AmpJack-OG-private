"""Verify final offline receipts, unchanged protected inputs and exact tested sources."""
import ast,hashlib,json
from pathlib import Path
O=Path(__file__).resolve().parent
W=O.parent;R=W/'45-x11-runtime-capture'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load(p):return json.loads(Path(p).read_text())
def save(name,data):(O/name).write_text(json.dumps(data,indent=2)+'\n')
source=[R/'tools'/n for n in ('enum_watch.py','test_observer_local_invariant54.py','test_live_adapter.py')]
hashes={str(p):sha(p) for p in source}
receipts={n:load(O/(n+'.receipt.json')) for n in ('baseline-red','initial-green','matrix-green','adapter-first','adapter-second','final-green')}
assert receipts['baseline-red']['exit']==1
assert receipts['baseline-red']['source_hashes'][str(source[0])]=='6057f8577829aaec8561b9141f66487711023e7450df6cb706469595ff21efa0'
assert all(v['exit']==0 for n,v in receipts.items() if n!='baseline-red')
assert receipts['final-green']['source_hashes']==hashes
for name in ('adapter-first','adapter-second'):
    for p in (source[0],source[2]):assert receipts[name]['source_hashes'][str(p)]==hashes[str(p)]
def outdir(label):
    line=(O/(label+'.stdout.log')).read_text().splitlines()[0]
    assert line.startswith('OUTPUT_DIRECTORY=')
    p=Path(line.split('=',1)[1]);assert p.is_relative_to(O)
    return p
F=outdir('final-green');B=outdir('baseline-red')
neg=load(F/'negative-matrix.json');static=load(F/'static-refusals.json')
assert len(neg)==len(set((x['name'],x['step']) for x in neg))
assert all(x['hold'] and not x['restore_running'] and x['continues']==1 for x in neg)
assert all({x['step'] for x in neg if x['name']==name}=={False,True} for name in {x['name'] for x in neg})
paired={}
for name in ('real-normal','real-step'):
    old=[json.loads(x) for x in (B/(name+'.jsonl')).read_text().splitlines()]
    new=[json.loads(x) for x in (F/(name+'.jsonl')).read_text().splitlines()]
    first=[x for x in new if x.get('eip')==0x4131e7];assert len(first)==1
    assert first[0]['writer']==0x4131e1 and not first[0].get('unclassified')
    unknown=[x for x in new if x.get('eip')==0x413300];assert len(unknown)==1 and unknown[0]['unclassified']
    assert new[-1]['hold'] and not new[-1]['restore_running']
    old_event=next(x for x in old if x.get('eip')==0x4131e7)
    assert old_event['writer'] is None and old_event['unclassified']
    paired[name]=dict(before_journal=str(B/(name+'.jsonl')),after_journal=str(F/(name+'.jsonl')),before=old_event,after=first[0],next_SYNTHETIC=unknown[0],cleanup=new[-1],provenance=str(F/(name+'.sources.json')))
save('before-after-replay.json',paired)
a1,a2=outdir('adapter-first'),outdir('adapter-second');assert a1!=a2
v1=load(a1/'continuation/adapter-tests.json');v2=load(a2/'continuation/adapter-tests.json');assert v1==v2
for key in ('header_decoded_pass','other_header_byte_refused','stale_native_start_refused','partial_arm_removed','safety_hold_paused_and_both_qmp_objects_closed'):assert v1[key] is True
for p in (a1,a2):
    journal=[json.loads(x) for x in (p/'continuation/partial-arm-offline.jsonl').read_text().splitlines()]
    assert journal[-1]['hold'] and not journal[-1]['restore_running']
    assert (p/'continuation/schema-offline.json').is_file()
protected=load(O/'PARENT-PROTECTED-INPUTS.json')
immutable={p:dict(expected=h,actual=sha(p)) for p,h in protected.items() if p not in (str(source[0]),str(source[2]))}
assert all(x['expected']==x['actual'] for x in immutable.values())
for original in ('ordered-trace.jsonl','final-context.json'):
    assert sha(F/('original-'+original))==sha(R/'post-entry-49/live'/original)
# Recheck frozen inputs independently of module imports or inherited pyc.
tree=ast.parse(source[0].read_text())
expected=next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='HASHES' for t in n.targets))
frozen={'dump':W/'35-loading-stop/probe3/mem_00412000_a000.bin','elf':W/'32-opus-final-integration/artifact/pic.elf','layout':W/'32-opus-final-integration/artifact/layout.json','xbe':Path('/home/roasted/Desktop/Xbox/H2-Decomp/tu15-decomp/targets/halo2-tu15-u803/default.xbe')}
for k,p in frozen.items():
    immutable[str(p)]=dict(expected=expected[k],actual=sha(p));assert sha(p)==expected[k]
parentlog=W/'53-astra-observer-local-invariant/parent-joint-baseline/test_live_adapter.py.log'
assert 'FileExistsError' in parentlog.read_text() and str(R/'continuation/partial-arm-offline.jsonl') in parentlog.read_text()
save('immutable-input-recheck.json',immutable)
save('final-tested-source-hashes.json',hashes)
save('command-transcript.json',receipts)
save('final-verification.json',dict(result='offline local observer coverage GREEN',focused_methods=7,negative_cases=len(neg),negative_factors=len({x['name'] for x in neg}),negative_layers={layer:sum(x['layer']==layer for x in neg) for layer in {x['layer'] for x in neg}},static_edge_refusals=len(static),focused_output=str(F),adapter_outputs=[str(a1),str(a2)],adapter_results_equal=True,adapter_default_tested=False,parent_collision_log=dict(path=str(parentlog),sha256=sha(parentlog),receipt_scope='parent joint baseline corroborates exit1; original fixed journal preimage pinned'),immutable_inputs=len(immutable),all_immutable_match=True,final_sources_match_test_receipts=True,combined_suites='EXCLUDED: shared output effects; parent owns final normal combined suites',native_commands_used=0,host_compilation='not required; prepare used read-only objdump/llvm-objdump/llvm-nm',remaining_unknowns=['before-write value','upper observed stack','semantic/device identity','async/global alias history','product/game/input/boot health','live admission','default adapter CLI and changed-source combined suites']))
print(json.dumps(load(O/'final-verification.json'),indent=2))
