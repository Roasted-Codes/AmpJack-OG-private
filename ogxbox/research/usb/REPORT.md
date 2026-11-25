# Worker 01 — USB enumeration/speed/hub feasibility for wired Xbox One pads on OG Xbox

Owner: Roasted (AmpJack-OG, milestone = wired Xbox One INPUT in Halo 2 only).
Worker owns: `ogxbox/research/usb/` and `ogxbox/work/01-usb/`.
Upstream AmpJack: `b83cf6546e7d04c6013571d4641cb3e482b05e94` (this port's HEAD, re-verified `git rev-parse HEAD`).

Label discipline used throughout: VERIFIED = observed source bytes or real local
execution; REFERENCE = a cited third-party/labelled external capture or source I read
but did not capture myself; INFERENCE = my interpretation; UNKNOWN = hardware fact
with no evidence present.

## 1. Headline answer

The wired Xbox One controller family is a **full-speed USB device**. Every listed
model enumerates at 12 Mbps on a USB 1.1 / OHCI host — full speed is the device's
native speed, not a negotiated fallback. The OG Xbox's two MCPX OHCI controllers are
USB 1.1 full-speed hosts, so the pads **will electrically enumerate full-speed** once a
passive controller-port-to-USB cable is attached.

This is a USB-physics YES. It does **not** mean the pad controls Halo 2: no shipped OG
Xbox software has a GIP class driver (the console only speaks XID), so playable input
is blocked at the *software* layer (a driver/shim + title XInput hook — workers 02/03/04),
not at enumeration. Do not conflate the two.

## 2. Evidence-backed gate table (USB full-speed enumeration only)

| Model (VID:PID) | Full-speed enumerate on OHCI? | Key evidence |
|---|---|---|
| Xbox One 2013, model 1537 (045e:02d1) | **YES** | Full `lsusb -v`: bcdUSB 2.00, class FF/47/D0, bMaxPacketSize0 64, IF0 EP 0x01/0x81 interrupt 64 B bInterval 4 [REF: input-overlay #183] |
| Xbox One 2015 w/ 3.5 mm "Firmware 2015" (045e:02dd) | **YES** (same data IF) | xpad device table, `XTYPE_XBOXONE`; 64-B interrupt path [VERIFIED: xpad.c:128] |
| Xbox One S / Bluetooth (045e:02ea) | **YES** | xpad `xboxone_s_init` + same 64-B GIP data interface [REF]; wired mode is GIP, not BT |
| Xbox One Elite v1 (045e:02e3) | **YES** | Full `lsusb -v`: EP 0x01/0x81 interrupt 64 B bInterval 4 [REF: opensuse forum] |
| Xbox One Elite v2 (045e:0b00) | **YES** | xpad device table; same GIP data path [VERIFIED: xpad.c:132] |
| Xbox Adaptive Controller (045e:0b0a) | **YES** | xpad `XTYPE_XBOXONE` [VERIFIED: xpad.c:133] |
| Xbox Series X\|S (045e:0b12) | **YES** (secondary) | `lsusb`: EP 0x02/0x82 interrupt 64 B bInterval 4 [REF: linuxhw] |
| Third-party GIP pads (PDP/Mad Catz/PowerA/Hori/…) | **YES** | BOS "Lowest fully-functional device speed = Full Speed (12 Mbps)" [REF: linuxhw 0e6f:02b8] |

"Enumerate full-speed" = YES for all in-scope pads. Per-model UNKNOWNs are power and
presence (see §7), not speed.

## 3. Why bcdUSB == 2.00 is not the answer (and why it doesn't have to be)

- USB 2.0 permits a **full-speed-only device to report `bcdUSB` 0x0200**: the field
  states spec compliance, not link speed. The decisive facts are the endpoint
  descriptors and the actual negotiated speed, not `bcdUSB`.
- Stronger: a high-speed USB 2.0 device **must also be full-speed capable** — the bus
  always connects at full speed and high speed is negotiated afterwards via the chirp
  handshake (USB 2.0 §7.1.7.5). There are no compliant "high-speed-only" devices.
  Therefore even a high-speed-capable third-party pad still enumerates full-speed on OHCI.
- The pads' interrupt endpoints are `wMaxPacketSize = 0x0040` (64), which is **exactly
  the full-speed ceiling** for interrupt endpoints (USB 2.0 §9.6.6, table 9-10: full-speed
  interrupt = 1–64 B; high-speed allows up to 1024 B). A device that needed high speed
  would not cap its only data endpoint at the full-speed maximum.

## 4. Descriptor / endpoint evidence (consolidated)

First-party Microsoft Xbox One controller (045e:02d1), complete descriptor
[REF: user-submitted `lsusb -d 045e:02d1 -v`, github univrsal/input-overlay issue #183;
confirmed independently by linuxhw/LsUSB file E0687D11BB and xone/xpad source]:

```
Device Descriptor:  bcdUSB 2.00, class 255/71(0x47)/208(0xD0), bMaxPacketSize0 64
Configuration:      bNumInterfaces 3, bMaxPower 500 mA
  IF0 (data):       EP 0x01 OUT interrupt 64 B bInterval 4
                    EP 0x81 IN  interrupt 64 B bInterval 4   <- gamepad GIP
  IF1 (headset):    alt0: 0 endpoints
                    alt1: EP 0x02 OUT isochronous 228 B bInterval 1
                          EP 0x82 IN  isochronous 228 B bInterval 1
  IF2 (chatpad):    alt0: 0 endpoints
                    alt1: EP 0x03 OUT bulk 64 B, EP 0x83 IN bulk 64 B
```

Cross-checked against the two Linux implementations I read:

- **xone** `transport/wired.c` (local copy under
  `_Parked/x360-padbridge/.../sources/xone-current/transport/wired.c`):
  `XONE_WIRED_INTF_DATA 0` / `_AUDIO 1`, match class `USB_CLASS_VENDOR_SPEC / 0x47 /
  0xd0`, `XONE_WIRED_LEN_DATA_PKT 64`, `usb_fill_int_urb` on `port->ep_in` (interrupt IN,
  64-B buffer, `bInterval`), audio via isochronous on interface 1, `.id_table` matches any
  vendor on interface 0 with class FF/47/D0. VERIFIED source bytes (lines cited in §11).
- **Linux `xpad.c`**: `XPAD_PKT_LEN 64`; `XTYPE_XBOXONE` reads interrupt IN; device table
  lines 127–134 list exactly 045e:02d1/02dd/02e3/02ea/0b00/0b0a/0b12. VERIFIED.

In-repo AmpJack corroboration (VERIFIED source bytes, this port's HEAD):

- `xbox360/xw_priv.h:26-29`: `#define PKT_MAX 64` — "GIP packets on a cable are at most
  64 bytes … GIP pads are **full-speed devices** (the 360's OHCI companion controllers,
  not EHCI like the wireless adapter); with two queued on one endpoint the console froze."
- `xbox360/xw_plugin.c:57-60`: `GIP_CLASS 0xFF / GIP_SUBCLASS 0x47 / GIP_PROTOCOL 0xD0`.
- `research/AUDIO.md:291`: "The GIP pad is full speed, so it must be on a root port (OHCI
  companion)."

These are the project's own operating instructions, written after AmpJack ran GIP pads on
real Xbox 360 hardware: the wired Xbox One scaffold only ever used the OHCI full-speed
companion controllers, never EHCI.

## 5. Transport model: GIP vs XUSB vs HID, and input report length

- **Xbox One/Series = GIP** (Microsoft's "Game Input Protocol", doc MS-GIPUSB): a
  vendor-specific USB interface (class/subclass/protocol FF/47/D0) carrying a small
  framed protocol over **interrupt IN/OUT** endpoints. There is no HID report descriptor;
  the device is not a generic HID gamepad.
- **Xbox 360 = XUSB/XInput over USB**: vendor interface with **bulk IN/OUT** endpoints and
  a distinct 20-byte report (used by AmpJack's wireless-dongle path `xbox360/xa_plugin.c`,
  `USBD_TYPE_BULK`). Not what the One pad speaks.
- **Generic HID**: unrelated third mode seids (`Xbox One` pads can be put in a GIP/HID
  toggle only in some third-party firmware); first-party pads are GIP only.

Input report length (VERIFIED, `core/gip.c:767-781` `handle_input`): the GIP gamepad
payload is 14 bytes — `buttons u16`, `trigger_left u16`, `trigger_right u16` (each 0–1023),
then `stick_left_x/y` and `stick_right_x/y` as s16 (up = positive). With the GIP header
(command/options/sequence + length framing) the total packet is ≤ ~20 bytes, comfortably
inside the 64-byte full-speed interrupt maximum. Compare the OG XID pad's own input
report, also 20 bytes (`bMaxInputReportSize 0x14`, xboxdevwiki). The modern pad moves
*no more* input data per report than the pad the console was designed for; bandwidth at
12 Mbps is a non-issue.

Full-speed legality of every endpoint type the pad uses:

| Endpoint | Pad value | Full-speed limit | Verdict |
|---|---|---|---|
| interrupt IN/OUT (data) | 64 B, bInterval 4 (→ 4 ms at FS) | 1–64 B; interval 1–255 ms | legal |
| isochronous IN/OUT (headset) | 228 B, bInterval 1 | 1–1023 B | legal |
| bulk IN/OUT (chatpad) | 64 B | 8/16/32/64 B | legal |

## 6. OG pad topology vs modern composite GIP — does the missing hub matter?

- OG Xbox controller = **XID device that is itself a USB hub** for its two memory-unit
  slots and the Communicator; the logical gamepad is a downstream function behind that
  internal hub. Hardware: Atmel **AT43USB401** (Duke, boards 23-0819B/C), later
  **AT43USB355/353M** (Controller-S) — Atmel full-speed USB hub+MCU parts
  [REF: xboxdevwiki.net/Xbox_Input_Devices, oldid=7426].
- Xbox One pad = **composite device** (GIP data + audio + chatpad interfaces) with **no
  hub**. Two of its three functions (audio interface 1, chatpad interface 2) are
  out of scope for this milestone.

**Does the absence of a hub matter to INPUT enumeration? No.** The hub on the OG pad
exists solely to fan out expansion accessories; the gamepad function is reachable by
ordinary USB addressing whether or not it sits behind a hub. The OG console addresses
devices by standard enumeration — it does not require a hub to find a device on a root
port. The real mismatch is **XID vs GIP class**, i.e. software, not the hub.

INFERENCE (flagging clearly): the only scenario where the OG hub could matter is if the
console's USB/XID driver hard-assumes "the gamepad device lives on the hub's downstream
ports 3/4" rather than "any XID-class device on any port". That is worker 02's binding
territory; from the USB-protocol side there is no hub prerequisite.

## 7. Honest UNKNOWNs (hardware facts with no evidence present)

1. **No pad was present at dispatch** (`lsusb` at boot showed only an Intel BT radio
   `8087:0aa7`). All first-party descriptor bytes above are labelled REFERENCE
   (third-party/user-submitted captures + xone/xpad/in-repo source). The only capture I
   executed locally is the host root hubs (§10). Nothing here is a claim that *this*
   host enumerated a controller.
2. **Port power**: the pad's descriptor requests `bMaxPower = 500 mA`. The OG Xbox front
   ports power its own pads; whether a given console/port reliably sources 500 mA to a
   modern pad is UNKNOWN and needs a real measurement (pad draw in practice is far below
   the requested maximum, but this is not measured). OHCI full-speed has no suspend/
   remote-wakeup quirk at play here.
3. **Exact physical model presence** is not established (owner owns hardware but no model
   was identified). Per-model speed gates are uniform anyway (all full-speed), so this is
   a minor unknown for this report.

## 8. "Xbox One pad on OG Xbox without an active converter" — what actually exists

- **External adapters (active, not our goal)**: OGX-Mini / ogx360 and forks run a USB
  *host* on an RP2040/RP2350/AVR, parse GIP, and re-emit an OG XID device to the console
  [REF: github.com/wiredopposite/OGX-Mini]. These exist **because the console has no GIP
  class driver**, i.e. to bridge the software gap at the wire with an MCU. The user
  explicitly wants a passive cable + console-side software instead.
- **Passive cable + shipped software**: NO documented case of a first-party Xbox One pad
  driving an OG Xbox controls a game. The OG Xbox BIOS/dashboard/titles speak only XID;
  there is no GIP binding in any stock title, so a passive cable alone connects the pad at
  USB level but nothing reads it. This is the exact gap AmpJack-OG fills (as AmpJack did
  for the 360, linking a GIP class driver into Usbd's list — `xbox360/xw_plugin.c`).

**Contradiction resolved**: "pad works on OG Xbox" statements in the homebrew scene all
trace to an active MCU translator. The *passive* question decomposes cleanly — (a) USB
enumeration: full-speed, works; (b) input function: needs the GIP driver + XInput/XID
presentation that this project is building. No evidence contradicts (a) for any model.

## 9. What USB host facilities a title actually initializes (scoped note)

This is worker 02's core deliverable; here only the USB-level fact: OG Xbox titles use the
kernel's OHCI/XID path via `XInput*`/XID control+interrupt traffic. Halo 2 u803's
title-linked `XInputOpen`/`XInputGetState` (0x413A12 / 0x413C4C per the brief — old clues,
re-verify against the pinned XBE; worker 03 owns that) sits above XID, which itself sits
above OHCI. The new GIP input must be presented to that chain as a valid XID/XInput device
— not as raw GIP — which is precisely the driver/shim boundary, not a USB-speed issue.

## 10. Local deliverable: read-only descriptor-capture helper

`ogxbox/research/usb/usb_descriptor_probe.py` — pure stdlib Python, **read-only**, zero
privileges, zero mutation. It reads `/sys/bus/usb/devices/*/descriptors` (kernel ≥ 4.5
binary descriptor blob) and `…/speed` (negotiated link speed), parses device/config/
interface/endpoint descriptors directly from bytes (so it prints real `wMaxPacketSize`,
`bmAttributes` transfer type, `bInterval`), and optionally falls back to a read-only
`lsusb -v`. It flags any interface with class FF/47/D0 as a GIP pad.

Exercise performed **on this host's root hubs only** (no pad present, as instructed):

```
$ python3 ogxbox/research/usb/usb_descriptor_probe.py
Device 1-7      8087:0aa7  bus speed=12 Mbps (full)      # Intel BT radio: correctly full-speed
  EP 0x81 IN interrupt wMaxPacketSize=64 bInterval=1 …
Device usb1..6  1d6b:0002/0003 xHCI Host Controller, speed=480/10000 Mbps
$ python3 ogxbox/research/usb/usb_descriptor_probe.py --vid 045e
(empty — correct: no Microsoft device attached)
```

Saved output: `ogxbox/research/usb/descriptor-captures/host-root-hubs-2026-11-23.txt`.
**This scope exercise validates the tool's parsing against the host's own root hubs and
the one real full-speed device attached; it is NOT a claim that a controller enumerated.**
When the owner plugs in a pad, this same script prints its real speed and endpoint
descriptors — the definitive proof this report could not (and is honest not to) claim yet.

## 11. Citations

VERIFIED (source bytes / local execution):
- AmpJack-OG @ `b83cf65`: `xbox360/xw_priv.h:26-29`; `xbox360/xw_plugin.c:5-7,57-60`;
  `core/gip.c:767-781`; `research/AUDIO.md:291`.
- Linux `xpad.c` (local copy; upstream `linux/drivers/input/joystick/xpad.c`):
  `:40` `XPAD_PKT_LEN 64`; `:127-134` device table.
- xone `transport/wired.c` (local copy): `:12-29` interface/class, `:19`
  `XONE_WIRED_LEN_DATA_PKT 64`, `:139-152` interrupt IN URB, `:545-570` id table.
- Local probe run (this host, root hubs) — output in §10.

REFERENCE (cited third-party/user-submitted captures, labelled, not captured by me):
- github.com/univrsal/input-overlay/issues/183 (`lsusb -v` for 045e:02d1).
- github.com/linuxhw/LsUSB file `…/E0687D11BB` (045e:02d1; third-party BOS).
- forums.opensuse.org/t/152435 (045e:02e3 Elite descriptor).
- github.com/wiredopposite/OGX-Mini (active RP2040 XID-emulation adapter).
- xboxdevwiki.net/USB ("two OHCI USB Host controllers within the MCPX … up to USB1.1
  12 Mbit/s"; retail USB0 = 4 front controller ports).
- xboxdevwiki.net/Xbox_Input_Devices?oldid=7426 (XID = hub for MU/communicator; AT43USB401/
  355/353 parts; XID input report 20 B).

## 12. Bottom line for the integrator

USB-level feasibility is solved: **a wired Xbox One/Series pad enumerates full-speed on the
OG Xbox's OHCI hosts** (native full-speed device, 64-B interrupt IN/OUT, all endpoint types
within full-speed limits). The milestone's remaining work is not USB physics — it is the
GIP class driver binding (worker 02) and the GIP→XID/XInput presentation + Halo 2 hook
(workers 03/04). Next smallest physical test: owner runs the probe helper with one real
pad on a USB 1.1 (or full-speed) port and records `speed=12` + the endpoint rows; that
confirms the descriptors on *his* hardware and converts the UNKNOWNs in §7 to VERIFIED.
