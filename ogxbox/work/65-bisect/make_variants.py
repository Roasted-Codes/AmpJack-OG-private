#!/usr/bin/python3
"""Fork exact baseline; select only the requested W63 edits, not W63 sources."""
import ast, os, sys, shutil, json, hashlib, subprocess, difflib
from pathlib import Path
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent; R=W.parents[2]; W43=W.parent/'43-trainer-candidate'; W63=W.parent/'63-wake-rumble'
os.environ['TMPDIR']=str(W/'tmp');os.environ['PYTHONDONTWRITEBYTECODE']='1'
assert json.loads((W/'RESULT.json').read_text())['match']
def rep(t,a,b,n=1):
 assert t.count(a)==n,(a[:80],t.count(a));return t.replace(a,b)
def run(cmd,log):
 p=subprocess.run(list(map(str,cmd)),stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
 log.write_text('$ '+' '.join(map(str,cmd))+'\n'+p.stdout+f'\nexit={p.returncode}\n'); print(log,p.returncode)
 assert p.returncode==0,p.stdout
# Copy unmodified mock dependencies at the relative location required by f6_test.c.
shutil.copytree(R/'ogxbox/work/28-opus-controller-review/tests',W/'28-opus-controller-review/tests',ignore=shutil.ignore_patterns('out','__pycache__'))
a=(W/'tools/apply_w63.py').read_text(); tree=ast.parse(a)
pack=(W/'tools/make_packaging.py').read_text(); ptree=ast.parse(pack)
for variant,letter in [('wake','W'),('rumble','R')]:
 V=W/variant;shutil.copytree(W/'baseline/src',V/'src',ignore=shutil.ignore_patterns('out','__pycache__'))
 S=V/'src/ogxbox'
 def source_rep(path,old,new,count=1):
  p=S/path;p.write_text(rep(p.read_text(),old,new,count))
 # Select exact asserted source replacements from our COPIED apply_w63.py.
 env={'S':S,'rep':source_rep}
 selected=(18,21) if variant=='wake' else (65,90)
 for node in tree.body:
  if node.lineno in selected:exec(compile(ast.Module(body=[node],type_ignores=[]),str(W/'tools/apply_w63.py'),'exec'),env)
 if variant=='rumble':
  # The appended context members and rumble helper are isolated from diagnostics.
  orig=(S/'integration/ogx_present.h').read_text()
  node=next(n for n in tree.body if n.lineno==56)
  env.update(p=S/'integration/ogx_present.h',t=orig,i=orig.index('struct ogx_host_ctx {'))
  env['j']=orig.index('\n};',env['i'])
  exec(compile(ast.Module(body=[node],type_ignores=[]),'copied apply_w63.py','exec'),env)
  (S/'integration/ogx_present.h').write_text(env['t'])
  transport=S/'integration/ogx_transport.c';t=transport.read_text()
  t=rep(t,'struct ogx_module ogx_g_module;\n','struct ogx_module ogx_g_module;\nstatic uint32_t ogx_rumble_sent;\nstatic uint32_t ogx_rumble_frames;\n')
  t=rep(t,'\togx_seen_generation = g;\n','\togx_seen_generation = g;\n\togx_rumble_sent = 0;          /* W63: re-send a nonzero rumble after replug */\n')
  # Extract the literal rumble-only helper from the copied transformation, not log helpers.
  helpernode=next(n for n in tree.body if n.lineno==210)
  replacement=ast.literal_eval(helpernode.value.args[2])
  helper=replacement[replacement.index('/* ---- W63 rumble:'):replacement.index('void ogx_transport_init(void)')]
  t=rep(t,'void ogx_transport_init(void)',helper+'void ogx_transport_init(void)')
  t=rep(t,'\t\tgdr_gip_poll(&ogx_g_module.gip, now);','\t\tgdr_gip_poll(&ogx_g_module.gip, now);\n\t\togx_rumble_service();')
  transport.write_text(t)
 # Verify strictly bounded source changes and unchanged loader/build flags/caps/entry.
 changed=[];diff=[]
 for p in (W/'baseline/src').rglob('*'):
  if not p.is_file() or '/out/' in str(p):continue
  q=V/'src'/p.relative_to(W/'baseline/src')
  if p.read_bytes()!=q.read_bytes():
   changed.append(str(p.relative_to(W/'baseline/src')))
   diff+=list(difflib.unified_diff(p.read_text().splitlines(True),q.read_text().splitlines(True),fromfile=str(p),tofile=str(q)))
 assert set(changed)==({'ogxbox/gipdriver/src/gipdrive.h'} if variant=='wake' else {'ogxbox/integration/ogx_present.h','ogxbox/integration/ogx_present.c','ogxbox/integration/ogx_transport.c'}),changed
 (V/'changes.diff').write_text(''.join(diff));(V/'source-changes.json').write_text(json.dumps(changed,indent=2)+'\n')
 run(['bash',S/'integration/build_pic.sh'],V/'build_pic.log')
 (V/'artifact').mkdir();shutil.copyfile(S/'integration/out/pic.elf',V/'artifact/pic.elf')
 (V/'tools').mkdir();g=(W/'tools/gen_layout.py').read_text().replace('(work/63)','(work/65 '+variant+')')
 (V/'tools/gen_layout.py').write_text(g)
 run(['/usr/bin/python3',V/'tools/gen_layout.py',V/'artifact/pic.elf',V/'artifact/layout.json'],V/'layout.log')
 # Adapt W43 packaging using only generic ELF/layout binding operations from copied script.
 env={'S':W43,'W':V,'rep':rep}
 for node in ptree.body:
  if node.lineno in (12,13,15,16,17,35,43):
   exec(compile(ast.Module(body=[node],type_ignores=[]),'copied make_packaging.py','exec'),env)
 t=env['t'];t=rep(t,'REPO=ROOT.parents[2]','REPO=ROOT.parents[3]')
 t=t.replace('AmpJack63-u803-',f'AmpJack65{letter}-u803-').replace("'state':'w63_synthesized'","'state':'w65_synthesized'")
 t=rep(t,"'AmpJack43 u803 CANDIDATE'",f"'AmpJack65 {'WAKE' if variant=='wake' else 'RUMBLE'}-ONLY'")
 t=rep(t,"['Enable AmpJack43 candidate']","['Enable']")
 t=t.replace('AMPJ43-CAND',f'AMPJ65-{letter}')
 (V/'build.py').write_text(t)
 for f in ['loader.c','bootstrap.S','bootstrap.ld','sha256.inc','NOTICES.txt']:
  shutil.copyfile(W43/f,V/f)
 assert (V/'loader.c').read_bytes()==(W43/'loader.c').read_bytes()
 t=(W43/'test_candidate.py').read_text()
 t=t.replace('x.mod.module_off+21128',"x.mod.module_off+x.mod.layout['status_fields']['install_failed']")
 t=t.replace('x.mod.module_off+21124',"x.mod.module_off+x.mod.layout['status_fields']['installed_hooks']")
 # Allocation expectations remain W43 values: fail rather than silently broaden them.
 (V/'test_candidate.py').write_text(t)
 t=(W43/'release.py').read_text().replace('AmpJack43-u803-candidate.zip',f'AmpJack65{letter}-u803.zip')
 (V/'release.py').write_text(t)
 (V/'README.txt').write_text(f'AmpJack65 {variant.upper()}-ONLY; Halo 2 u803. Enable (default OFF).\nIndependent W43 fork; W43 loader and zero motor caps retained.\nOFFLINE HOST-TESTED ONLY; NOT CONSOLE-TESTED. Keep the matched .xbtf/.bin pair together.\n')
 (V/'tests').mkdir();shutil.copyfile(W63/'tests/f6_test.c',V/'tests/f6_test.c')
 t=(W63/'tests/test63.c').read_text();lines=t.splitlines(True)
 # Shared synthetic USB seam, only relevant case, no log implementation or log cases.
 common=''.join(lines[:90]).replace('#include "ogx_log.h"\n','').replace('ogx_log_fake_tick += 10; ','').replace('\togx_log_init(flags);\n','\t(void)flags;\n')
 case=''.join(lines[90:118] if variant=='wake' else lines[119:172])
 if variant=='rumble':case=case.replace('caps.Vibration.wLeftMotorSpeed == 0xFFFF && caps.Vibration.wRightMotorSpeed == 0xFFFF','caps.Vibration.wLeftMotorSpeed == 0 && caps.Vibration.wRightMotorSpeed == 0')
 c='a' if variant=='wake' else 'b'
 main=f'\nint main(void) {{ test_{c}(); printf("%s {c} frames=%d\\n", fails ? "FAIL" : "PASS", nframes); return fails ? 1 : 0; }}\n'
 (V/'tests/test65.c').write_text(common+case+main)
 print('PREPARED',variant,changed)
 (W/'RESULT.json').write_text(json.dumps({'status':'INCOMPLETE','step':variant+' source build complete','baseline_elf_sha256':'7bbfdafaa91920269876aa54e02efe278b738c0298aeb7bd629b1aaf8a1a08b8'},indent=2)+'\n')
 (W/'REPORT.md').write_text('INCOMPLETE\nBaseline reproduced exactly. '+variant+' isolated source build complete; tests pending.\n')
