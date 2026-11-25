"""Create candidate (repair) and guardonly (negative control) copies of hcd-ohci.c
from the read-only astra-emu-fix source (which already carries the prior
shared-buffer patch).  Never writes to the astra tree."""
from pathlib import Path
import shutil

W = Path(__file__).resolve().parent
S = W.parent / 'astra-emu-fix' / 'source' / 'hw/usb/hcd-ohci.c'
base = S.read_text()

old1 = '''    if (ohci->async_td) {
        usb_cancel_packet(&ohci->usb_packet);
        ohci->async_td = 0;
    }
    for (i = 0; i < ohci->num_ports; i++) {'''
new1 = '''    if (ohci->async_td) {
        /*
         * A completed packet stays owned by async_td until its TD is
         * retired; only a packet still in flight can be cancelled.
         */
        if (usb_packet_is_inflight(&ohci->usb_packet)) {
            usb_cancel_packet(&ohci->usb_packet);
        }
        ohci->async_td = 0;
        ohci->async_complete = false;
    }
    for (i = 0; i < ohci->num_ports; i++) {'''
old2 = '''            if (ohci->async_td && addr == ohci->async_td) {
                usb_cancel_packet(&ohci->usb_packet);
                ohci->async_td = 0;
'''
new2 = '''            if (ohci->async_td && addr == ohci->async_td) {
                if (usb_packet_is_inflight(&ohci->usb_packet)) {
                    usb_cancel_packet(&ohci->usb_packet);
                }
                ohci->async_td = 0;
                ohci->async_complete = false;
'''
assert base.count(old1) == 1 and base.count(old2) == 1
# guard-only: same inflight guard, but leaves async_complete stale (negative control)
g1 = new1.replace('        ohci->async_complete = false;\n', '')
g2 = new2.replace('                ohci->async_complete = false;\n', '')

for name, text in (('baseline', base),
                   ('candidate', base.replace(old1, new1).replace(old2, new2)),
                   ('guardonly', base.replace(old1, g1).replace(old2, g2))):
    d = W / name / 'hw/usb'
    d.mkdir(parents=True, exist_ok=True)
    (d / 'hcd-ohci.c').write_text(text)
print('ok')
