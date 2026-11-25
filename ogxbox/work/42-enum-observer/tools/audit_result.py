#!/usr/bin/env python3
"""Local evidence cross-check; never talks to a guest or writes outside W42."""
import hashlib
import json
import os
from pathlib import Path
import enum_watch as e
R=e.ROOT
p=e.prepare()
summary=json.loads((R/'evidence/test-results.json').read_text())
positive=next(x for x in summary['cli_cases'] if x['name']=='positive')
log=Path(positive['command'][positive['command'].index('--log')+1])
rows=[json.loads(l) for l in log.read_text().splitlines()]
stops=[r for r in rows if r['event']=='stop']
watch=next(r for r in stops if r.get('writer')==0x4166b5)
raw=bytes.fromhex(watch['raw_snapshot']['memory'][0]['hex'])
assert int.from_bytes(raw[0x80:0x84],'little')==watch['current']==0
stock=e.DUMP.read_bytes(); assert stock[0x4166b5-0x412000:0x4166bb-0x412000].hex()=='891d30094900'
assert watch['eip']==0x4166bb and watch['fixture']
result={'offline_cli_cases':len(summary['cli_cases']), 'pins':len(p['pins']),
        'unique_breakpoints':len({(x['relative'],x['offset']) for x in p['pins']}),
        'decisive_fixture_check':{'log':str(log),'seq':watch['seq'],'post_write_pc':'0x4166bb','writer':'0x4166b5','writer_bytes':'891d30094900','current_raw':raw[0x80:0x84].hex(),'NOT_LIVE':True},
        'timer_calls':[{k:v for k,v in x.items() if k!='asm'} for x in p['pins'] if x['event'].startswith('timer_')],
        'writers':{hex(k):hex(v) for k,v in p['writers'].items()},
        'module_sites':{hex(k):v for k,v in e.MODULE.items()},
        'model':'openai-codex/gpt-6.1-sol','live_evidence':False,
        'runtime_precondition_source':str(R.parent/'41-astra-install-plan/PARENT-DISPATCH-ACCEPTED.json'),
        'runtime_blocker':json.loads((R.parent/'41-astra-install-plan/PARENT-DISPATCH-ACCEPTED.json').read_text())['runtime42_preflight'],
        'input_hashes':{str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in (e.DUMP,e.ELF,e.LAYOUT,e.XBE)},
        'authored_files':{str(f.relative_to(R)):hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted((R/'tools').glob('*.py'))}}
(R/'evidence/audit.json').write_text(json.dumps(result,indent=2)+'\n')
for f in (R/'tools').glob('*.py'): f.chmod(f.stat().st_mode|0o111)
print(json.dumps({k:result[k] for k in ('offline_cli_cases','pins','unique_breakpoints','writers','runtime_blocker','live_evidence')},indent=2))
