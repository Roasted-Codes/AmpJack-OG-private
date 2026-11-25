"""Offline evidence closure only; never admission or a future lease."""
from pathlib import Path
import ast,difflib,hashlib,importlib.util,json,re,sys
sys.dont_write_bytecode=True
O=Path(__file__).resolve().parent
R=O.parent/'45-x11-runtime-capture'
S=R/'post-entry-59/preparation'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,obj):
    p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('x') as f:f.write(json.dumps(obj,indent=2,sort_keys=True)+'\n')
# Source-only import of the owned launcher, no environment/discovery calls.
spec=importlib.util.spec_from_file_location('parent_launch59_closure',R/'parent_launch.py')
w=importlib.util.module_from_spec(spec);sys.modules[spec.name]=w;spec.loader.exec_module(w)
runs=[O/'verified1-opz2c3au',O/'verified2-l42gerr7']
receipts={};enumerations=[];imports={};fixtures={};links={};positive={}
for run in runs:
    receipt=json.loads((run/'receipt.json').read_text());assert receipt['all_passed'] and receipt['exit_code']==0
    for p,h in receipt['source_hashes'].items():assert sha(Path(p))==h,('untested final edit',p)
    text=(run/'stderr.txt').read_text()
    names=re.findall(r'^(test_\S+) \(test_active_slot59\.Slot59\.\S+\) \.\.\. ok$',text,re.M)
    n=int(re.search(r'Ran (\d+) tests',text)[1]);assert len(names)==n==103 and len(set(names))==n
    enumerations.append(sorted(names));receipts[str(run/'receipt.json')]=sha(run/'receipt.json')
    loaded=list(run.rglob('actual-imports.json'));assert len(loaded)==1
    imports[str(loaded[0])]=json.loads(loaded[0].read_text())
    p=list(run.rglob('test_normal_positive_claim_cleanup_same_slot/45-x11-runtime-capture/post-entry-59/SOURCE-MANIFEST.json'))
    assert len(p)==1
    positive[str(p[0])]=sha(p[0])
    for p in run.rglob('*'):
        if p.is_symlink():links[str(p)]=str(p.readlink())
        elif p.is_file():fixtures[str(p)]=sha(p)
assert enumerations[0]==enumerations[1]
required=w.required_sources59()
files={p:sha(Path(p)) for p in sorted(required)}
for inventory in imports.values():
    for mod,pin in inventory.items():
        assert sha(Path(pin['path']))==pin['sha256'],('import drift',mod)
        files[pin['path']]=pin['sha256']
# Check tested positive mirror source bytes against the exact final sources.
for manifest in positive:
    p=Path(manifest);mirror=p.parents[1];out=mirror.parent;guest=out/'42-enum-observer/parent-prepared-guest'
    m=json.loads(p.read_text())
    for name,h in m['files'].items():
        n=Path(name)
        original=R/n.relative_to(mirror) if n.is_relative_to(mirror) else w.GUEST/n.relative_to(guest) if n.is_relative_to(guest) else O.parent/n.relative_to(out) if n.is_relative_to(out) else n
        assert sha(original)==h,('positive fixture not final source',original)
pins=json.loads((O/'PARENT-PROTECTED-INPUTS.json').read_text())
protected={p:dict(before=h,after=sha(Path(p)),unchanged=sha(Path(p))==h) for p,h in pins.items()}
unexpected=[p for p,item in protected.items() if not item['unchanged'] and p!=str(R/'parent_launch.py')]
assert not unexpected,unexpected
save(O/'PROTECTED-INPUTS-AFTER.json',protected)
old=json.loads((R/'post-entry-49/PARENT-RUNTIME-LEASE.json').read_text())
frozen={pin['path']:dict(sha256=sha(Path(pin['path'])),expected=pin['sha256']) for pin in old['frozen_inputs'].values()}
assert all(p['sha256']==p['expected'] for p in frozen.values())
edges={}
for name in files:
    p=Path(name)
    if p.suffix=='.py':
        try:tree=ast.parse(p.read_text())
        except (SyntaxError,UnicodeError):continue
        edges[name]=sorted({n.module or '' for n in ast.walk(tree) if isinstance(n,ast.ImportFrom)}|{a.name for n in ast.walk(tree) if isinstance(n,ast.Import) for a in n.names})
