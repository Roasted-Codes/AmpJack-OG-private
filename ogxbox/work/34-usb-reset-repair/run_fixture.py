"""RED/GREEN runner: extracts real function bodies from one hcd-ohci.c variant
plus the read-only astra core.c / usb.h, compiles fixture.c, runs all cases.
usage: run_fixture.py <variant: baseline|candidate|guardonly> [--sanitize]"""
from pathlib import Path
import hashlib, json, re, resource, subprocess, sys

W = Path(__file__).resolve().parent
SRC = W.parent / 'astra-emu-fix' / 'source'
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
variant = sys.argv[1]
san = '--sanitize' in sys.argv
ohci_src = (W / variant / 'hw/usb/hcd-ohci.c').read_text()
core_src = (SRC / 'hw/usb/core.c').read_text()
usb_h = (SRC / 'include/hw/usb.h').read_text()


def func(src, sig):
    i = src.index(sig)
    i = src.rindex('\n', 0, i) + 1
    j = src.index('\n}\n', i) + 3
    return src[i:j]


ohci_funcs = [func(ohci_src, s) for s in (
    'void ohci_stop_endpoints(OHCIState *ohci)\n{',
    'static void ohci_roothub_reset(OHCIState *ohci)\n{',
    'static void ohci_child_detach(USBPort *port1, USBDevice *dev)\n{',
    'static void ohci_detach(USBPort *port1)\n{',
    'static void ohci_async_complete_packet(USBPort *port, USBPacket *packet)\n{',
    'static int ohci_service_ed_list(OHCIState *ohci, uint32_t head)\n{')]
core_funcs = [func(core_src, s) for s in (
    'void usb_detach(USBPort *port)\n{',
    'void usb_port_reset(USBPort *port)\n{',
    'void usb_packet_complete_one(USBDevice *dev, USBPacket *p)\n{',
    'void usb_packet_complete(USBDevice *dev, USBPacket *p)\n{',
    'void usb_cancel_packet(USBPacket * p)\n{')]
inflight = func(usb_h, 'static inline bool usb_packet_is_inflight(USBPacket *p)\n{')
consts = ohci_src[ohci_src.index('#define OHCI_ED_FA_SHIFT'):ohci_src.index('#define OHCI_HRESET_FSBIR')]
consts = re.search(r'^#define ED_LINK_LIMIT .*$', ohci_src, re.M)[0] + '\n' + consts

name = variant + ('-sanitized' if san else '')
out = W / 'runs' / name
out.mkdir(parents=True, exist_ok=True)
allsrc = '\n'.join(ohci_funcs + core_funcs)
(out / 'extracted_ohci.inc').write_text('\n'.join(ohci_funcs))
(out / 'extracted_core.inc').write_text('\n'.join(core_funcs))
(out / 'extracted_usb_h.inc').write_text(inflight)
(out / 'extracted_constants.inc').write_text(consts)
(out / 'extracted_trace_stubs.inc').write_text(''.join(
    '#define %s(...) ((void)0)\n' % t for t in sorted(set(re.findall(r'\btrace_\w+', allsrc)))))
cmd = ['cc', '-std=gnu11', '-O1', '-g', '-Wall', '-Wextra', '-Wno-unused-parameter',
       '-Wno-unused-function', '-Wno-sign-compare', '-I' + str(out), str(W / 'fixture.c'), '-o', str(out / 'fixture')]
if san:
    cmd[1:1] = ['-fsanitize=address,undefined', '-fno-omit-frame-pointer', '-fno-sanitize-recover=all']
b = subprocess.run(cmd, text=True, capture_output=True)
(out / 'build.log').write_text(' '.join(cmd) + '\n' + b.stdout + b.stderr + '\nexit=%d\n' % b.returncode)
if b.returncode:
    print(b.stderr[-3000:]); sys.exit(b.returncode)
cases = ['idle_reset', 'reset_inflight_direct', 'reset_inflight_hub',
         'reset_complete_direct', 'reset_complete_hub', 'reset_complete_then_input_hub',
         'listdisable_complete', 'edskip_inflight', 'edskip_complete',
         'complete_then_retire_control']
res = []
for c in cases:
    r = subprocess.run([str(out / 'fixture'), c], text=True, capture_output=True)
    res.append(dict(case=c, returncode=r.returncode, stdout=r.stdout, stderr=r.stderr[-1500:]))
    tail = (r.stderr.strip().splitlines() or [''])[-1]
    fails = [l for l in r.stdout.splitlines() if l.startswith('FAIL')]
    print('%-30s rc=%-4d %s %s' % (c, r.returncode, '; '.join(fails), tail if r.returncode < 0 or 'Assert' in tail else ''))
summary = dict(variant=name, ohci_sha256=hashlib.sha256(ohci_src.encode()).hexdigest(),
               core_sha256=hashlib.sha256(core_src.encode()).hexdigest(),
               extracted_ohci_sha256=hashlib.sha256('\n'.join(ohci_funcs).encode()).hexdigest(),
               build_command=cmd, passed=sum(r['returncode'] == 0 for r in res), total=len(res),
               cases=res)
(out / 'results.json').write_text(json.dumps(summary, indent=2) + '\n')
print('%s: %d/%d pass' % (name, summary['passed'], summary['total']))
