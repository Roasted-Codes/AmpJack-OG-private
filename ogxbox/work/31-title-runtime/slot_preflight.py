#!/usr/bin/env python3
"""Read-only preflight of the paused work31 guest: confirm it is still held at
entry and that the kernel-resolved import slots the loader depends on are live,
BEFORE any allocation or module write."""
import json
import struct
import sys
from pathlib import Path

sys.path.insert(0, '/home/roasted/Desktop/Xbox/LAN_Stats/tools/xemu')
from gdbrsp import RSP

ROOT = Path(__file__).resolve().parent
handoff = json.loads((ROOT / 'HANDOFF.json').read_text())

slot = {0x41B640: 'MmAllocateContiguousMemoryEx (ord 166)',
        0x41B700: 'KeRaiseIrqlToDpcLevel (ord 129)',
        0x41B6FC: 'KfLowerIrql (ord 161)'}

r = RSP(port=1239, timeout=4)
try:
    regs = r.regs()
    assert regs['eip'] == 0x2DA9DE, hex(regs['eip'])
    out = {'eip': hex(regs['eip']), 'esp': hex(regs['esp']), 'slots': {}}
    for va, label in slot.items():
        val = struct.unpack('<I', r.read(va, 4))[0]
        out['slots'][hex(va)] = {'label': label, 'value': hex(val),
                                 'resolved': bool(val & 0x80000000 and not (val & 0x7FFFFFFF) == 0)}
finally:
    r.close()
(ROOT / 'slot-preflight.json').write_text(json.dumps(out, indent=2) + '\n')
print(json.dumps(out, indent=2))
