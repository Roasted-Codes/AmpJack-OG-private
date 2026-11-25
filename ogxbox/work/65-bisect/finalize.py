#!/usr/bin/python3
"""Verify deliverables, aggregate measured results, publish final reports."""
import sys,os,json,hashlib,importlib.util,subprocess,re,shutil,difflib
from pathlib import Path
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;R=W.parents[2];P=W.parent/'43-trainer-candidate'
os.environ['TMPDIR']=str(W/'tmp');os.environ['PYTHONDONTWRITEBYTECODE']='1'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
base=sha(W/'baseline/src/ogxbox/integration/out/pic.elf')
assert base=='7bbfdafaa91920269876aa54e02efe278b738c0298aeb7bd629b1aaf8a1a08b8'
progress=json.loads((W/'tests-progress.json').read_text());assert all(t['rc']==0 for t in progress)
sizes={};variants={};tests=[];commands=[]
for name in ['baseline','wake','rumble']:
 elf=W/name/'src/ogxbox/integration/out/pic.elf'
 out=subprocess.check_output(['size',str(elf)],text=True);values=list(map(int,out.splitlines()[1].split()[:3]))
 rel=subprocess.check_output(['readelf','-r',str(elf)],text=True);dyn=subprocess.check_output(['readelf','-d',str(elf)],text=True)
 kinds=re.findall(r'R_386_\w+',rel);assert len(kinds)==20 and set(kinds)=={'R_386_RELATIVE'} and 'TEXTREL' not in dyn
 sizes[name]=dict(zip(['text','data','bss'],values))
 if name=='baseline':
  m=json.loads((P/'build/manifest.json').read_text())
 else:
  V=W/name;spec=importlib.util.spec_from_file_location('build_'+name,V/'build.py');assert spec and spec.loader
  B=importlib.util.module_from_spec(spec);spec.loader.exec_module(B)
  _,m=B.check(V/'release');B.check(V/'release/unpacked')
  data,info=B.TF.parse((V/'release/candidate'/B.NAMES[0]).read_bytes(),True)
  assert info['name']==f'AmpJack65 {name.upper()}-ONLY',info
  assert len(info['options'])==1 and info['options'][0]['label']=='Enable' and info['options'][0]['default']==0,info
  for f in ['loader.c','bootstrap.S','bootstrap.ld','sha256.inc']:
   assert (V/f).read_bytes()==(P/f).read_bytes(),f
  assert (V/'src/ogxbox/integration/build_pic.sh').read_bytes()==(W/'baseline/src/ogxbox/integration/build_pic.sh').read_bytes()
  assert (V/'src/ogxbox/halo2/xinput_model.c').read_bytes()==(W/'baseline/src/ogxbox/halo2/xinput_model.c').read_bytes()
  assert (V/'tests/f6_test.c').read_bytes()==(W.parent/'63-wake-rumble/tests/f6_test.c').read_bytes()
  for f in ['crt0.c','module_main.c','ogx_module.h','ogx_stub.c','ogx_install.c']:
   assert (V/'src/ogxbox/integration'/f).read_bytes()==(W/'baseline/src/ogxbox/integration'/f).read_bytes(),f
  if name=='rumble':assert (V/'src/ogxbox/gipdriver/src/gipdrive.h').read_bytes()==(W/'baseline/src/ogxbox/gipdriver/src/gipdrive.h').read_bytes()
  for mode in ['stubs-only','explicit-pump']:
   t=(V/'tests/out/f6'/f'{mode}.log').read_text();assert 'SUMMARY tests=6 red=0 green=6' in t
  for target in ['release','release/unpacked']:
   t=(V/target/'cpu-tests.log').read_text();assert 'Ran 7 tests' in t and '\nOK\n' in t
  verify=json.loads((V/'release/verification.json').read_text());assert verify['unpacked_checker_and_cpu_tests']=='PASS'
  # Place the requested pair directly in each variant directory as well.
  files={}
  for f in B.NAMES:
   src=V/'release/candidate'/f;shutil.copyfile(src,V/f)
   assert sha(src)==sha(V/f)
   files['xbtf' if f.endswith('.xbtf') else 'bin']={'name':f,'sha256':sha(V/f),'bytes':(V/f).stat().st_size}
  (V/'SHA256SUMS').write_text(''.join(v['sha256']+'  '+v['name']+'\n' for v in files.values()))
  variants[name]={'output_dir':str(V),'elf_sha256':sha(elf),'files':files,'display_name':info['name'],'options':info['options'],'archive':str(V/'release'/('AmpJack65'+('W' if name=='wake' else 'R')+'-u803.zip')),'archive_sha256':verify['archive_sha256'],'console_tested':False}
  tests.append({'variant':name,'build_pic_rc':0,'relocations':'20 R_386_RELATIVE only','TEXTREL':False,'f6_stubs_only':'6/6','f6_explicit_pump':'6/6','applicable_test63_case':'a PASS frames=5' if name=='wake' else 'b PASS frames=9; caps 0/0','release_cpu':'7/7','unpacked_archive_cpu':'7/7','source_isolation_and_display_option_audit':'PASS'})
  for srcf in ['build.py','test_candidate.py','release.py']:
   (V/(srcf+'.diff')).write_text(''.join(difflib.unified_diff((P/srcf).read_text().splitlines(True),(V/srcf).read_text().splitlines(True),fromfile='W43/'+srcf,tofile=name+'/'+srcf)))
 for k in ['image_size','mem_end','resident_alloc','file_buffer_alloc','payload_bytes']:sizes[name][k]=m[k]
 assert m['resident_alloc']==36864 and m['file_buffer_alloc']==16384
 commands.append('bash '+str(W/name/'src/ogxbox/integration/build_pic.sh'))