dynamic=[dict(path=str(R.parent/'27-title-runtime/ogx_title_loader.py'),role='live_adapter.load_file at import; executed in focused tests'),dict(path=str(R.parent/'52-usb-topology/topology_check.py'),role='usb_target57.parser dynamic dependency; required membership, changed/omitted refusals; qualification itself parent accepted W57, not repeated'),dict(path='/home/roasted/.hermes/skills/xemu-development-workflow/scripts/roqfatx.py',role='live_preflight dynamic disk reader; stubbed external block-device boundary, not executed here'),dict(path='/home/roasted/Desktop/Xbox/LAN_Stats/tools/xemu/qmp.py',role='imported QMP client; no connection'),dict(path='/home/roasted/Desktop/Xbox/LAN_Stats/tools/xemu/gdbrsp.py',role='imported RSP client; no connection')]
baseline=(O/'baseline-parent_launch.py').read_text();current=(R/'parent_launch.py').read_text()
(O/'production.diff').open('x').write(''.join(difflib.unified_diff(baseline.splitlines(True),current.splitlines(True),fromfile='before/parent_launch.py',tofile='after/parent_launch.py')))
closure=dict(kind='lease-independent tested-source candidate; NOT parent source confirmation or final SOURCE-MANIFEST',files=files,required_membership=sorted(required),actual_imports=imports,static_import_edges=edges,dynamic_dependencies=dynamic,frozen_inputs=frozen,green_receipts=receipts,fixture_files=fixtures,synthetic_symlinks=links,synthetic_positive_manifests=positive,test_enumeration=enumerations[0],tests_per_run=103,normal_runs=[json.loads((p/'receipt.json').read_text()) for p in runs],native_commands=0,unfinished_edits=[],not_executed=['historical/shared combined suites (parent-owned)','actual stopped preflight, guard and command inspection','native parity/UI, real USB qualification, title execution and responsive capture','live admission and controller/game-input proof'],historical_inventory=dict(path=str(R/'post-entry-49/SOURCE-MANIFEST.json'),sha256=w.MANIFEST49),parent_accepted_USB_provenance=dict(path=str(O.parent/'57-usb-runtime-qualification/PARENT-INDEPENDENT-ACCEPTANCE.json'),sha256=sha(O.parent/'57-usb-runtime-qualification/PARENT-INDEPENDENT-ACCEPTANCE.json')))
save(S/'TESTED-SOURCES.json',closure)
save(S/'GREEN-RECEIPTS.json',dict(receipts=receipts,tests_per_run=103,source_hashes={str(R/'parent_launch.py'):sha(R/'parent_launch.py'),str(R/'tools/test_active_slot59.py'):sha(R/'tools/test_active_slot59.py')},all_passed=True,exit_code=0,synthetic=True))
summary='Offline slot59 implementation verified: 103 focused production-chain fixture methods GREEN twice, unchanged final tested bytes, no native commands or live authority. Parent combined/default checks and real stopped admission remain required.'
status=dict(state='offline_implementation_verified_parent_acceptance_pending',summary=summary,tests_per_run=103,normal_cli_runs=2,receipts=receipts,source_closure=str(S/'TESTED-SOURCES.json'),source_closure_sha256=sha(S/'TESTED-SOURCES.json'),protected_inputs_unchanged_except_owned_launcher=True,unfinished_edits=[],native_commands=0,live_authorized=False,remaining_live_allowance=0,parent_handoff=str(O/'PARENT-HANDOFF.md'))
(O/'status.json').write_text(json.dumps(status,indent=2)+'\n')
(O/'shortsummary.txt').write_text(summary+'\n')
report='''Offline implementation verified; parent acceptance and live admission NOT issued.

Final normal CLI: /usr/bin/python3 -B -m unittest -v test_active_slot59
Cwd: R/tools. 103 unique methods GREEN twice; separate atomic verified1-opz2c3au and verified2-l42gerr7 roots. Each has exact argv/cwd/environment, raw stdout/stderr, exit, and source hashes. Final bytes match both runs; no unfinished source edits. New cache prefixes prevent inherited pyc use. Source-only fixtures never import inherited shared tests or compile/rebuild anything.

Production change only R/parent_launch.py. Adds the canonical post-entry-59 recipe, budgets 4/2/1/5, immutable spent49 predecessor paths/digests, canonical future receipt digest anchor without baking a new lease hash, attested private-display validation/socket derivation, required source membership including W52 and USB source proof, pre-issue freshness, pinned authority rereads and consumed claim/handle validation. Normal main dispatches directly to existing FreshEffects initial selection. Recovery.py and runtime_session.py are byte-identical, as are all other protected sources/evidence.

Fixtures exercise original main -> runtime_session -> FreshEffects -> ActiveSlot -> original stopped_gates -> inherited LiveEffects.install -> run_session cleanup. External disk/USB/process/socket/RAM/UI effects are synthetic. Staged --check/--command/--active-slot are separate from launch: a canonical receipt/binding is still required, but source confirmation/new_launch_authorized are not; actual issue requires both. Normal real coordinator with HERMES_SESSION_ID unset refuses before environment/discovery/claim; current owner not modified or impersonated. Positive fixture uses independently invented owner/session/process/route at normal mirror-relative coordinator path. One initial selector is asserted; subsequent calls carry the selected slot.

Coverage includes path alias/symlink/traversal, stale descendants/handle, wrong authority/owner/session/process/model/provider/billing/reasoning/unit/budgets, absent/placeholder/mismatched digest, missing receipt/manifest/confirmation, malformed source confirmation/token proof, omitted mandatory dependencies/changed helpers, spent/duplicate/interrupted claim, mid-gate and post-claim rebind, consumed cleanup at zero allowance, ambiguous issue/no retry, preserved capture and quit errors. Failure receipts and final synthetic positive/negative manifests are retained under each run. RED red-6rv3gmkg is the original production resolver refusing the slot59 path; fixture repair failures/checkpoints also remain retained.

TESTED-SOURCES.json is lease-independent candidate closure only. It records final source bytes, required membership, actual imports, dynamic loads, frozen pins, fixtures and GREEN receipts; it does not authorize anything. Protected inventory and production.diff are in O. Historical module/loader/XBE pins and roles are unchanged.

Limits: no full shared or default adapter suites reexecuted here; parent owns them. No actual display/device, external preflight/guard, native launch, attachment, title input, service/build/deploy/upload or physical console action. Native parity/UI are stubbed external effects in this lane, not end-to-end proof for an arbitrary display: inherited frozen parity/UI still contain :2. Parent must check compatibility of its actual attested environment and HOLD if incompatible; no owned-scope edits to those accepted files were made. No title RAM footprint change. No actual authority/coordinator/lease/claim/source confirmation created in S or root binding.
'''
(O/'REPORT.md').write_text(report)
save(O/'CLOSURE-VERIFICATION.json',dict(source_files=len(files),required_members=len(required),fixture_files=len(fixtures),unique_methods=len(enumerations[0]),runs=2,protected_unexpected_changes=unexpected,final_tested_bytes_match=True,closure_sha256=sha(S/'TESTED-SOURCES.json')))
print(json.dumps(status,indent=2));print('closure counts',len(files),len(required),len(fixtures))
