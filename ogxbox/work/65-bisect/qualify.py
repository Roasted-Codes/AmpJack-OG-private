#!/usr/bin/python3
"""Offline host qualification with full sanitizer flags retained."""
import os,sys,json,subprocess,hashlib,re
from pathlib import Path
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent
os.environ['TMPDIR']=str(W/'tmp');os.environ['PYTHONDONTWRITEBYTECODE']='1'
results=[]
# Preserve the failed initial packaging run; never relax the format checker.
if (W/'wake/release').exists() and not (W/'wake/release/verification.json').exists():
 (W/'wake/release').rename(W/'wake/release-attempt1')
def run(cmd,log,env=None):
 p=subprocess.run(list(map(str,cmd)),stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,env=env)
 log.write_text('$ '+' '.join(map(str,cmd))+'\n'+p.stdout+f'\nexit={p.returncode}\n')
 results.append({'command':' '.join(map(str,cmd)),'rc':p.returncode,'log':str(log.relative_to(W))})
 (W/'tests-progress.json').write_text(json.dumps(results,indent=2)+'\n')
 print(str(log.relative_to(W)),p.returncode,p.stdout[-250:],flush=True)
 assert p.returncode==0, str(log)
 return p.stdout
for variant in ('wake','rumble'):
 V=W/variant;S=V/'src/ogxbox';I=S/'integration';O=V/'tests/out';O.mkdir(parents=True,exist_ok=True)
 mock=W/'28-opus-controller-review/tests'
 cf=['-m32','-std=gnu11','-O1','-g','-fno-omit-frame-pointer','-fsanitize=address,undefined','-fno-sanitize-recover=undefined','-Wall','-Wno-unused-function','-Wno-unused-parameter']
 cf += ['-I'+str(p) for p in [I,S/'gip',S/'halo2',V/'src/core',S/'gipdriver/src',mock]]
 objects=[]
 for name in ['ogx_transport','ogx_present','ogx_stub']:
  obj=O/(name+'.o');run(['clang']+cf+['-c',I/(name+'.c'),'-o',obj],O/(name+'-build.log'));objects.append(obj)
 for name,source in [('xinput_model',S/'halo2/xinput_model.c'),('test65',V/'tests/test65.c')]:
  obj=O/(name+'.o');run(['clang']+cf+['-c',source,'-o',obj],O/(name+'-build.log'));objects.append(obj)
 run(['clang']+cf+objects+['-o',O/'test65'],O/'link.log')
 env=os.environ.copy();env['ASAN_OPTIONS']='detect_leaks=0'
 out=run([O/'test65'],O/'test65.log',env);assert 'PASS ' in out and 'FAIL' not in out
 F=O/'f6';F.mkdir(exist_ok=True);objects=[]
 sources=[(n,I/(n+'.c')) for n in ['ogx_transport','ogx_present','ogx_stub','ogx_install']]+[('xinput_model',S/'halo2/xinput_model.c'),('native_mock',mock/'native_mock.c'),('f6_test',V/'tests/f6_test.c')]
 for name,source in sources:
  obj=F/(name+'.o');run(['gcc']+cf+['-c',source,'-o',obj],F/(name+'-build.log'));objects.append(obj)
 run(['gcc']+cf+objects+['-o',F/'f6_test'],F/'link.log')
 for mode in ('stubs-only','explicit-pump'):
  e=env.copy();e['OGX_EXPLICIT_PUMP']='1' if mode=='explicit-pump' else '0'
  out=run([F/'f6_test'],F/(mode+'.log'),e)
  assert 'SUMMARY tests=6 red=0 green=6' in out
 run(['/usr/bin/python3',V/'release.py','--out',V/'release'],V/'release.log')
 for log in [V/'release/cpu-tests.log',V/'release/unpacked/cpu-tests.log']:
  t=log.read_text();assert re.search(r'Ran 7 tests',t) and '\nOK\n' in t,(log,t[-1000:])
 man=json.loads((V/'release/manifest.json').read_text())
 # W43 allocation must remain exactly unchanged for each isolated variant.
 assert man['resident_alloc']==36864 and man['file_buffer_alloc']==16384,man
 (W/'RESULT.json').write_text(json.dumps({'status':'INCOMPLETE','step':variant+' all offline tests passed; final audit pending','baseline_elf_sha256':'7bbfdafaa91920269876aa54e02efe278b738c0298aeb7bd629b1aaf8a1a08b8'},indent=2)+'\n')
 (W/'REPORT.md').write_text('INCOMPLETE\nBaseline reproduced. '+variant+' offline sanitizer/F6/release/archive tests pass. Final audit and crash review pending.\n')
print('ALL OFFLINE QUALIFICATION PASSED')