queue=(W/'baseline/src/ogxbox/gipdriver/src/gipdrive.h').read_text();a=queue.index('static int gdr_tx_send');b=queue.index('static int gdr_tx_drain',a)
queue=queue[a:b];print('QUEUE EVIDENCE\n'+queue)
assert 'tx_dropped' in queue and '8' in queue
not_verified=['No console, emulator, USB, network or git remote was accessed. No console testing performed.','Real pad wake/rumble and Xbox launch success remain unverified.','Whether Halo 2 calls SetState with W43 zero motor caps; hEvent is recorded but not signalled.','W63 crash cause is not proven; log/entry/loader/allocation changes are in neither variant.']
crash='''## Crash review
VERIFIED (owner report): W43 launches; W63 black-screens with log ON and OFF. Timing is owner-observed, not reproduced here.
INFERENCE rank 1 — W63 log/entry plumbing (NEITHER variant): inspect this first; log OFF does not remove all added execution.
VERIFIED: changes.diff:87-127 adds crt0/module_main flags, ogx_log_init and BOOT formatting after hook installation regardless of flags.
VERIFIED: ogx_ll_begin returns before tick access when OFF (diff:232-240); BOOT is not evidence of an unconditional tick or IRQL read.
VERIFIED: k_irql uses fs:[0x24] (diff:183-187), but ogx_log_service checks log_on before k_irql (307-310); OFF skips that read.
VERIFIED: pump unconditionally evaluates ogx_log_ms() as an argument to ogx_log_periodic (diff:851-853), BEFORE periodic's OFF guard.
VERIFIED: ogx_log_ms reads slot 0x41b774, then dereferences its value (175-182): slot -> ADDRESS of tick variable -> tick; no function call.
INFERENCE: dereference levels look correct, but a mapped-yet-invalid slot target could fault at the first pump even with logging OFF; hosted doubles do not cover it.
INFERENCE rank 2 — W63 allocation/loader changes (NEITHER): they execute before title entry; larger allocation changes placement/pressure and validation extents.
VERIFIED: W43 actual allocations are 36864/16384, W63 manifest reports 45056/24576; both W65 variants retain 36864/16384.
VERIFIED: W43 loader.c:78-81 region_ok rejects overflow/title/trainer overlap; W63 changes.diff does not alter its expression, only generated sizes affect its extent.
INFERENCE: mere allocation failure/rejection should return stock via existing gates, not itself prove a black-screen fault; actual Xbox allocation placement remains untested.
VERIFIED: W63 adds flags passing and extra resolved-slot checks (diff:857-902; tools/make_packaging.py:37,50-61); OFF still runs checks. Neither variant includes them.
INFERENCE rank 3 — wake repeat-ANNOUNCE traffic (WAKE variant only): plausible during a blinking pad's startup, before the first visible frame.
VERIFIED: gdr_rx_announce queues power-on for each qualified fallback ANNOUNCE, even non-28 lengths; successful POWER TXDONE triggers existing S-init.
VERIFIED: decoder queue is bounded to 8 entries and gdr_tx_send increments tx_dropped/refuses when full; attach OUT queue also has GDR_TX_SLOTS=8.
INFERENCE: not unbounded memory growth; repeated ANNOUNCE can still cause sustained traffic/starvation/protocol churn. A short hosted case cannot exclude it.
INFERENCE rank 4 — rumble/generation behavior (RUMBLE variant only): depends on early SetState/nonzero desired state, so less direct than entry/pump additions.
VERIFIED: generation sync resets last-sent to zero; BSS desired starts zero. No rumble frame until ready, no S-init pending, queues/OUT idle, desired differs.
INFERENCE: generation change alone does not emit initial rumble; a retained nonzero request is resent after qualification. SetState's pending/status/event semantics may matter.
INFERENCE rank 5 — motor caps 0xFFFF (NEITHER): might induce earlier/different title rumble behavior, not an obvious standalone entry fault; both W65 caps stay zero.
INFERENCE: if both W65 variants launch, a third isolated W43 + log/entry/loader/allocation variant is needed; these two do not exonerate that group or combinations.
'''
# Confirm the W63 allocation claim from the actual manifest, not narrative.
w63=json.loads((W.parent/'63-wake-rumble/release/manifest.json').read_text());assert (w63['resident_alloc'],w63['file_buffer_alloc'])==(45056,24576)
report='# W65 independent W43 bisect builds — COMPLETE (offline only)\n\n'
report+='Step 0 VERIFIED: unmodified copied W43 inputs rebuilt to '+base+'.\nInputs: W63 orig/ snapshot (not its modified src/), validated by the exact W43 ELF identity.\nBoth variants fork baseline/src independently. The copied apply_w63.py and make_packaging.py supply selected transformations only; neither is imported from W63.\n\n'
report+='## Deliverables\n'
for name,v in variants.items():
 report+=name+': '+v['output_dir']+'\nELF SHA256 '+v['elf_sha256']+'\n'
 for f in v['files'].values():report+=f['name']+'  SHA256 '+f['sha256']+'\n'
 report+='Archive: '+v['archive']+'  SHA256 '+v['archive_sha256']+'\n'
