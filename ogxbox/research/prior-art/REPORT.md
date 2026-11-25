# Worker 12 — Prior art: driving a wired Xbox One (GIP) pad, and what to fix in gipdriver

Scope: ogxbox/research/prior-art/ + ogxbox/work/12-prior-art/. Read-only research; no commits, no code
changes to ogxbox/gipdriver (worker 11 owns it). Sources read as raw bytes, with URLs and line
refs. Labels: VERIFIED = I read the source bytes; INFERENCE = my interpretation. Nothing here is a
new hardware measurement.

## TLDR

1. The current gipdriver endpoint guess is WRONG. It opens IN 0x82 / OUT 0x02; the Xbox One pad's
   GIP *data* interface uses IN 0x81 / OUT 0x01 (interrupt, 64 B, bInterval 4). 0x82/0x02 are the
   headset's isochronous endpoints, which will not open as interrupt.
2. The power-on/LED packet bytes already in gipdriver are correct and match Linux xpad and
   Ryzee119's tusb_xinput byte-for-byte. Add one more packet after power-on: the "S" init
   (05 20 ss 0f 06 ...) that Xbox One S / Elite 2 pads need to leave Bluetooth mode.
3. Both prior-art drivers (Linux xpad, tusb_xinput) auto-detect endpoints from the interface
   descriptor instead of hardcoding — but on the OG Xbox the interface/config descriptor fields are
   NOT populated at class-match (LoadClassDriver) time, so gipdriver should hardcode the correct
   0x81/0x01 (or fetch the config descriptor itself), not rely on the device struct.
4. No existing code drives a wired GIP pad over the *console's own OHCI*. The closest real prior art
   is Ryzee119's ogx360 (external MCU, uses tusb_xinput) plus Linux xpad/xone and AmpJack's own
   360 xw.xex GIP class driver. The gap this project fills is exactly the console-side GIP class driver.
5. First-party wired pads stream input after a bare power-on; the announce/identify/ACK dance is a
   refinement (only the guide/mode button needs an ACK). Keep the current "identify-then-blind-
   start" fallback, but it should be preceded by the correct endpoint open (0x81/0x01).

## What to change in ogxbox/gipdriver (no tables)

Each item: current → evidence-backed value, and the evidence. Worker 11 owns the code.

1. IN endpoint address: 0x82 → 0x81.
   Evidence: ogxbox/research/usb/REPORT.md §4 (lsusb -d 045e:02d1 -v, input-overlay #183):
   "IF0 (data): EP 0x01 OUT interrupt 64 B bInterval 4 / EP 0x81 IN interrupt 64 B bInterval 4 <- gamepad GIP";
   linuxhw/LsUSB PDP 0e6f:02a6 descriptor ("bEndpointAddress 0x81 … Interrupt … 64 bytes … bInterval 4");
   gip-pad crate (PDP 0e6f:0338): "interrupt IN 0x81, OUT 0x01, 64 bytes, 4 ms".
   Confidence: VERIFIED (three independent captures agree). Value is the same for every GIP data interface.

2. OUT endpoint address: 0x02 → 0x01.
   Evidence: same three sources; also MS-GIPUSB spec fixes the data interface at one 64-byte interrupt IN + one 64-byte interrupt OUT (worker 06 §2, learn.microsoft.com MS-GIPUSB).
   Confidence: VERIFIED.

3. What 0x82/0x02 actually are: they belong to interface 1 (headset), isochronous, 228 B, bInterval 1 —
   the pad's audio endpoints, NOT the gamepad path. The old guess mirrored the OG XID pad (which
   uses EP 0x82 IN / 0x02 OUT interrupt — xboxdevwiki Xbox_Input_Devices), but the GIP pad renumbers
   the data endpoints to EP1 and gives EP2 to audio. Opening address 0x82 as TransferType=3
   (interrupt) targets an isochronous endpoint and will fail to open.
   Evidence: ogxbox/research/usb/REPORT.md §4 (IF1 headset alt1: "EP 0x02 OUT isochronous 228 B / EP 0x82 IN isochronous 228 B").
   Confidence: VERIFIED.

4. Transfer type (interrupt = 3), bInterval (4), MaxPacketSize (64) in gdr_urb_open:
   all three are already correct. GIP data endpoints are interrupt (bmAttributes 0x03), wMaxPacketSize 0x0040, bInterval 4.
   Evidence: linuxhw PDP 0e6f:02a6; worker 01 §4; MS-GIPUSB "bInterval MUST be >= 4 ms".
   Confidence: VERIFIED.

