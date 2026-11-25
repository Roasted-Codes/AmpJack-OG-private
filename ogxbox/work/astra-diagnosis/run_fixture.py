from pathlib import Path
import subprocess,re,hashlib,json
out=Path(__file__).resolve().parent
src=Path('/home/roasted/Desktop/Xbox/OGH2_Server/reference/xemu/hw/usb/hcd-ohci.c')
s=src.read_text();lic=s[:s.index('#include')]
constants=s[s.index('#define OHCI_ED_FA_SHIFT'):s.index('#define OHCI_HRESET_FSBIR')]
fn=s[s.index('static int ohci_service_td('):s.index('/* Service an endpoint list.')]
(out/'ohci_constants.inc').write_text(lic+constants)
(out/'ohci_service_td.inc').write_text(lic+fn)
guard='''    if (!completion && ohci->async_td) {
        trace_usb_ohci_td_too_many_pending(OHCI_BM(ed->flags, ED_EN));
        return 1;
    }
'''
anchor='    if (ohci_read_td(ohci, addr, &td)) {'
assert fn.count(anchor)==1
(out/'ohci_service_td_guarded.inc').write_text(lic+fn.replace(anchor,guard+anchor))
stubs=[]
for name in sorted(set(re.findall(r'trace_\w+',fn))):
 stubs.append('#define '+name+'(...) '+ ('(++blocked)' if name=='trace_usb_ohci_td_too_many_pending' else '((void)0)'))
(out/'ohci_trace_stubs.inc').write_text('\n'.join(stubs)+'\n')
cmd=['cc','-std=c11','-O2','-Wall','-Wextra','-Wno-unused-variable',str(out/'ohci_fixture.c'),'-o',str(out/'ohci_fixture')]
r=subprocess.run(cmd,capture_output=True,text=True);(out/'fixture-build.log').write_text(' '.join(cmd)+'\n'+r.stdout+r.stderr);print(r.stdout+r.stderr);r.check_returncode()
r=subprocess.run([str(out/'ohci_fixture')],capture_output=True,text=True)
(out/'fixture-run.log').write_text(r.stdout+r.stderr);print(r.stdout+r.stderr);r.check_returncode()
(out/'fixture-result.json').write_text(json.dumps({'source_sha256':hashlib.sha256(src.read_bytes()).hexdigest(),'function_sha256':hashlib.sha256(fn.encode()).hexdigest(),'function_extracted_verbatim':True,'test_kind':'isolated real source function with simulated memory and USB completion; not physical input','exit_code':r.returncode},indent=2)+'\n')
cmd.insert(1,'-DGUARD_EARLY');cmd[-1]=str(out/'ohci_fixture_guarded')
r=subprocess.run(cmd,capture_output=True,text=True)
(out/'guarded-build.log').write_text(' '.join(cmd)+'\n'+r.stdout+r.stderr);r.check_returncode()
r=subprocess.run([cmd[-1]],capture_output=True,text=True)
(out/'guarded-run.log').write_text(r.stdout+r.stderr);print(r.stdout+r.stderr);r.check_returncode()
