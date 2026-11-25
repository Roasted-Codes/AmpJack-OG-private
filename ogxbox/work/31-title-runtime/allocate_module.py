#!/usr/bin/env python3
"""Allocate the 0x9000-byte module block on the paused work31 guest and write the
loader receipt. Uses the exact proven MmAllocateContiguousMemoryEx allocator stub
from LAN_Stats inject_trainer; fills + reads back; does NOT load or run entry."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, '/home/roasted/Desktop/Xbox/LAN_Stats/tools/xemu')
sys.path.insert(0, '/home/roasted/Desktop/Xbox/LAN_Stats/tools')
from gdbrsp import RSP
from inject_trainer import run_stub

SCRATCH = 0x233194
ALLOC_CODE = bytes.fromhex('ff 15 40 b6 41 00 cc')   # call [MmAllocateContiguousMemoryEx]; int3
SIZE = 0x9000
FILL = 0xFF

r = RSP(port=1239, timeout=5)
try:
    assert r.regs()['eip'] == 0x2DA9DE, 'guest not at entry'
    res = run_stub(r, SCRATCH, ALLOC_CODE, (SIZE, 0, 0xffffffff, 0, 0x4), require_padding=True)
    buf = res['eax']
    assert buf and buf != 0, 'allocation returned NULL'
    base = buf & ~0xFFF
    if base < buf:
        base += 0x1000
    assert base + SIZE <= buf + SIZE, 'rounding exceeded allocation'
    r.write(base, bytes([FILL]) * SIZE)
    assert r.read(base, SIZE) == bytes([FILL]) * SIZE, 'fill readback mismatch'
    receipt = {'base': base, 'extent': SIZE, 'fill_byte': FILL,
               'allocation_id': 'work31-module-1'}
finally:
    r.close()
(ROOT / 'allocation-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps({'allocator_eax': hex(buf), 'base': hex(base),
                  'extent': hex(SIZE)}, indent=2))
