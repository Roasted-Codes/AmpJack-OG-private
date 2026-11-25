"""Read-only W45 resumed admission audit. Does not import runtime code."""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import time

OUT = Path(__file__).resolve().parent
W = OUT.parent.parent
C = W.parent / 'sol-audit/COORDINATOR_STATE.json'
def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()
def frozen(path):
    raw = path.read_bytes()
    return {'path': str(path), 'sha256': hashlib.sha256(raw).hexdigest(), 'data': json.loads(raw)}
state = frozen(C)
claim = frozen(W/'runtime-claim.json')
accepted = frozen(W/'continuation-2/recovery/PARENT-ACCEPTED-DIAGNOSTIC.json')
final = frozen(W/'continuation-2/recovery/final-verification.json')
session = os.environ['HERMES_SESSION_ID']
with sqlite3.connect('file:/home/roasted/.hermes/profiles/halo2-specialist/state.db?mode=ro', uri=True) as db:
    db.row_factory = sqlite3.Row
    usage = [dict(r) for r in db.execute('SELECT session_id, model, billing_provider, billing_mode, api_call_count, input_tokens, output_tokens FROM session_model_usage WHERE session_id=?', (session,))]
b = state['data']['runtime_binding']
commands = [
    ['systemctl','--user','show','ampjack-parent45-devkit.service','--property=LoadState,ActiveState,SubState,MainPID,InvocationID','--no-pager'],
    ['ss','-ltnpH','sport = :1242'],
    ['ss','-xlpnH'],
]
checks = []
for command in commands:
    p = subprocess.run(command, text=True, capture_output=True)
    stdout = p.stdout
    if command == commands[-1]:
        stdout = '\n'.join(line for line in stdout.splitlines() if str(W.parent/'42-enum-observer/parent-prepared-guest/runtime/qmp.sock') in line)
    checks.append({'command':command, 'returncode':p.returncode, 'stdout':stdout, 'stderr':p.stderr})
source_comparison = {name: {'expected':sha, 'actual':digest(W/name)} for name, sha in final['data']['final_production_hashes'].items()}
result = {
    'epoch': time.time(), 'card':'t_af7623e9', 'session':session,
    'route_usage':usage, 'reasoning_medium_verified':False,
    'canonical_snapshot':state, 'existing_claim_snapshot':claim,
    'parent_accepted_snapshot':accepted, 'prior_final_verification':final,
    'receipt_sha256':digest(W/'PARENT-RUNTIME-LEASE.json'),
    'identity_manifest_sha256':digest(W/'PARENT-TITLE-IDENTITIES.json'),
    'production_source_comparison':source_comparison,
    'all_production_sources_unchanged_since_prior_final':all(v['expected']==v['actual'] for v in source_comparison.values()),
    'resource_checks':checks,
    'binding_matches_executing_session':b.get('session')==session,
    'binding_is_verified':b.get('state')=='verified',
    'new_launch_authorized':b.get('new_launch_authorized'),
    'remaining_commands':b.get('remaining_commands'),
    'new_claims':0, 'new_launch_commands':0, 'new_runtime_clients':0,
    'verdict':'PRE_ADMISSION_BLOCKED',
    'blockers':['canonical binding closed_verified for previous session, not executing session', 'canonical new_launch_authorized=false and remaining_commands=0; immutable original claim already spent', 'medium reasoning not independently attested in usage rows'],
    'historical_test_result':'Parent accepted 46 methods; not replayed or counted as new changed-path tests',
    'restart':'Parent must reconcile stale task dispatch with current Astra admission decision. No claim deletion, receipt reissue, guest retry, or canonical edit by this worker.'
}
with (OUT/'admission-evidence.json').open('x') as stream:
    json.dump(result, stream, indent=2)
print(json.dumps({k:result[k] for k in ('verdict','binding_matches_executing_session','binding_is_verified','new_launch_authorized','remaining_commands','all_production_sources_unchanged_since_prior_final','new_claims','new_launch_commands')}, indent=2))
