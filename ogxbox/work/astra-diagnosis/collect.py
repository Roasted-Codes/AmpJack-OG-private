from pathlib import Path
import hashlib,json,subprocess,datetime
ROOT=Path(__file__).resolve().parents[3]
OUT=Path(__file__).resolve().parent
paths=['ogxbox/gipdriver/src/main.c','ogxbox/gipdriver/src/gipdrive.h','ogxbox/gipdriver/bin/AmpJackGip.exe','ogxbox/gipdriver/bin/default.xbe','ogxbox/gipdriver/bin/AmpJackGip.map','ogxbox/work/17-sol-execution/runtime/human-run.log','ogxbox/work/17-sol-execution/runtime/pad-run-2.log','ogxbox/research/usb/real-pad/config-descriptor-0b12.bin','/home/roasted/Desktop/Xbox/OXDK/xbox/xdk/lib/xapilib.lib','/home/roasted/Desktop/Xbox/OGH2_Server/reference/xemu/hw/usb/hcd-ohci.c','/home/roasted/Desktop/Xbox/OGH2_Server/reference/xemu/hw/usb/host-libusb.c','/home/roasted/Desktop/_Parked/halo2-system-link-bridge/devkit--xemu--0.8.136/xemu.AppImage']
manifest={}
for p in paths:
    f=ROOT/p;b=f.read_bytes();manifest[p]={'sha256':hashlib.sha256(b).hexdigest(),'bytes':len(b)}
(OUT/'input-hashes.json').write_text(json.dumps(manifest,indent=2)+'\n')
for name,start,end in [('submit',0x2ef3f,0x2f265),('open',0x30108,0x3027d),('addcomplete',0x2f9bb,0x2fb7b),('enum',0x2f462,0x30108),('transfer',0x3290b,0x32e50),('xid-open',0x2e088,0x2e3a0)]:
    cmd=['objdump','-d','-Mintel',f'--start-address={start}',f'--stop-address={end}',str(ROOT/'ogxbox/gipdriver/bin/AmpJackGip.exe')]
    r=subprocess.run(cmd,text=True,capture_output=True)
    (OUT/(name+'.disasm.txt')).write_text('COMMAND: '+' '.join(cmd)+'\n'+r.stdout+r.stderr)
app=Path(paths[-1]).read_bytes(); offsets=[];i=0
while True:
    i=app.find(b'hsqs',i)
    if i<0:break
    if app[i+28:i+30]==b'\x04\x00':offsets.append(i)
    i+=4
print(json.dumps({'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'hashes':manifest,'squashfs_candidates':offsets},indent=2))
