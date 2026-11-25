#!/usr/bin/env python3
"""Cold-copy the existing devkit for one patched-USB experiment; never boots."""
import hashlib,json,os,shutil,subprocess,tomllib
from pathlib import Path
ROOT=Path(__file__).resolve().parent
PRIMARY=Path('/home/roasted/Desktop/_Parked/halo2-system-link-bridge/devkit--xemu--0.8.136')
GUEST=ROOT/'guest'
ARTIFACT=ROOT.parent/'astra-emu-fix/artifact/xemu'
PIN='cb72610807d242f1b13eebace7f7049f8e57b9ee7e84b1799a6d77fc8b5f865c'
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for block in iter(lambda:f.read(8*1024*1024),b''):h.update(block)
 return h.hexdigest()
for p in Path('/proc').iterdir():
 if not p.name.isdigit():continue
 try:e=(p/'exe').readlink()
 except OSError:continue
 assert not(e.name.lower()=='xemu' or 'xemu.appimage' in e.name.lower() or e.name.lower().startswith('qemu-system')),f'Existing emulator {p.name}'
assert sha(ARTIFACT)==PIN
assert PIN in json.loads((Path.home()/'.local/share/xemu-safety/trusted-executables.json').read_text())['sha256']
assert not GUEST.exists(),'Do not overwrite an existing experiment'
GUEST.mkdir()
source_config=(PRIMARY/'xemu.toml').read_bytes()
cfg=tomllib.loads(source_config.decode())
manifest={'primary':str(PRIMARY),'guest':str(GUEST),'primary_config_sha256':sha(PRIMARY/'xemu.toml'),'copied':{}}
for name in list(cfg['sys']['files'].values())+['.start-xemu.py']:
 assert name and Path(name).name==name
 src=PRIMARY/name;dst=GUEST/name
 subprocess.run(['cp','--reflink=auto','--sparse=always','--preserve=mode,timestamps',str(src),str(dst)],check=True)
 assert src.stat().st_ino!=dst.stat().st_ino
 a=sha(src);assert sha(dst)==a
 manifest['copied'][name]={'bytes':dst.stat().st_size,'sha256':a}
shutil.copy2(ARTIFACT,GUEST/'xemu');assert sha(GUEST/'xemu')==PIN
text=source_config.decode()
old="port2 = '0300f0365e0400008902000021010000'"
assert text.count(old)==1
text=text.replace(old,"port2 = ''")
# Only the test copy disables automatic SDL physical-pad assignment.
spec=(ROOT.parent/'astra-emu-fix/source/config_spec.yml').read_text()
if 'auto_bind:' in spec:
 text=text.replace('[input]\n','[input]\nauto_bind = false\n',1)
(GUEST/'xemu.toml').write_text(text)
(GUEST/'xemu.toml.before').write_text(text)
(GUEST/'runtime').mkdir()
check=tomllib.loads(text);assert check['display']['renderer']=='VULKAN'
assert check['input']['bindings']['port1']=='keyboard'
assert check['input']['bindings']['port2']==''
assert (PRIMARY/'xemu.toml').read_bytes()==source_config
manifest.update(binary_sha256=PIN,experimental_config_sha256=sha(GUEST/'xemu.toml'),primary_unchanged=True,identity='Same source console, paired disk/EEPROM cold copy; no EEPROM or MAC changes')
(ROOT/'PREPARED.json').write_text(json.dumps(manifest,indent=2))
print(json.dumps(manifest,indent=2))