5. Power-on packet: current gdr_build_power_on = 05 20 ss 01 00 (POWER, OPT_INTERNAL, seq, len 1, payload 0x00). CORRECT — identical to xpad.c xboxone_power_on (drivers/input/joystick/xpad.c:655-657) and tusb_xinput xboxone_power_on (xinput_host.c:45).
   Confidence: VERIFIED.

6. MISSING init packet — add an "S" power-on after the plain power-on. Bytes (tusb_xinput, xinput_host.c:46):
   05 20 ss 0f 06 00 00 00 00 00 00 55 53 00 00 00 00 00 00
   (POWER, OPT_INTERNAL, seq, len 0x0f, 15-byte payload ending "US" = region). xpad.c:665-667 sends a
   truncated form — 05 20 ss 0f 06 — and gates it to VID 045e, PID 02ea (One S) and 0b00 (Elite 2);
   tusb_xinput sends the full form to EVERY Xbox One pad. Purpose: force a pad previously paired in
   Bluetooth mode back into USB mode. Needed for the One S Bluetooth pad (045e:02ea) and Elite 2.
   Confidence: VERIFIED from code; whether the owner's specific pad needs it is INFERENCE (add it
   unconditionally — harmless, and it prevents a pad stuck in BT mode from staying silent).

7. LED packet: current gdr_build_led = 0a 20 ss 03 00 01 14 (LED, OPT_INTERNAL, seq, len 3, mode 0, on 1, brightness 0x14=20). CORRECT — matches xpad.c xboxone_led_on (693-694) and tusb xboxone_s_led_init (47).
   Confidence: VERIFIED.

8. Rumble-stop payload: current gdr_build_rumble_stop payload = 00 0f 00 00 00 00 ff 00 eb (9 bytes).
   xpad.c rumbleend init payload = 00 0f 00 00 00 00 00 00 00; tusb xboxone_rumble = 00 0f 00 00 00 00 ff 00 ff. The
   layout (motor mask 0x0f, trigger L/R, main L/R, duration/delay/repeat) matches; only the trailing
   repeat/last byte differs (0xeb in core/gip.c vs 0x00/0xff in xpad/tusb). For an all-off rumble the
   difference is immaterial, but core/gip.c's 0xeb (repeat) is the "spin-down infinitely" value — use
   xpad's 0x00 for the quiet repeat. Low priority: rumble is not required to receive input.
   Confidence: VERIFIED (bytes), INFERENCE (which repeat matters, since rumble is out of scope for the transport milestone).

9. Output URB direction/flags (FlagB0=2, FlagB1=1, Direction=0 "mirror XID"): these are copied from the
   XID producer and are NOT re-verified against how a non-XID class driver should fill the interrupt
   OUT transfer URB. tusb_xinput/xpad use the endpoint's direction from the descriptor (OUT = 0x01).
   FlagB0/FlagB1/Direction should be re-checked by worker 11 against the 09-urb pinned offsets; this
   prior-art search found no OG-side source to settle them.
   Confidence: INFERENCE / UNKNOWN (stays as-is until console run).

10. Announce/identify/ACK handling: current gipdriver sends IDENTIFY on announce and after 1.5 s blind-starts (power+LED+rumble). This matches core/gip.c's wired fallback and is sufficient for a first-party wired pad: it begins streaming GIP_CMD_INPUT after power-on with no ACK required (xpad sends init immediately on open for first-party pads; see xpad_prepare_next_init_packet xpad.c:1272-1309, and the delay_init quirk only applies to wireless dongles, xpad.c:74 + device-table FLAG_DELAY_INIT entries). No change needed for transport. One refinement to record (not required): the Xbox One S re-sends guide/mode-button reports (GIP_CMD_VIRTUAL_KEY 0x07) until they are ACKed — xpad acks them (xpadone_ack_mode_report xpad.c:1526-1545; mode_report_ack bytes 01 20 ss 09 00 07 20 02 00 00 00 00 00). tusb_xinput acks the same (xboxone_send_ack xinput_host.c:148-157). Only matters for the guide (Mode) button, later work.
    Confidence: VERIFIED (xpad/tusb), INFERENCE (needed only once guide button is wired up).

11. Audio-interface disable: xpad calls usb_set_interface(audio interface 1, alt 0) at start
    (xpad_start_xbox_one xpad.c:1500-1513) because some pads hold the guide button until the audio
    interface is disabled. Optional; not needed for basic input. Record, don't act.
    Confidence: VERIFIED from code.

