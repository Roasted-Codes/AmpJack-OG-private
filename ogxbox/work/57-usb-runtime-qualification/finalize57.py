"""Final isolated focused executions and mechanical evidence aggregation."""
import ast,difflib,hashlib,json,os,pathlib,re,subprocess,tempfile
D=pathlib.Path(__file__).resolve().parent
T=D.parent/'45-x11-runtime-capture/tools'
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def dump(path,value):path.write_text(json.dumps(value,indent=2)+'\n')
runs=[]
for label in ('accepted-green1','accepted-green2'):
    wrapper=pathlib.Path(tempfile.mkdtemp(prefix='wrapper-',dir=D))
    env=dict(os.environ,PYTHONPYCACHEPREFIX=str(wrapper/'pycache'),TMPDIR=str(wrapper/'tmp'),XDG_CACHE_HOME=str(wrapper/'cache'))
    for key in ('PYTHONPYCACHEPREFIX','TMPDIR','XDG_CACHE_HOME'):pathlib.Path(env[key]).mkdir()
    argv=['/usr/bin/python3','-B',str(D/'run_focused57.py'),label]
    result=subprocess.run(argv,env=env,capture_output=True,text=True)
    (wrapper/'stdout.log').write_text(result.stdout);(wrapper/'stderr.log').write_text(result.stderr)
    dump(wrapper/'execution.json',dict(argv=argv,exit=result.returncode))
    assert result.returncode==0,result.stdout+result.stderr
    run=pathlib.Path(result.stdout.splitlines()[0]);execution=json.loads((run/'execution.json').read_text())
    log=(run/'stderr.log').read_text()
    methods=re.findall(r'^(test_\w+) \(test_usb_target57.InstallTests\.\w+\) \.\.\. ok$',log,re.M)
    count=int(re.search(r'Ran (\d+) tests',log)[1])
    assert len(methods)==len(set(methods))==count
    assert execution['exit']==0
    for name,digest in execution['tested_sha256'].items():assert sha(T/name)==digest
    rows=[]
    for method in methods:
        fixtures=list(run.glob(method+'-*'));assert len(fixtures)==1,(method,fixtures)
        fixture=fixtures[0];proof_path=fixture/'usb-topology.json'
        proof=json.loads(proof_path.read_text()) if proof_path.exists() else None
        rows.append(dict(method=method,result='PASS',fixture=str(fixture),
                         evidence=str(proof_path) if proof else None,
                         failed_stage=proof.get('failed_stage') if proof else None,
                         verdict=proof.get('verdict') if proof else None,
                         caller_result=str(fixture/'caller-result.json') if (fixture/'caller-result.json').exists() else None,
                         mutated_receipt=str(fixture/'tampered-receipt.json') if (fixture/'tampered-receipt.json').exists() else None))
    dump(run/'negative-matrix.json',rows)
    runs.append(dict(path=str(run),methods=count,exit=0,execution=execution))
    print(label,run,'methods',count,'exit',execution['exit'])
assert runs[0]['methods']==runs[1]['methods']
pins=json.loads((D/'PARENT-PROTECTED-INPUTS.json').read_text())
protected={p:dict(expected=h,actual=sha(pathlib.Path(p))) for p,h in pins.items()}
for p,row in protected.items():
    if pathlib.Path(p)!=T/'runtime_effects.py':assert row['expected']==row['actual'],p
assert sha(D/'runtime_effects.preimage.py')==pins[str(T/'runtime_effects.py')]
old=(D/'runtime_effects.preimage.py').read_text();new=(T/'runtime_effects.py').read_text()
def methods(text):
    cls=next(x for x in ast.parse(text).body if isinstance(x,ast.ClassDef) and x.name=='LiveEffects')
    return {x.name:x for x in cls.body if isinstance(x,ast.FunctionDef)}
a,b=methods(old),methods(new)
unchanged=[]
for name in a:
    if name not in ('install','authenticate'):
        assert ast.dump(a[name])==ast.dump(b[name]),name
        unchanged.append(name)
