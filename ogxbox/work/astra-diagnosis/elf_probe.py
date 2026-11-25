from pathlib import Path
import importlib.util,subprocess
p=Path(__file__).resolve().parent
for n in ['capstone','elftools','unicorn']:
 print(n, bool(importlib.util.find_spec(n)))
b=(p/'appimage/usr/bin/xemu').read_bytes()
for key in [b'ohci_service_td',b'usb_ohci_td_too_many_pending',b'usb_ohci_td_pkt_hdr',b'usb_ohci_async_complete',b'0.8.136']:
 start=0
 while (i:=b.find(key,start))>=0:
  print(hex(i),repr(b[max(0,i-20):i+len(key)+100]));start=i+len(key)
r=subprocess.run(['readelf','-Wl',str(p/'appimage/usr/bin/xemu')],capture_output=True,text=True)
print(r.stdout)
