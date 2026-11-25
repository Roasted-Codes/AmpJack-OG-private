#!/usr/bin/env python3
"""gen_layout.py -- publish the loader layout for ONE exact ELF from the compiler's
own i386 offsetof() (clang -target i386-unknown-none-elf, the build_pic.sh flags),
never from hand arithmetic. Usage: gen_layout.py <pic.elf> <out.json>"""
import hashlib, json, re, subprocess, sys, tempfile, os
from pathlib import Path

ELF, OUT = Path(sys.argv[1]), Path(sys.argv[2])
INTEG = Path(__file__).resolve().parents[1] / 'src/ogxbox/integration'
HOST = ['submit_request', 'findclassdriver', 'add_complete', 'cancel_request', 'remove_complete',
        'class_table_begin', 'class_table_end', 'xdevice_type_gamepad', 'now_ms',
        'irql_raise_slot', 'irql_lower_slot']
STATUS = ['attached', 'installed_hooks', 'install_failed']
src = ['#include <stddef.h>', '#include "ogx_module.h"',
       'const unsigned o_sizeof_module = sizeof(struct ogx_module);',
       'const unsigned o_sizeof_host = sizeof(struct ogx_mod_host);',
       'const unsigned o_sizeof_att = sizeof(struct gdr_attach_ctx);',
       'const unsigned o_host = offsetof(struct ogx_module, host);']
src += [f'const unsigned o_h_{f} = offsetof(struct ogx_mod_host, {f});' for f in HOST]
src += [f'const unsigned o_s_{f} = offsetof(struct ogx_module, {f});' for f in STATUS]
with tempfile.TemporaryDirectory() as td:
    c = Path(td) / 'probe.c'; c.write_text('\n'.join(src) + '\n')
    cmd = ['clang', '-target', 'i386-unknown-none-elf', '-march=pentium3', '-Os', '-std=gnu11', '-ffreestanding',
           '-nostdlib', '-fpie', '-S', '-o', '-', '-I', str(INTEG), '-I', str(INTEG / 'freestanding'), '-I', str(INTEG.parent),
           '-I', str(INTEG.parent / 'gip'), '-I', str(INTEG.parent / 'halo2'), '-I', str(INTEG.parents[1] / 'core'),
           '-I', str(INTEG.parent / 'gipdriver/src'), str(c)]
    asm = subprocess.run(cmd, capture_output=True, text=True, check=True).stdout
v = {m.group(1): int(m.group(2), 0) for m in re.finditer(r'^(o_\w+):\s*\n\s*\.long\s+(\S+)', asm, re.M)}
need = ['o_sizeof_module', 'o_sizeof_host', 'o_host'] + [f'o_h_{f}' for f in HOST] + [f'o_s_{f}' for f in STATUS]
missing = [k for k in need if k not in v]
assert not missing, missing
data = ELF.read_bytes()
lay = {
    '_comment': 'Module ABI layout for ONE exact ELF (work/65 rumble). Offsets from clang i386 offsetof() of the '
                'current integration headers (tools/gen_layout.py); bound to elf_sha256. Not valid for any other ELF.',
    'elf_sha256': hashlib.sha256(data).hexdigest(),
    'entry_symbol': 'ogx_module_entry', 'entry_abi': 'cdecl(void*)',
    'module_symbol': 'ogx_g_module', 'module_size': v['o_sizeof_module'],
    'host_offset': v['o_host'],
    'host_fields': [[f, v[f'o_h_{f}']] for f in HOST],
    'host_size': v['o_sizeof_host'],
    'now_ms_abi': 'stdcall_u32',
    'irql_abi': {'irql_raise_slot': 'import slot -> stdcall KIRQL KeRaiseIrqlToDpcLevel(void), ord 129',
                 'irql_lower_slot': 'import slot -> fastcall void KfLowerIrql(KIRQL in CL), ord 161'},
    'status_fields': {f: v[f'o_s_{f}'] for f in STATUS},
    'expected_installed_hooks': 191,
    'hook_targets': {'FindClassDriver': 'ogx_findclassdriver', 'XGetDeviceChanges': 'ogx_stub_xgetdevicechanges',
                     'XInputOpen': 'ogx_stub_xinputopen', 'XInputClose': 'ogx_stub_xinputclose',
                     'XInputGetCapabilities': 'ogx_stub_xinputgetcaps', 'XInputGetState': 'ogx_stub_xinputgetstate',
                     'XInputSetState': 'ogx_stub_xinputsetstate'},
    '_measured': {'sizeof_gdr_attach_ctx': v['o_sizeof_att']},
}
OUT.write_text(json.dumps(lay, indent=2) + '\n')
print(json.dumps(lay, indent=2))
