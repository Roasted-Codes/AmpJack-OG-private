#!/usr/bin/env python3
"""NEXT-BOOT diagnostic (UNTESTED LIVE: the runtime31 guest is dead-halted, so
this could not be exercised this slice). Parent-owned use only, on a fresh
authorized boot, attached BEFORE the GIP pad enumerates.

Records every event that can leave the Halo 2 u803 XPP enumeration timer armed
with g_current_enum (0x490930) == NULL, which is the verified crash condition:
  Z2 write watch 0x490930 (current enum device)
  Z0 0x41672E  KeSetTimer arm of the enum timer (stage byte 0x490928 = 0)
  Z0 0x416992  IUsbDevice::AddComplete entry (who calls it, status, device)
  Z0 0x41668E  EnumNext entry
  Z0 0x416568  fault site mov edi,[esi+0xC]; if ESI==0 it STOPS and leaves the
               CPU halted (intentional authenticated stop) instead of letting
               the bugcheck recurse into XBDM's crashdump/0xCF9 halt.
Every other stop is logged then continued. One RSP client; finally always 'c'
unless the fault stop was reached. Byte-check XPP before arming.
usage: enum_watch.py LOG.jsonl [--port 1239] [--seconds 1800]
"""
import argparse, json, os, struct, sys, time
sys.path.insert(0, os.path.expanduser('~/Desktop/Xbox/LAN_Stats/tools/xemu'))
from gdbrsp import RSP

EXPECT = {  # verified live bytes (work/35-loading-stop/probe3, XBE ts 0x4600a62b)
    0x41655F: '5356 8b3530094900 57 8b7e0c'.replace(' ', ''),
    0x41672E: '00ff15f8b64100'[2:],
    0x416992: '558bec83ec0c',
}
BPS = [0x41672E, 0x416992, 0x41668E, 0x416568]


def snap(r):
    g = r.regs(); st = r.read(0x4908B0, 0x90)
    return {'t': time.time(), 'eip': hex(g['eip']), 'esp': hex(g['esp']), 'ecx': hex(g['ecx']),
            'esi': hex(g['esi']), 'stack': r.read(g['esp'], 20).hex(),
            'b0_b3': st[0:4].hex(), 'stage_490928': st[0x78], 'pending_49092c': hex(struct.unpack_from('<I', st, 0x7c)[0]),
            'current_490930': hex(struct.unpack_from('<I', st, 0x80)[0])}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('log'); ap.add_argument('--port', type=int, default=1239)
    ap.add_argument('--seconds', type=int, default=1800); a = ap.parse_args()
    r = RSP(port=a.port, timeout=10); keep_halted = False
    out = open(a.log, 'a')
    try:
        if r.last_stop is None:
            r.reason()
        assert r.read(0x10114, 4) == bytes.fromhex('2ba60046'), 'not Halo 2 u803'
        for addr, hx in EXPECT.items():
            assert r.read(addr, len(hx) // 2).hex() == hx, hex(addr)
        assert r.cmd('Z2,490930,4') == 'OK'
        for b in BPS: r.bp(b)
        end = time.time() + a.seconds
        while time.time() < end:
            try:
                why = r.continue_wait(timeout=min(60, max(1, end - time.time())))
            except TimeoutError:
                continue  # interrupted+paused by helper; loop continues it
            s = snap(r); s['why'] = why; out.write(json.dumps(s) + '\n'); out.flush()
            if int(s['eip'], 16) == 0x416568 and s['esi'] == '0x0':
                keep_halted = True; break
            if 'watch' not in why and int(s['eip'], 16) in BPS:  # step off the bp
                b = int(s['eip'], 16); r.bp(b, False); r.step(); r.bp(b)
    finally:
        try:
            if not keep_halted:
                r.cmd('z2,490930,4')
                for b in BPS: r.bp(b, False)
                r.cont()
        finally:
            r.close(); out.close()
    print('fault reached, CPU left halted' if keep_halted else 'window ended, guest continued')


if __name__ == '__main__':
    main()
