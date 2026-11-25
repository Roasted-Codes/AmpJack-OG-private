#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Clean owned build, CPU qualification, deterministic archive and unpack retest."""
import argparse, json, subprocess, sys, zipfile
from pathlib import Path
sys.dont_write_bytecode=True
import build as B
ALLOW=set(B.NAMES)|{'README.txt','NOTICES.txt','COPYING.GPL-3','SHA256SUMS','manifest.json'}
def execute(cmd,log):
 p=subprocess.run([str(x) for x in cmd],cwd=B.ROOT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
 log.write_text('$ '+' '.join(map(str,cmd))+'\n'+p.stdout+f'\nexit={p.returncode}\n')
 print(p.stdout,end='')
 if p.returncode:raise SystemExit(f'FAILED ({p.returncode}); see {log}')
def verify(archive,out):
 assert out.is_relative_to(B.ROOT) and not out.exists(),'unpack output must be new and owned'
 with zipfile.ZipFile(archive) as z:
  assert len(z.namelist())==len(ALLOW) and set(z.namelist())==ALLOW,'archive allowlist'
  out.mkdir();c=out/'candidate';c.mkdir()
  for name in ALLOW:
   data=z.read(name)
   ((out if name=='manifest.json' else c)/name).write_bytes(data)
 sums=(c/'SHA256SUMS').read_text().splitlines()
 assert len(sums)==len(ALLOW)-1
 for line in sums:
  digest,name=line.split('  ',1);assert name in ALLOW-{'SHA256SUMS'}
  target=out/name if name=='manifest.json' else c/name
  assert B.sha(target.read_bytes())==digest,name
 B.check(out)
 execute([sys.executable,B.ROOT/'test_candidate.py','--out',out],out/'cpu-tests.log')
 return {'archive_allowlist':sorted(ALLOW),'archive_sha256':B.sha(archive.read_bytes()),'unpacked_checker_and_cpu_tests':'PASS','guest_tested':False,'physical_test_clearance':False}
def main():
 p=argparse.ArgumentParser();p.add_argument('--out',type=Path,default=B.ROOT/'release-build');p.add_argument('--verify-archive',type=Path);a=p.parse_args();out=a.out.resolve()
 if a.verify_archive:
  r=verify(a.verify_archive.resolve(),out);(out/'verification.json').write_text(json.dumps(r,indent=2)+'\n');return
 assert out.is_relative_to(B.ROOT) and not out.exists(),'clean output must be new and owned'
 out.mkdir()
 execute([sys.executable,B.ROOT/'build.py','build','--out',out],out/'build.log')
 execute([sys.executable,B.ROOT/'test_candidate.py','--out',out],out/'cpu-tests.log')
 c=out/'candidate'
 for name in ('README.txt','NOTICES.txt'):(c/name).write_bytes((B.ROOT/name).read_bytes())
 (c/'COPYING.GPL-3').write_bytes((B.REPO/'LICENSE').read_bytes())
 (c/'manifest.json').write_bytes((out/'manifest.json').read_bytes())
 sums=''.join(B.sha((c/n).read_bytes())+'  '+n+'\n' for n in sorted(ALLOW-{'SHA256SUMS'}))
 (c/'SHA256SUMS').write_text(sums)
 archive=out/'AmpJack65R-u803.zip'
 with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
  for name in sorted(ALLOW):
   item=zipfile.ZipInfo(name,(2026,1,1,0,0,0));item.external_attr=0o100644<<16;item.compress_type=zipfile.ZIP_DEFLATED
   z.writestr(item,(c/name).read_bytes())
 (out/'ARCHIVE-SHA256SUMS').write_text(B.sha(archive.read_bytes())+'  '+archive.name+'\n')
 r=verify(archive,out/'unpacked');(out/'verification.json').write_text(json.dumps(r,indent=2)+'\n')
 print('HOST QUALIFIED candidate — NOT runtime/physical cleared:',archive)
if __name__=='__main__':main()
