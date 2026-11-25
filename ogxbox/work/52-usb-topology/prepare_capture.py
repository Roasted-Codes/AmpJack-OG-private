"""Bind saved evidence only; no emulator/device interaction."""
import json
import hashlib
from pathlib import Path
from topology_check import digest, text_hash, listing
O=Path(__file__).resolve().parent
W=O.parent
L=W/'45-x11-runtime-capture/post-entry-49/live'
def load(path): return json.loads(path.read_text())
raw=(L/'usb-topology.json').read_bytes(); capture=json.loads(raw)
assert digest(raw)=='da8a9ff7b31dc9190790a64a1d2b7bc15c34b78423e0440cb5ba7c547c05cab3'
native=load(L/'native-identity.json'); launch=load(L/'launch-handle.json')
journal=[json.loads(s) for s in (L/'final-invocation-journal.jsonl').read_text().splitlines()]
assert all(r['_BOOT_ID']==native['boot_id'].replace('-','') and int(r['_PID'])==native['pid'] and r['_SYSTEMD_INVOCATION_ID']==launch['invocation_id'] for r in journal)
trace=[json.loads(s) for s in (L/'ordered-trace.jsonl').read_text().splitlines()]
assert all(trace[0]['identity'][k]==native[k] for k in ('pid','start_ticks','boot_id','native_sha256'))
pre=load(L.parent/'preflight.json')
assert pre['usb'][0]['busnum']==str(capture['bus']) and pre['usb'][0]['devnum']==str(capture['address']) and pre['usb'][0]['sysfs']==capture['sysfs']
identity={k:native[k] for k in ('boot_id','pid','start_ticks')}
identity.update(capture_id='post-entry-49/device_add-pt_pad3/immediate-after',invocation_id=launch['invocation_id'],capture_sha256=digest(raw),listing_sha256=text_hash(capture['after']),qtree_sha256=text_hash(capture['qtree']),
 provenance='External offline binding of frozen topology artifact to saved native identity/journal and frozen runtime_effects.py:158-173 ordering; capture has no embedded timestamp or boot ID. Not an independently timestamped QMP transcript.')
selector=dict(capture_id=identity['capture_id'],controller='00:02.0',bus='usb-bus.1',busnr=1,port='1.4',node_id='pt_pad3',driver='usb-host',hostbus=3,hostaddr=7,vendorid=0x045e,productid=0x0b12)
for name,obj in (('capture-identity.json',identity),('target-selector.json',selector)):
 (O/name).write_text(json.dumps(obj,indent=2)+'\n')
rows=listing(capture['after'])
legacy=dict(predicate="'pt_pad3' in qtree and ('12 Mb/s' in after or '12 Mb' in after)",accepted='pt_pad3' in capture['qtree'] and ('12 Mb/s' in capture['after'] or '12 Mb' in capture['after']),accepting_rows=[r for r in rows if '12 Mb' in r['raw']],target_rows=[r for r in rows if r['node_id']=='pt_pad3'])
(O/'legacy-predicate-result.json').write_text(json.dumps(legacy,indent=2)+'\n')
sources=['hw/usb/bus.c','hw/usb/core.c','hw/usb/host-libusb.c','hw/usb/desc.c','hw/usb/dev-xbox-gamepad.c','ui/xemu-input.c','include/hw/usb.h','qom/object.c']
# Report source availability without assuming a gamepad implementation filename.
source_hashes={}
for name in sources:
 p=W/'astra-emu-fix/source'/name
 if p.is_file(): source_hashes[str(p)]=digest(p.read_bytes())
files=[L/'usb-topology.json',L/'native-identity.json',L/'launch-handle.json',L/'final-invocation-journal.jsonl',L/'ordered-trace.jsonl',L.parent/'preflight.json',W/'astra-emu-fix/REPORT.md',W/'36-reset-build/PARENT-VERIFICATION.json']
source_hashes.update({str(p):digest(p.read_bytes()) for p in files})
(O/'source-evidence-hashes.json').write_text(json.dumps(source_hashes,indent=2)+'\n')
print(json.dumps(dict(journal_rows=len(journal),journal_identity_consistent=True,preflight_epoch=pre['epoch'],sysfs_saved=pre['usb'],legacy_accepted=legacy['accepted'],native_row=[r for r in rows if r['node_id']=='gamepad_0'],target_row=legacy['target_rows'],sample_time='not embedded; relational before/device_add/after/qtree order only',trace_armed_monotonic_ns=trace[0]['monotonic_ns']),indent=2))
