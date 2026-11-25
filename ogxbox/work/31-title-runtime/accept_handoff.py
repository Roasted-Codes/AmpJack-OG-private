#!/usr/bin/env python3
"""Accept the already-paused work31 handoff. Read guest only; never resume.

Single QMP client for the whole run (the QMP socket accepts one client) and the
RSP client is opened inside the shared QMP window; both are read-only.
"""
import hashlib
import json
from pathlib import Path
import struct
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, '/home/roasted/Desktop/Xbox/LAN_Stats/tools/xemu')
sys.path.insert(0, '/home/roasted/Desktop/Xbox/LAN_Stats/tools')
from gdbrsp import RSP
from qmp import QMP
XBE_PATH = '/home/roasted/Desktop/Xbox/H2-Decomp/tu15-decomp/targets/halo2-tu15-u803/default.xbe'
XBE_SHA = '21b207e7efdacaf6124a0822837f8be570766a42505057f7fd2d2ba8f409c4fd'

handoff = json.loads((ROOT / 'HANDOFF.json').read_text())
pid = handoff['native_pid']
stat = Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()
assert int(stat[19]) == handoff['native_starttime_ticks'], 'Native PID was reused'
assert hashlib.sha256(Path(handoff['native_exe']).read_bytes()).hexdigest() == handoff['native_exe_sha256']

result = {'native_pid': pid, 'native_identity_verified': True}
q = QMP(handoff['qmp'], timeout=10)
r = None
try:
    result['qmp_before'] = q.cmd('query-status')
    assert not result['qmp_before']['running'], result['qmp_before']

    r = RSP(port=1239, timeout=4)
    result['stop_reason'] = r.reason()
    xml = r.target_xml()
    parse_xml = xml.replace('<target>', '<target xmlns:xi="http://www.w3.org/2001/XInclude">', 1)
    docs = [parse_xml]
    includes = ET.fromstring(parse_xml).findall('.//{http://www.w3.org/2001/XInclude}include')
    for inc in includes:
        docs.append(r.target_xml(inc.attrib['href']))
    registers = [reg for doc in docs for reg in ET.fromstring(doc).iter('reg')]
    names = [reg.attrib['name'] for reg in registers[:16]]
    assert names == 'eax ecx edx ebx esp ebp esi edi eip eflags cs ss ds es fs gs'.split(), names
    raw = r.raw_regs()
    regs = struct.unpack('<16I', bytes.fromhex(raw)[:64])
    assert regs[8] == 0x2da9de, hex(regs[8])
    result.update(eip=hex(regs[8]), esp=hex(regs[4]), raw_register_packet=raw,
                  target_xml=xml, core_register_names_verified=names)

    # frozen header comparison with only 0x128 entry / 0x158 thunk permitted to
    # differ (live = kernel-decoded). Do not read or touch any other scan region.
    import importlib
    xbe_va = importlib.import_module('xbe_va')
    x = xbe_va.XBE(XBE_PATH, expect_sha256=XBE_SHA)
    live = r.read(x.base, 0x178)
    assert live[0x114:0x118] == bytes.fromhex('2b a6 00 46')
    expected = bytearray(x.data[:0x178])
    fields = {}
    for off, decoded in [(0x128, x.entry), (0x158, x.kernel_thunk)]:
        observed = struct.unpack_from('<I', live, off)[0]
        disk = struct.unpack_from('<I', expected, off)[0]
        assert observed in (disk, decoded), (hex(off), hex(observed), hex(disk), hex(decoded))
        fields[hex(off)] = {'disk': hex(disk), 'live': hex(observed), 'decoded': hex(decoded)}
        struct.pack_into('<I', expected, off, observed)
    assert live == bytes(expected), 'Live header differs beyond the two decoded fields'
    result.update(live_header_hex=live.hex(), header_fields=fields, header_other_bytes_exact=True)
finally:
    if r is not None:
        r.close()
    result['qmp_after'] = q.cmd('query-status')
    assert not result['qmp_after']['running'], result['qmp_after']
    result['clients_closed'] = True
    q.close()

(ROOT / 'PARENT-ACCEPTED.json').write_text(json.dumps(result, indent=2) + '\n')
summary = {k: v for k, v in result.items() if k not in ('raw_register_packet', 'target_xml', 'live_header_hex')}
print(json.dumps(summary, indent=2))
