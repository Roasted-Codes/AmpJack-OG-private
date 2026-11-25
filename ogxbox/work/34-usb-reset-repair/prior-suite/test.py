"""Real-source preservation regressions; deterministic DMA/USB, no hardware."""
from pathlib import Path
import hashlib
import itertools
import json
import os
import re
import resource
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
SRC = ROOT / 'source'
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
mode = sys.argv[1]
assert mode in ('original', 'patched', 'sanitized')
source = (subprocess.check_output(['git', '-C', str(SRC), 'show', 'HEAD:hw/usb/hcd-ohci.c']).decode()
          if mode == 'original' else (SRC / 'hw/usb/hcd-ohci.c').read_text())
function = source[source.index('static int ohci_service_td('):source.index('/* Service an endpoint list.')]
walker = source[source.index('static int ohci_service_ed_list('):source.index('/* set a timer for EOF */')]
lists = source[source.index('static void ohci_process_lists('):source.index('/* Do frame processing on frame boundary */')]
callback = source[source.index('static void ohci_async_complete_packet('):source.index('static USBPortOps ohci_port_ops')]
lic = source[:source.index('#include')]
out = ROOT / ('test-' + mode)
out.mkdir(exist_ok=True)
(out / 'ohci_service_td.inc').write_text(lic + function)
limit = re.search(r'^#define ED_LINK_LIMIT .*$', source, re.M)
assert limit is not None
(out / 'ohci_service_ed_list.inc').write_text(lic + limit[0] + '\n' + walker + lists + callback)
(out / 'ohci_constants.inc').write_text(lic + source[source.index('#define OHCI_ED_FA_SHIFT'):source.index('#define OHCI_HRESET_FSBIR')])
(out / 'ohci_trace_stubs.inc').write_text('\n'.join('#define '+n+'(...) '+('(++blocked)' if n == 'trace_usb_ohci_td_too_many_pending' else '((void)0)') for n in sorted(set(re.findall(r'trace_\w+',function+walker+lists+callback))))+'\n')
command = ['cc', '-std=c11', '-O1', '-g', '-Wall', '-Wextra', '-Wno-unused-variable', '-Wno-sign-compare', '-I'+str(out), str(ROOT/'fixture.c'), '-o', str(out/'fixture')]
if mode == 'sanitized':
    command[1:1] = ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
build = subprocess.run(command, text=True, capture_output=True)
(out/'build.log').write_text(' '.join(command)+'\n'+build.stdout+build.stderr)
build.check_returncode()
cases = []
# ED_D=0 exercises TD direction (control); ED_D set is the common bulk/interrupt path.
for n, order, rounded, status, control in itertools.product((5,19),(0,1),(0,1),(0,-2,-3,-5),(0,1)):
    cmd = [str(out/'fixture'), str(n), str(order), str(rounded), str(status), '1', str(control)]
    run = subprocess.run(cmd, text=True, capture_output=True)
    expected_fail = mode == 'original' and order == 1 and status == 0
    case = dict(command=cmd, returncode=run.returncode, expected_preservation_failure=expected_fail, stdout=run.stdout, stderr=run.stderr)
    case['matched_expected'] = (run.returncode != 0 and 'memcmp(memory+0x1000,input' in run.stderr) if expected_fail else run.returncode == 0
    cases.append(case)
# Setup uses endpoint zero and its TD direction, also sharing the packet buffer.
for order in (0,1):
    cmd = [str(out/'fixture'), '5', str(order), '1', '0', '0', '1']
    run = subprocess.run(cmd,text=True,capture_output=True)
    expected_fail = mode == 'original' and order == 1
    cases.append(dict(command=cmd,returncode=run.returncode,expected_preservation_failure=expected_fail,stdout=run.stdout,stderr=run.stderr,matched_expected=(run.returncode != 0 and 'memcmp(memory+0x1000,input' in run.stderr) if expected_fail else run.returncode == 0))
for order, kind in itertools.product((0,1),(0,1,2)):
    cmd = [str(out/'fixture'), 'list', str(order), str(kind)]
    run = subprocess.run(cmd,text=True,capture_output=True)
    expected_fail = mode == 'original' and order == 1
    cases.append(dict(command=cmd,returncode=run.returncode,expected_preservation_failure=expected_fail,stdout=run.stdout,stderr=run.stderr,matched_expected=(run.returncode != 0 and 'memcmp(memory+0x1000,input' in run.stderr) if expected_fail else run.returncode == 0))
result = dict(mode=mode,source_sha256=hashlib.sha256(source.encode()).hexdigest(),function_sha256=hashlib.sha256(function.encode()).hexdigest(),walker_sha256=hashlib.sha256(walker.encode()).hexdigest(),build_command=command,cases=cases,total=len(cases),expected_red=sum(c['expected_preservation_failure'] for c in cases),all_expected=all(c['matched_expected'] for c in cases))
(out/'results.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:v for k,v in result.items() if k!='cases'},indent=2))
assert result['all_expected'], str(out/'results.json')
