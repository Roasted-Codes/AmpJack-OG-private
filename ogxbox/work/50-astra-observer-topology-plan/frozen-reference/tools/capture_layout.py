#!/usr/bin/env python3
"""Read-only compiler-derived i386 capture ABI, bound to frozen W32 ELF."""
import sys
sys.dont_write_bytecode=True
import json
from pathlib import Path
import re
import subprocess
import enum_watch as e

def prepare():
    integ=e.WORK.parent/'integration'
    frozen=e.WORK/'32-opus-final-integration/artifact/src'
    for name in ('ogx_module.h','ogx_present.h'):
        e.need((integ/name).read_bytes()==(frozen/name).read_bytes(),'capture header differs from frozen '+name)
    fields={
      'module_size':'sizeof(struct ogx_module)',
      'att_size':'sizeof(struct gdr_attach_ctx)',
      'ring':'offsetof(struct ogx_module, ring)',
      'ring_head':'offsetof(struct ogx_module, ring.head)',
      'ring_tail':'offsetof(struct ogx_module, ring.tail)',
      'ring_overflow':'offsetof(struct ogx_module, ring.overflow)',
      'evt_size':'sizeof(struct gdr_evt)',
      'ring_cap':'GDR_RING_CAP',
      'evt_data':'offsetof(struct gdr_evt, data)',
      'evt_type':'offsetof(struct gdr_evt, kind)',
      'gip_reports':'offsetof(struct ogx_module, gip.input_reports)',
      'gip_valid':'offsetof(struct ogx_module, gip.snapshot_valid)',
      'served':'offsetof(struct ogx_module, present.served_packet[1])',
      'served_seq':'offsetof(struct ogx_module, present.last_served_seq[1])',
      'native_mask':'offsetof(struct ogx_module, present.native_connected_mask)',
      'gamepad':'offsetof(struct ogx_module, gport[1].gamepad)',
      'port_valid':'offsetof(struct ogx_module, gport[1].snapshot_valid)',
      'vh':'offsetof(struct ogx_module, present.vh)',
      'vh_size':'sizeof(struct ogx_vhandle)',
      'present':'offsetof(struct ogx_module, present)',
    }
    source='#include <stddef.h>\n#include "ogx_module.h"\n'+'\n'.join('const unsigned o_'+k+' = '+v+';' for k,v in fields.items())+'\n'
    out=e.ROOT/'continuation-2/capture-abi';out.mkdir(parents=True,exist_ok=True)
    c=out/'probe.c';c.write_text(source)
    cmd=['clang','-target','i386-unknown-none-elf','-march=pentium3','-Os','-std=gnu11','-ffreestanding','-nostdlib','-fpie','-S','-o','-']
    for path in (integ,integ/'freestanding',integ.parent,integ.parent/'gip',integ.parent/'halo2',integ.parents[1]/'core',integ.parent/'gipdriver/src'):
        cmd+=['-I',str(path)]
    cmd.append(str(c));p=subprocess.run(cmd,capture_output=True,text=True)
    (out/'compiler.json').write_text(json.dumps(dict(command=cmd,returncode=p.returncode,stdout=p.stdout,stderr=p.stderr),indent=2)+'\n')
    e.need(p.returncode==0,'capture ABI compiler failed')
    values={m[1]:int(m[2],0) for m in re.finditer(r'^o_(\w+):\s*\n\s*\.long\s+(\S+)',p.stdout,re.M)}
    # Clang prints zero initializers using .zero rather than .long 0.
    values.update({m[1]:0 for m in re.finditer(r'^o_(\w+):\s*\n\s*\.zero\s+4',p.stdout,re.M)})
    e.need(set(fields)==set(values),'missing compiler ABI fields')
    e.need(values['module_size']==21132 and values['att_size']==1340,'frozen ABI size changed')
    e.need(e.sha(e.ELF.read_bytes())==e.HASHES['elf'],'capture ELF changed')
    result=dict(values=values,elf_sha256=e.HASHES['elf'],source_sha256=e.sha(source.encode()),
                headers={str(p):e.sha(p.read_bytes()) for p in (integ/'ogx_module.h',integ/'ogx_present.h',integ.parent/'gipdriver/src/gipdrive.h',integ.parent/'gip/og_gip.h')})
    (out/'layout.json').write_text(json.dumps(result,indent=2)+'\n')
    return result

if __name__=='__main__':print(json.dumps(prepare(),indent=2))
