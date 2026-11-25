"""Close an unspent admission refusal; no runtime or authority access."""
from pathlib import Path
import hashlib,json
O=Path(__file__).resolve().parents[1];R=O.parent/'45-x11-runtime-capture';S=R/'post-entry-59';OUT=O/'live-run';RUN=OUT/'attempt-1'
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
refusal=json.loads((RUN/'PREISSUE-REFUSAL.json').read_text())
manifest=json.loads((S/'SOURCE-MANIFEST.json').read_text())
verification=dict(lease_sha256=sha(S/'PARENT-RUNTIME-LEASE.json'),manifest_sha256=sha(S/'SOURCE-MANIFEST.json'),sources_checked=len(manifest['files']),fixture_files_checked=len(manifest.get('fixture_files',{})),test_receipts_checked=len(manifest['test_receipts']))
verification['lease_matches']=verification['lease_sha256']=='1e01a781bb4ad097320cd30797484282e705ad5a72a58ceada03b5c4bab57165'
verification['manifest_matches']=verification['manifest_sha256']=='899ca7a57d4824cca4cf175cd5f49c628d47eed9391fca38e4e4e10ba84806d3'
verification['mismatches']={p:sha(p) for group in ('files','fixture_files','test_receipts') for p,h in manifest.get(group,{}).items() if sha(p)!=h}
protected=json.loads((O/'PROTECTED-INPUTS-AFTER.json').read_text())
verification['protected_mismatches']={p:sha(p) for p,pin in protected.items() if sha(p)!=pin['after']}
verification['claim_exists']=(S/'runtime-claim.json').exists() or (S/'runtime-claim.json').is_symlink()
verification['live_exists']=(S/'live').exists() or (S/'live').is_symlink()
verification['slot_status']=json.loads((S/'status.json').read_text())
verification['slot_status_sha256']=sha(S/'status.json')
verification['no_canonical_or_tracking_repoll']=True
with (RUN/'UNSPENT-INVARIANTS.json').open('x') as f:json.dump(verification,f,indent=2);f.write('\n')
status=dict(state='UNSPENT_GATE_REFUSAL',first_missing_link='required parent live tracking file absent at admission',tracking_path=str(O/'PARENT-LIVE-TRACKING.json'),preissue_validator_exit=2,runner_started=False,runner_exit=None,worker_exit='parent intake; not inferred from helper',native_command_records_this_continuation=0,cumulative_actual_native_commands=4,authenticated_TU_entries=2,remaining_old_allowance=0,no_retry=True,no_polling=True,cleanup='not applicable: no runner/native/client created by continuation',verification=verification)
(OUT/'status.json').write_text(json.dumps(status,indent=2)+'\n')
text='''UNSPENT_GATE_REFUSAL

First missing link: required O/PARENT-LIVE-TRACKING.json was absent both at initial prerequisite read and at the single preissue admission validation. The exact FileNotFoundError/traceback is retained in attempt-1/PREISSUE-REFUSAL.json. No identity/route/grant was manufactured, no admission polling or retry was performed, and no normal runner was started. This is not a console, USB, title, permission or native-runtime failure.

Executed admission-only command: /usr/bin/python3 -B ogxbox/work/59-sol-bounded-preparation/live-run/verify-preissue.py
Cwd: /home/roasted/Desktop/Xbox/AmpJack-OG
Validator exit: 2. Runner exit: none (never started). Worker exit is separate, parent-owned intake; no worker success inferred from helper exit.

Final read-only evidence verification rehashed the final manifest/lease, complete source/fixture/test receipt maps and protected prior inputs, and recorded slot status and claim/live absence in attempt-1/UNSPENT-INVARIANTS.json. This verification is not a new admission attempt and does not re-read canonical/tracking to seek a later grant.

No new actual native command or durable claim. Cumulative actual command count remains4; authenticated TU entries remain2; old allowance remains0. No cold diagnostic, new invocation/native PID/start/hostboot, title/module/seven-hook/USB/watch/capture/input result exists for this continuation. Existing earlier stopped preflight is provenance only, not a live result. Cleanup: no runner/native/QMP/RSP/client ownership was acquired, so none left to release by this continuation. No launch, reset, warmboot, native retry, source/lease/manifest/confirmation/coordinator write, human contact, real console or upload.

Parent must supply and independently bind the missing actual live tracking/authority in a separate continuation before any one-command admission. No runtime or card closure is claimed.
'''
(OUT/'REPORT.md').write_text(text)
(OUT/'PHASE2-RESULT.md').write_text(text+'\nObserved final evidence:\n'+json.dumps(verification,indent=2)+'\n')
print(json.dumps(status,indent=2))