report+='\n## Isolation and tests\nWAKE: only gipdrive.h announce hunk and its two counters. RUMBLE: only appended presentation rumble fields, SetState handling, pump helper/call and generation last-sent reset. No caps/wake/log changes in rumble.\nBoth loader.c/bootstrap.S/bootstrap.ld/sha256.inc are byte-identical to W43. build_pic.sh and flags are byte-identical. No allocation delta required.\nPackaging adaptations: exact new ELF/layout identities, compiler-derived status offsets, repo depth, new filenames/display/options/creation keys; W43 slot list and loader logic unchanged. Per-file .diff files record these changes.\nW43 test_candidate.py contains seven tests; copied as seven, with compiler-derived status offsets replacing hard-coded W43 offsets. No test_08 was copied: that is W63 log-specific. Allocation checks remain W43 literals, not relaxed.\nFor BOTH variants: build rc=0, 20 R_386_RELATIVE only, no TEXTREL; F6 6/6 in both modes; applicable test63 case PASS; release 7/7 and unpacked archive 7/7.\nHosted test63 removes log plumbing/cases and the unrelated a/b case, keeps relevant checks unchanged, except rumble caps expected 0/0. F6 test is byte-identical, with copied mock dependencies preserving its relative include.\nSanitizers: -m32 ASan+UBSan, no undefined recovery. Warnings are unused test fixtures/counter; no sanitizer errors.\n\n## Sizes (bytes; GNU size text/data/bss)\n'
for name,s in sizes.items():report+=name+': '+json.dumps(s,sort_keys=True)+'\n'
report+='W43 build.py:83 derives RESIDENT_ALLOC=align_up(mem_end,4096), FILE_ALLOC=align_up(payload,4096); actual W43 values are 36864/16384, NOT 36864/24576.\n'
report+='\n## Exact executed commands\nAll commands run from '+str(R)+'; child command paths are absolute. Compiler temporary files are confined by TMPDIR='+str(W/'tmp')+' and PYTHONDONTWRITEBYTECODE=1.\n'
report+='\n'.join(commands)+'\n'
report+='\n'.join(t['command']+'  # rc='+str(t['rc'])+'; log '+t['log'] for t in progress)+'\n'
report+='The release.py child test commands (built/unpacked) are recorded verbatim at the start of each release/cpu-tests.log and release/unpacked/cpu-tests.log.\n\n'
report+=crash+'\n## Refusals and corrected failure\nSee REFUSALS.md for the verbatim execute_code refusal; normal tools and owned script files were used instead. No approval setting was changed.\nInitial packaging rejected creation key AMPJ65W: ValueError(creation key must have "-" at index 6 (Trainer.cpp check)). Corrected keys to AMPJ65-W / AMPJ65-R, preserved wake/release-attempt1, reran all qualification. No test was weakened.\n\n## Not verified\n'+'\n'.join('- '+x for x in not_verified)+'\n'
(W/'REPORT.md').write_text(report)
result={'status':'COMPLETE','baseline_elf_sha256':base,'variants':variants,'tests':tests,'test_commands':progress,'sizes':sizes,'crash_review':'REPORT.md#crash-review','not_verified':not_verified}
(W/'RESULT.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({'status':result['status'],'variants':variants,'sizes':sizes},indent=2))
