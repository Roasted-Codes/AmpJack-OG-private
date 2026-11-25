"""Aggregate retained diagnostic evidence; no runtime protocol clients."""
from pathlib import Path
from collections import Counter
import hashlib,json,struct,sys
sys.dont_write_bytecode=True
W=Path('/home/roasted/Desktop/Xbox/AmpJack-OG/ogxbox/work');R=W/'45-x11-runtime-capture';S=R/'post-entry-59';O=W/'59-sol-bounded-preparation';OUT=O/'live-run/preissue-97zbuuox';L=S/'live'
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def save(n,obj):
    with (OUT/n).open('x') as f:json.dump(obj,f,indent=2);f.write('\n')
install=json.loads((L/'install-verified.json').read_text());hooks=[]
for name,site in install['sites'].items():
    readback=install['result']['sites'][name];raw=bytes.fromhex(readback)
    target=(site['va']+5+struct.unpack('<i',raw[1:5])[0])&0xffffffff
    hooks.append(dict(name=name,site=hex(site['va']),expected=site['expect'],readback=readback,target=hex(target),expected_target=hex(site['target']),bytes_match=readback==site['expect'],target_match=target==site['target']))
assert len(hooks)==7 and all(h['bytes_match'] and h['target_match'] for h in hooks)
save('SEVEN-HOOK-READBACKS.json',hooks)
sys.path[:0]=[str(R/'tools'),str(R)]
import usb_target57 as usb
import live_preflight as pre
receipt=json.loads((L/'usb-topology.json').read_text());qualification=usb.validate(receipt)
request=next(e for e in receipt['events'] if e['stage']=='request')['value']
physical=[dict(stage=e['stage'],directory_identity=e['value']['directory_identity'],resolved=e['value']['resolved'],values=e['value']['values']) for e in receipt['events'] if e['stage'].startswith('physical_')]
usb_summary=dict(qualification=qualification,request=request,physical_samples=physical,event_stages=[e['stage'] for e in receipt['events']],receipt_sha256=sha(L/'usb-topology.json'),same_physical_directory_instance=len({json.dumps(x['directory_identity'],sort_keys=True) for x in physical})==1)
save('USB-QUALIFICATION-SUMMARY.json',usb_summary)
rows=[json.loads(line) for line in (L/'ordered-trace.jsonl').read_text().splitlines()]
assert [r['seq'] for r in rows]==list(range(1,len(rows)+1))
keys=('seq','event','eip','stop_reason','events','writer_kind','writer','current','device','stage','marker','attribution','reason','error','hold','local_observer_qualified','stored_value','writer_ea','writer_width')
compact=[{k:(hex(r[k]) if k in ('eip','writer','current','writer_ea') and isinstance(r[k],int) else r[k]) for k in keys if k in r} for r in rows]
trace=dict(rows=len(rows),event_counts=dict(Counter(r['event'] for r in rows)),sequence_contiguous=True,rows_summary=compact,last_rows=compact[-15:])
save('ORDERED-TRACE-SUMMARY.json',trace)
lease=json.loads((S/'PARENT-RUNTIME-LEASE.json').read_text())
release=pre.resources(lease);release['no_process_disk_listener_or_socket']=not any(release[k] for k in ('processes','disk_fds','tcp','qmp_listeners','qmp_path_exists')) and 'ActiveState=active' not in release['unit'] and 'ActiveState=activating' not in release['unit']
save('INDEPENDENT-RELEASE.json',release)
manifest=json.loads((S/'SOURCE-MANIFEST.json').read_text());mismatch={p:sha(p) for p,h in manifest['files'].items() if sha(p)!=h}
protected=json.loads((O/'PROTECTED-INPUTS-AFTER.json').read_text());protected_mismatch={p:sha(p) for p,pin in protected.items() if sha(p)!=pin['after']}
save('POST-RUN-SOURCE-PROTECTED.json',dict(files_checked=len(manifest['files']),mismatches=mismatch,protected_mismatches=protected_mismatch,lease_sha256=sha(S/'PARENT-RUNTIME-LEASE.json'),manifest_sha256=sha(S/'SOURCE-MANIFEST.json'),note='No disk-image rehash or offline qcow operation; normal authorized guest writes are not source drift'))
print(json.dumps(dict(hooks=hooks,install_status=install['result']['status'],base=hex(install['base']),module=hex(install['module']),usb=usb_summary,trace_last=trace['last_rows'],trace_rows=len(rows),trace_event_counts=trace['event_counts'],independent_release=release,source_mismatches=mismatch,protected_mismatches=protected_mismatch),indent=2))
