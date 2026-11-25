# Real pad on the dev PC — 2026-11-24 12:01

Microsoft Xbox Series S|X Controller, VID 045e PID 0b12, bcdDevice 5.09, full-speed (12 Mb/s),
device class FF/47/D0, bMaxPacketSize0 64, 1 configuration (bConfigurationValue 1), 3 interfaces,
all class FF/47/D0. Full dump: lsusb-045e-0b12.txt (VERIFIED, lsusb -v on this host).

Interface 0 (GIP data), alt 0: EP **0x02 OUT** interrupt 64 B bInterval 4, EP **0x82 IN** interrupt 64 B bInterval 4.
  alt 1: same addresses, IN bInterval 2.
Interface 1 (audio): alt 0 no endpoints; alt 1 EP 0x03 OUT iso 228 B, EP 0x83 IN iso 64 B.
Interface 2: alt 0 no endpoints; alt 1 two endpoints (see dump).

IMPORTANT: worker12's prior-art report says GIP data is 0x81/0x01 — that is true for the older Xbox One
pads it cited (045e:02d1, PDP 0e6f:xxxx). THIS pad (0b12) uses 0x82/0x02 and puts audio on EP3.
Conclusion: endpoint addresses MUST be read from the configuration descriptor at runtime, never hardcoded.
Both facts are now test fixtures for the gipdriver Attach state machine (worker14).

Host side: udev rule /etc/udev/rules.d/70-xbox-gip-passthrough.rules (uaccess for 045e:0b12) installed with
owner approval; /dev/bus/usb/003/004 now has user:roasted:rw-. Linux xpad is bound to it; QEMU usb-host
detaches the kernel driver itself when it claims the device.
