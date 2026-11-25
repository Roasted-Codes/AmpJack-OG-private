#!/usr/bin/env python3
"""Mechanical W42 read-only source import into W45; no runtime calls."""
import sys
sys.dont_write_bytecode = True
from pathlib import Path
import hashlib
import json
ROOT = Path(__file__).resolve().parent
OLD = ROOT.parent/'42-enum-observer'
records = {}
for name in ('runtime_session','live_adapter','live_preflight','enum_watch','ui','capture_startup_failure','test_live_adapter','test_observer'):
    source = OLD/'tools'/(name+'.py')
    text = source.read_text()
    records[name] = {'source':str(source),'sha256':hashlib.sha256(source.read_bytes()).hexdigest()}
    text = text.replace('W42','W45').replace('w42','w45')
    text = text.replace('import json\n','import sys\nsys.dont_write_bytecode=True\nimport json\n',1)
    if name == 'enum_watch':
        text = text.replace("a=ap.parse_args(); plan=prepare()", "a=ap.parse_args(); plan=prepare()\n    for output in (a.log, a.pins_out):\n        if output is not None: need(output.resolve().is_relative_to(ROOT), 'output outside W45')")
    if name == 'live_adapter':
        text = text.replace("p=ROOT/name; p.parent.mkdir(parents=True,exist_ok=True)", "p=ROOT/name; obs.need(p.resolve().is_relative_to(ROOT),'output outside W45'); p.parent.mkdir(parents=True,exist_ok=True)")
    if name == 'live_preflight':
        text = text.replace("lease=json.loads(a.LEASE.read_text()); guest=Path(lease['fresh_clone'])", "sys.path.insert(0,str(R))\nfrom parent_launch import receipt, environment\nlease=receipt(); guest=Path(lease['fresh_clone'])\nenvironment(lease)")
    if name == 'ui':
        text = text.replace("env=dict(os.environ,**json.loads(Path(lease['environment_file']).read_text()),LD_LIBRARY_PATH='/home/roasted/.local/lib')", "sys.path.insert(0,str(R))\nfrom parent_launch import receipt, environment\nlease=receipt()\nenv=environment(lease)\nenv['LD_LIBRARY_PATH']='/home/roasted/.local/lib'")
    target = ROOT/'tools'/(name+'.py')
    if target.exists():
        raise RuntimeError('refuse overwrite '+str(target))
    target.parent.mkdir(exist_ok=True)
    target.write_text(text)
(ROOT/'source-port.json').write_text(json.dumps(records,indent=2)+'\n')
(ROOT/'continuation').mkdir(exist_ok=True)
(ROOT/'tmp').mkdir(exist_ok=True)
print('Copied eight read-only sources into W45; runtime not executed')
