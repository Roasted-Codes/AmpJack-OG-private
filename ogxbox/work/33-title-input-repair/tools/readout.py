#!/usr/bin/env python3
"""Bound status readout for the installed AmpJack module (work33).

Addresses: module_addr = journal['module'] (== base + ELF sym ogx_g_module, asserted),
struct offsets from tools/offsets.txt (clang offsetof of the actual final structs,
SIZEOF_module asserted == layout module_size), statics from ELF symbols + journal base.
Binding: title timestamp, the seven live E9 sites == journal expect, live module .text
== relocated ELF .text. Reads over the existing loopback RSP stub and ALWAYS continues
(the guest is left running). Usage: readout.py JOURNAL OUT.json [--port 1239]
"""
import hashlib, json, subprocess, sys, time
from pathlib import Path
sys.path.insert(0, '/home/roasted/Desktop/Xbox/LAN_Stats/tools/xemu')
from gdbrsp import RSP

HERE = Path(__file__).resolve().parent
ELF = HERE.parents[1] / '32-opus-final-integration/artifact/pic.elf'
LAYOUT = json.loads((HERE.parents[1] / '32-opus-final-integration/artifact/layout.json').read_text())
STATICS = ['ogx_attach_ran', 'ogx_seen_generation', 'ogx_gen_resyncs', 'ogx_hold_removal', 'ogx_lost_events',
           'ogx_span_refused', 'ogx_span_revalid', 'ogx_pub_seq', 'ogx_pub_reports', 'g_pump_depth']


def syms():
    out = subprocess.run(['llvm-nm', str(ELF)], capture_output=True, text=True, check=True).stdout
    return {l.split()[2]: int(l.split()[0], 16) for l in out.splitlines() if len(l.split()) == 3}


def main():
    jpath, outp = Path(sys.argv[1]), Path(sys.argv[2])
    port = int(sys.argv[sys.argv.index('--port') + 1]) if '--port' in sys.argv else 1239
    j = json.loads(jpath.read_text())
    elf_bytes = ELF.read_bytes()
    assert hashlib.sha256(elf_bytes).hexdigest() == j['elf_sha256'] == LAYOUT['elf_sha256'], 'ELF/journal/layout mismatch'
    off = {l.split()[0]: int(l.split()[1]) for l in (HERE / 'offsets.txt').read_text().splitlines()}
    assert off['SIZEOF_module'] == LAYOUT['module_size'] and off['OFF_attached'] == LAYOUT['status_fields']['attached']
    S = syms()
    base, mod = j['base'], j['module']
    assert mod == base + S['ogx_g_module'], 'journal module != base + ogx_g_module'
    res = dict(epoch=time.time(), journal=str(jpath), base=hex(base), module=hex(mod), elf_sha256=j['elf_sha256'])
    r = RSP(port=port, timeout=5)
    try:
        regs = r.regs(); res['eip_at_sample'] = hex(regs['eip'])
        res['title_ts'] = r.read(0x10114, 4).hex()
        res['title_ok'] = res['title_ts'] == '2ba60046'
        res['sites_ok'] = all(r.read(s['va'], len(s['expect']) // 2).hex() == s['expect'] for s in j['sites'].values())
        # .text binding: compare live code against ELF file bytes of the first PT_LOAD R-X segment
        txt = subprocess.run(['llvm-readelf', '-S', '-W', str(ELF)], capture_output=True, text=True).stdout
        for line in txt.splitlines():
            p = line.replace('[ ', '[').split()
            if len(p) > 6 and p[1] == '.text':
                va, fo, sz = int(p[3], 16), int(p[4], 16), int(p[5], 16)
                live = r.read(base + va, sz)
                res['text_ok'] = live == elf_bytes[fo:fo + sz]
                res['text_extent'] = [hex(va), sz]
        blob = r.read(mod, off['SIZEOF_module'])
        f = {}
        for k, o in off.items():
            if k.startswith('OFF_'):
                n = 18 if k == 'OFF_gip_snap' else (64 if k == 'OFF_present_vh' else (16 if k in ('OFF_present_prev_present', 'OFF_present_gen', 'OFF_present_served_packet', 'OFF_present_last_served_seq', 'OFF_present_last_served_gen') else 4))
                v = blob[o:o + n]
                f[k[4:]] = v.hex() if n != 4 else hex(int.from_bytes(v, 'little'))
        res['fields'] = f
        res['statics'] = {n: hex(int.from_bytes(r.read(base + S[n], 4), 'little')) for n in STATICS if n in S}
    finally:
        r.cont(); r.close()
    res['resumed'] = True
    outp.write_text(json.dumps(res, indent=1))
    print(json.dumps(res, indent=1))


if __name__ == '__main__':
    main()