assert [ast.dump(x) for x in a['authenticate'].body]==[ast.dump(x) for x in b['authenticate'].body[:-1]]
assert [ast.dump(x) for x in a['install'].body[:3]]==[ast.dump(x) for x in b['install'].body[:3]]
assert ast.dump(a['install'].body[-1])==ast.dump(b['install'].body[-1])
dump(D/'protected-after.json',dict(inputs=protected,unchanged_methods=unchanged,authentication_prefix_unchanged=True,allocation_install_and_final_guards_unchanged=True))
diff=''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='runtime_effects.preimage.py',tofile='runtime_effects.py'))
for name in ('usb_target57.py','test_usb_target57.py'):
    diff+=''.join(difflib.unified_diff([], (T/name).read_text().splitlines(True),fromfile='/dev/null',tofile=name))
(D/'production.diff').write_text(diff)
source=D.parent/'astra-emu-fix/source/hw/usb/host-libusb.c'
dump(D/'tested-source-hashes.json',{str(p):sha(p) for p in [T/'runtime_effects.py',T/'usb_target57.py',T/'test_usb_target57.py',source,source.parent/'bus.c',pathlib.Path('/home/roasted/Desktop/Xbox/LAN_Stats/tools/xemu/qmp.py')]})
# Manifest covers every retained run, including the original intended RED.
artifacts={str(p.relative_to(D)):sha(p) for child in D.iterdir() if child.is_dir() for p in child.rglob('*') if p.is_file() and not p.is_symlink()}
dump(D/'run-artifacts-sha256.json',artifacts)
status=json.loads((D/'status.json').read_text())
status.update(state='OFFLINE_TESTED_ONLY_PARENT_ACCEPTANCE_PENDING',focused_runs=runs,
              intended_red=dict(path=str(D/'red-67niozq9'),exit=1,reason='RuntimeError not raised on original wrong-device speed acceptance'),
              protected_inputs_unchanged_except_owned_effects=True,partial_or_untested_code_edits=[],
              physical_input='untested',game_input='untested',live_launch_grant=False,
              combined_suites='parent-owned; not run by this worker',native_commands_used=0)
