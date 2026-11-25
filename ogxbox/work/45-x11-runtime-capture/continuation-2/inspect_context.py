import sys
sys.dont_write_bytecode=True
import hashlib, json, os
from pathlib import Path
R=Path(__file__).resolve().parents[1]
print('identity_hashes', {n:hashlib.sha256((R/n).read_bytes()).hexdigest() for n in ('PARENT-TITLE-IDENTITIES.json','PARENT-RUNTIME-LEASE.json')})
for root in (Path('/home/roasted/Desktop/Xbox/LAN_Stats/work/xemu'),R.parent/'35-loading-stop',R.parent/'33-title-input-repair'):
    print('kernel_candidates',str(root),[(str(p),p.stat().st_size) for p in root.rglob('*') if p.is_file() and p.suffix in ('.bin','.json') and ('kernel' in p.name.lower() or '800' in p.name)])
print('session',os.environ.get('HERMES_SESSION_ID'))
print('binding',json.loads((R.parent/'sol-audit/COORDINATOR_STATE.json').read_text()).get('runtime_binding'))