12. Interface 0 targeting: the GIP pad is a 3-interface composite (data=0, audio=1, chatpad=2). xpad
    rejects anything where the matched interface's bNumEndpoints != 2 (xpad.c:2069-2070) and requires
    bInterfaceNumber == 0 (xpad.c:2129-2138). Our match is on the DEVICE descriptor class FF/47/D0,
    which is the whole device; the endpoints we must open live on interface 0. If worker 11 ever
    auto-parses endpoints, it must parse interface 0's descriptors, not the device's.
    Confidence: VERIFIED (xpad). worker 01 §4 lists the full 3-interface layout.

## Raw GIP init byte sequences (verbatim)

All sequences are [command, options, sequence, packet_length, payload...]. GIP framing is command,
options, sequence, then a LEB128 packet_length (single byte for these short packets) — identical to
the gdr_gip_frame layout in gipdrive.h. "ss" = sequence byte, replaced per-send by a counter. Each
is the byte stream on the wire (interrupt OUT).

Linux xpad.c (drivers/input/joystick/xpad.c, torvalds/linux master; constants at xpad.c:613-649):
- power_on        xpad.c:655-657   05 20 ss 01 00
- s_init          xpad.c:665-667   05 20 ss 0f 06                       (truncated: len field 0x0f, one payload byte)
- extra_input     xpad.c:674-676   4d 10 ss 02 07 00                    (Elite 2 paddles only)
- hori_ack_id     xpad.c:683-686   01 20 ss 09 00 04 20 3a 00 00 00 80 00
- led_on          xpad.c:693-694   0a 20 ss 03 00 01 14
- auth_done       xpad.c:701-703   06 20 ss 02 01 00                    (PDP only)
- rumblebegin     xpad.c:709-712   09 00 ss 09 00 0f 00 00 1d 1d ff 00 00   (PowerA only)
- rumbleend       xpad.c:720-723   09 00 ss 09 00 0f 00 00 00 00 00 00 00
- mode_report_ack xpad.c:1530-1533 01 20 ss 09 00 07 20 02 00 00 00 00 00

Ryzee119 tusb_xinput (github.com/Ryzee119/tusb_xinput, xinput_host.c; constants xinput_host.c:20-44):
- power_on        xinput_host.c:45 05 20 00 01 00
- s_init (full)   xinput_host.c:46 05 20 00 0f 06 00 00 00 00 00 00 55 53 00 00 00 00 00 00   (19 bytes, "US")
- s_led_init      xinput_host.c:47 0a 20 00 03 00 01 14
- extra_input     xinput_host.c:48 4d 10 00 02 07 00
- pdp_led_on      xinput_host.c:49 0a 20 00 03 00 01 14
- pdp_auth        xinput_host.c:50 06 20 00 02 01 00
- rumble          xinput_host.c:51 09 00 00 09 00 0f 00 00 00 00 ff 00 ff
- ack             xinput_host.c:52 01 20 00 09 00 <cmd> <opt&0x20> <b3> 00 00 00 00 00   (filled in xboxone_send_ack:148-157)

Current gipdriver (gipdrive.h) for comparison:
- power_on     gipdrive.h:247-250  05 20 ss 01 00
- led          gipdrive.h:251-254  0a 20 ss 03 00 01 14
- rumble_stop  gipdrive.h:255-259  09 00 ss 09 00 0f 00 00 00 00 ff 00 eb
- identify     gipdrive.h:260-262  04 20 ss 00

## Descriptor availability at class-match time (item 3)

Determinant evidence is already in-repo: work/09-diagnostic/REAL-CONSOLE-RESULT.md CAVEAT — at
USBD_LoadClassDriver time the interface/config descriptor pointer fields (ifsub, nep, niface, vendor,
product) still held the previous (stock XID) device's values; only the device-descriptor-derived
class (FF/47/D0 → PNP_CLASS_ID 0xFF81) was fresh. So on the OG Xbox the class match is computed from
the DEVICE descriptor, and the CONFIG/interface descriptors are not yet populated in the per-device
struct when LoadClassDriver/FindClassDriver runs.

This is consistent with two independent sources:
- xemu emulator source documents the kernel's standard enumeration order
  (xemu hw/xbox/chihiro/chihiro.c): "PortReset → GET_DESC → SET_ADDRESS → GET_CONFIG_DESC →
  SET_CONFIG (unconditional, per standard USB flow)". The class match (driven by _PNP_CLASS_ID) fires
  on the device descriptor after GET_DESC/SET_ADDRESS, BEFORE the config descriptor is fetched.
