#!/usr/bin/env python3
import pathlib, hashlib, json, subprocess
R=pathlib.Path(__file__).resolve().parents[1]
for n in ('evidence','tmp'): (R/n).mkdir(exist_ok=True)
P=R.parent
files=[P/'35-loading-stop/probe3/mem_00412000_a000.bin',P/'32-opus-final-integration/artifact/pic.elf',P/'32-opus-final-integration/artifact/layout.json',pathlib.Path('/home/roasted/Desktop/Xbox/H2-Decomp/tu15-decomp/targets/halo2-tu15-u803/default.xbe')]
x: dict = {str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
x['boot_id']=pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip()
x['old_pid_exists']=pathlib.Path('/proc/2533644').exists()
ps=subprocess.run(['ps','-eo','pid,lstart,args'],text=True,capture_output=True,check=True).stdout
x['emulator_process_lines']=[l for l in ps.splitlines() if 'xemu' in l.lower() and 'discover.py' not in l]
(R/'evidence/identity-discovery.json').write_text(json.dumps(x,indent=2)+'\n')
print(json.dumps(x,indent=2))
for cmd,name in [(['llvm-objdump','-d',str(files[1])],'module.dis'),(['llvm-nm','-n',str(files[1])],'module.nm'),(['objdump','-D','-b','binary','-m','i386','--adjust-vma=0x412000','--start-address=0x41655f','--stop-address=0x417100',str(files[0])],'stock.dis')]:
 p=subprocess.run(cmd,text=True,capture_output=True);(R/'evidence'/name).write_text(p.stdout+p.stderr);print(name,p.returncode)