dump(D/'status.json',status)
previous=(D/'REPORT.md').read_text()
(D/'CHECKPOINT-HISTORY.md').write_text(previous)
report='''W57 USB runtime-qualification repair — OFFLINE TESTED ONLY

Implemented in the actual inherited LiveEffects.install path. Parent acceptance remains pending. No controller connection, game-input qualification, live capture, guest/native command, second QMP connection or launch authority is claimed. Four prior commands remain spent, zero remaining. W55 wrapper EXITED1 cause remains unknown; its substantive plan was parent-accepted, not rerun. W56 completion is accepted as supplied; W56 and test_watch_writer51.py were not read or modified.

Acceptance evidence

Intended production RED: red-67niozq9, exit 1, RuntimeError not raised. This replay reached actual install and accepted the saved target at 1.5 Mb/s because a neighbor had 12 Mb/s. It was not an import or fixture failure. runtime_effects.preimage.py and pre-edit-check.json preserve the production preimage and verified pins before edits; both new module paths were absent.

Final focused runs, each using /usr/bin/python3 -B -m unittest -v test_usb_target57 from R/tools, with independent atomic D directories and fresh PYTHONPYCACHEPREFIX, TMPDIR and XDG_CACHE_HOME:
'''
for run in runs:report+=f"  {run['path']}: {run['methods']} unique methods, exit {run['exit']}\n"
report+='''
Each execution.json records exact argv, cwd, environment roots, exit and tested-source hashes. Raw stdout/stderr, per-case ordinary-directory fixtures and USB receipts are retained. negative-matrix.json joins every passing method to actual evidence/refusal stage, caller result or tampered-receipt fixture. Earlier checkpoint and green runs remain retained, not overwritten. run-artifacts-sha256.json binds all retained run files. Two blocked shell inline-script attempts executed nothing; ordinary on-disk Python scripts provided the permitted alternative.

Production behavior and boundaries

The same authenticated QMP client sends one device_add with precisely driver=usb-host, id=pt_pad3, bus=usb-bus.1, port=1.4 and validated physical hostbus/hostaddr. No vendor/product/hostport/hostdevice/fd filters are sent. Only the real selected client's returned empty dictionary is success; None, wire envelopes, malformed objects and raised find/open/attach errors refuse. No resume, step, retry, guest-running fallback or extra client was introduced.

The pinned source direct-address branch synchronously finds and opens the device, maps speed with compatibility handling, and attaches before successful realization; failure closes/clears. Thus this interval supports source-implied open-at-add, not an observed libusb handle. Qtree independently supplies attached-at-sample. Neither establishes future health or input. Source-shaped fixtures contain explicit synthetic product labels; these are never interpreted as descriptors. Physical VID/PID comes only from directory-relative raw attributes, separate from zero qtree filter defaults.

A held read-only directory FD records fstat device/inode identity and resolved physical path. Fresh path/stat plus directory-relative attributes bracket add and post queries; ordinary directory replacement with identical text, retargeting/removal and attribute/address changes refuse. The existing preflight schema supplies path/bus/address/node/speed, not a historical inode or serial. The identity proof begins at the held-directory observation and ends at the post-sample observation. It is intentionally not a universal future identity guarantee. No real sysfs, USB device node, usbfs or ioctl was accessed. Device-node text is compared only, never opened.

The unchanged W52 pure parser/check API is hash-pinned and reused without CLI effects. Structural join requires unique pt_pad3, pci.0 / 00:02.0 OHCI, usb-bus.1 busnr 1, attached hub 1, full path 1.4, driver/hostbus/hostaddr and matching guest address/product/speed listing row. Guest address is distinct from hostaddr. Full-speed acceptance additionally requires exact matching host 12 and target 12, attached target and direct successful add. The frozen historical raw listing/qtree remain a negative, with useful 1.5-speed/unattached target observations retained; no live receipt was retrofitted onto historical files.

Receipts retain compatible before/after/qtree/bus/address/sysfs, plus pre-tree, raw physical snapshots, capture ID, authenticated invocation/native identity, real wall and monotonic observation bounds, ordering and hashes. Raw replies and client results are recorded rather than reconstructed wire envelopes. On failure the exact stage/exception and completed raw observations remain; failed external observations include actual timing bounds. Missing later observations remain absent/unknown. Canonical SHA256 bindings detect accidental mixing/tampering, not a dishonest evidence issuer.

Real runtime_session.run_session(existing=True), with inherited install and stub external boundaries, refuses at install_and_topology, obtains context, reauthenticates before quit, closes both clients and verifies release; no observe/capture/takeover occurs. Quit-error preservation is separately asserted and saved in caller-result.json with caller-boundary-order.json. Allocation, installation, all other methods, authentication's existing checks and final native/entry guards are AST-checked unchanged. protected-after.json verifies every protected input except the intentionally owned runtime_effects edit; historical raw hashes, runner, W52 and accepted W54 inputs remain exact. production.diff and tested-source-hashes.json provide the tested patch and pins.

Coverage includes independent raw join/filter/collision/speed negatives, original saved capture, direct result failures, unknown/missing/low physical speed, nondefault validated address, held-instance replacement, missing post-add attributes, denied post-query, identity/entry bracket failures, directory-FD closure, receipt session/order/time/hash/raw/tuple corruption and forged-handle non-rescue. No shared/default/legacy observer suites were imported or executed; parent owns combined normal suites/default paths. Import inspection found only definitions/constants and the existing read-only loader import; lease constructors, layout compilation and shared evidence writers were not invoked. Syntax checks passed; no standalone static typechecker run is claimed (editor inference warnings on untyped fixture attributes are not runtime test results).

No partial or untested code edits remain relative to the final focused suite. Actual physical cold behavior, game input, reconnect/coexistence, XBMC exact package and 64 MiB operation remain unverified future gates. Parent owns acceptance, process/card closure and notifications.
'''
(D/'REPORT.md').write_text(report)
print('protected inputs and unchanged guard AST verified; report/status/diff/matrices saved')
