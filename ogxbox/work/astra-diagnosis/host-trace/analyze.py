from pathlib import Path
import re,json,hashlib,collections,subprocess
R=Path(__file__).resolve().parent
lines=(R/'capture.log').read_text().splitlines()
g=(R/'guest.log').read_text(); start=g.rfind('SYNTH log=')
latest=g[start:]; (R/'guest-latest.log').write_text(latest)
host=[{'line':i+1,'text':s} for i,s in enumerate(lines) if 'usb_host_req_' in s]
(R/'host-requests.json').write_text(json.dumps(host,indent=2))
intervals=[]
for i,s in enumerate(lines):
    if 'usb_host_req_data' not in s or 'in 1, ep 2, size 64' not in s: continue
    end=next((j for j in range(i+1,len(lines)) if 'usb_host_req_complete' in lines[j]),None)
    if end is None: continue
    if any('usb_host_req_control' in t or 'usb_host_req_data' in t for t in lines[i+1:end]): continue
    blocked=[]
    for j in range(i+1,end):
        if 'bytes out ' in lines[j]:
            k=next((k for k in range(j+1,min(j+5,end)) if 'too_many_pending ep=2' in lines[k]),None)
            if k is not None: blocked.append({'td_line':j+1,'pending_line':k+1,'td':lines[j]})
    intervals.append({'in_submit':i+1,'in_complete':end+1,'out_blocked_visits':len(blocked),'first':blocked[:1],'last':blocked[-1:]})
summary={'trace_bytes':(R/'capture.log').stat().st_size,'trace_lines':len(lines),'host_requests':host,'in_intervals':intervals,'latest_guest':{'RX':len(re.findall(r'^RX ',latest,re.M)),'TXDONE':len(re.findall(r'^TXDONE ',latest,re.M)),'STATE':len(re.findall(r'^STATE ',latest,re.M))},'hashes':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [R/'capture.log',R/'guest.log',R/'guest-latest.log',R/'before.toml',R/'after-exit.toml']}}
(R/'analysis.json').write_text(json.dumps(summary,indent=2))
print(json.dumps({k:v for k,v in summary.items() if k!='host_requests'},indent=2));print(latest)
for a,b in [(41845,41875),(52330,52385)]:
    (R/f'excerpt-{a}-{b}.txt').write_text('\n'.join(f'{n}: {lines[n-1]}' for n in range(a,b+1)))
