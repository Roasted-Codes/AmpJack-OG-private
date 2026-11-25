from pathlib import Path
import struct, subprocess
p=Path(__file__).resolve().parent;b=(p/'appimage/usr/bin/xemu').read_bytes()
targets={0x279e9e:'too_many_pending',0x2cae1d:'td_pkt_hdr',0x29a977:'async_complete'}
for i in range(0x55cf40,0x101bc60-7):
 if b[i] in (0x48,0x4c) and b[i+1]==0x8d and (b[i+2]&0xc7)==5:
  dest=i+0x1000+7+struct.unpack_from('<i',b,i+3)[0]
  if dest in targets:
   va=i+0x1000;print(targets[dest],hex(va))
   r=subprocess.run(['objdump','-d','-Mintel',f'--start-address={va-300}',f'--stop-address={va+300}',str(p/'appimage/usr/bin/xemu')],capture_output=True,text=True)
   (p/f'xemu-{targets[dest]}-{va:x}.disasm.txt').write_text(r.stdout)