- Darkone83 Xbox-live-camera-research-project/RESEARCH.md (MOdded the OG USBD for the Xbox Cam):
  Connect flow is "USBD_DeviceEnumStage0→Pre1→1→3→6 → determine _PNP_CLASS_ID →
  USBD_LoadClassDriver → USBD_FindClassDriver(match) → Attach", and the driver's descriptor access is
  the IUsbDevice methods GetDeviceDescriptor() / GetConfigurationDescriptor() /
  GetInterfaceDescriptor() / GetEndpointDescriptor(iface,alt,ep). The camera project ultimately
  claimed its device manually off the tree rather than relying on the built-in attach path —
  corroborating that the built-in path does not hand the class driver a populated endpoint set.

Consequence for gipdriver (research finding, not a code change):
- Do NOT read the endpoint/interface fields off the IUsbDevice struct at Attach time; they may still
  alias the previous device. Either hardcode the correct data-interface endpoints (IN 0x81 / OUT 0x01,
  interrupt, 64 B, interval 4) — the evidence-backed value for every first-party and most third-party
  GIP pad — or, to be model-robust, issue our own GET_DESCRIPTOR(config) control transfer inside
  Attach and parse interface 0's endpoint descriptors the way xpad.c:2140-2157 and
  tusb_xinput:306-334 do.
- Linux xpad never hardcodes endpoint addresses: it iterates intf->cur_altsetting->endpoint[] and
  takes the interrupt IN and interrupt OUT (xpad.c:2140-2157), with bInterval taken verbatim from the
  endpoint descriptor (xpad.c:2163-2168). That is the pattern to copy if worker 11 adds a config-descriptor fetch.

## Provenance correction (honesty)

The brief named a "Ryzee119 usbh_xinput library inside nxdk / libusbohci / tinyusb host." There is no
nxdk library that drives a wired Xbox One pad over the console's OHCI: nxdk's libusbohci ships only an
XID driver (XboxDev/nxdk lib/usb/libusbohci_xbox/xid_driver.c, per worker 06 §1). Ryzee119's real
work is tusb_xinput (github.com/Ryzee119/tusb_xinput) — a TinyUSB HOST driver — which he uses in
ogx360 (github.com/Ryzee119/ogx360), an external MCU adapter (Pro Micro/Teensy) that speaks GIP to a
wired Xbox One pad and re-emits a Duke/Controller-S XID to the console. ogx360 is the closest thing to
"existing code that drives a wired Xbox One pad for OG Xbox hardware," but it runs on an external MCU,
not on the console's OHCI. The single closest console-side analogue of the project's own design is
AmpJack's 360 USB class driver (xbox360/xw_plugin.c registers FF/47/D0 into the 360 kernel's USB
driver list) — the same "GIP class driver registered into Usbd's class table" approach, on the 360.
This project (OG Xbox, title-local XInitDevices) is the first to do it on the console's own OHCI; the
prior-art value above is the GIP wire protocol + init sequences + endpoint selection, which are
identical regardless of which USB host carries them.

## Cited sources

- Linux xpad.c (VERIFIED, raw): https://raw.githubusercontent.com/torvalds/linux/master/drivers/input/joystick/xpad.c
  (lines cited inline above).
- Ryzee119 tusb_xinput (VERIFIED, raw): https://github.com/Ryzee119/tusb_xinput — xinput_host.c (lines
  cited inline), xinput_host.h (CFG_TUH_XINPUT_EPIN/EPOUT_BUFSIZE 64, xinput_host.h:22-31).
- Ryzee119 ogx360 (referenced): https://github.com/Ryzee119/ogx360 (release note "V1.4 default firmware
  now supports Xbox one wired controllers").
- Darkone83 Xbox Cam RESEARCH.md (referenced): https://github.com/Darkone83/Xbox-live-camera-research-project/blob/main/RESEARCH.md.
- xemu chihiro.c enumeration-order comment (referenced):
  https://github.com/xemu-project/xemu/blob/50fc538657f44704e0d1d0906bdc9ef6e435dffe/hw/xbox/chihiro/chihiro.c.
- linuxhw/LsUSB PDP 0e6f:02a6 descriptor (user-submitted lsusb, VERIFIED bytes).
- gip-pad crate (PDP 0e6f:0338, user-captured, VERIFIED bytes): https://crates.io/crates/gip-pad.
- MS-GIPUSB spec (referenced): learn.microsoft.com MS-GIPUSB, and the "GIP data interface = 64-byte
  interrupt IN/OUT, bInterval >= 4 ms" summary already at worker 06 §2.
- In-repo: ogxbox/research/usb/REPORT.md §4 (descriptor table), work/09-diagnostic/REAL-CONSOLE-RESULT.md (CAVEAT).
