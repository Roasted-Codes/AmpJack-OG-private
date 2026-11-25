# Worker 06 — Alternatives survey, claim verification, risk register, test protocol

Scope-owner: ogxbox/research/alternatives/ and ogxbox/work/06-alternatives/.
Dates: 2026-11-23 (UTC-05:00). Method: source bytes read locally, immutable URLs/web
fetched, host commands executed. Labels used: VERIFIED (observed source bytes or real
execution), INFERENCE (interpretation), UNKNOWN (missing hardware fact).

No hardware was connected, no driver installed, no emulator launched. No claim below
asserts that a pad enumerated on a real Xbox.

---

## 0. Executive summary

Three prior claims were tested and two corrected:

1. "all GIP high speed" — FALSE. Microsoft's own MS-GIPUSB specification mandates the GIP
   **data** interface be a **Full-Speed (12 Mbps)** device, with 64-byte interrupt IN/OUT
   endpoints and bInterval >= 4 ms (§2). The INPUT-only milestone therefore needs no
   high-speed host: the OG Xbox's OHCI (USB 1.1, ~12 Mbps) meets every requirement of the
   GIP input transport.
2. "no kernel USB" — TRUE, precisely as "no kernel USB/XInput **API**". XInput and the
   OHCI/USBD stack are XDK library code statically linked into each title's XPP section and
   drive OHCI MMIO at 0xFED00000 directly; no kernel ordinal exports USB (§3).
3. "no OG plugin/driver analogue" — PARTLY TRUE / misleading. There is no kernel plugin
   loader (no DashLaunch/launch.ini analogue), but there **is** a linkable USB class-driver
   framework (XInitDevices + a class/subclass-matched driver table) inside XAPILIB — the
   exact analogue of the 360 class-driver route AmpJack (xw.xex) uses. The difference is
   *where* it runs: per-title XPP (injected via an XBMC trainer) rather than a persistent
   kernel driver (§4).

Net: input transport is full-speed and the OG has a class-driver framework, so the
milestone is not blocked by "GIP is high-speed" or "no driver mechanism". What remains
UNKNOWN is hardware-only: whether Roasted's specific pad, once present, enumerates at
full speed on a real OHCI, and whether a title's USBD accepts a *non-hub* composite GIP
device (the OG pad is a hub; a modern pad is not).

---

## 1. Landscape (existing projects)

| Project | What it is | Category | Xbox One wired input? | Citation (VERIFIED) |
|---|---|---|---|---|
| AmpJack xw.xex (upstream) | 360 kernel plugin; GIP class driver `FF/47/D0` via kernel USB driver list | system USB class registration (360) | yes (input) | local `docs/WIRED.md`, `core/gip.c` @ b83cf65 |
| ogx360 / ogx360_t4 (Ryzee119) | Pro Micro / Teensy4.1, emulates a Duke/Controller-S XID per port | external active translator | yes ("Genuine and PDP Wired Xbox One Controllers") | github.com/Ryzee119/ogx360 README |
| OGX-Mini (wiredopposite) | RP2040/RP2350 firmware, emulates OG controller / XInput / PS3 etc. | external active translator | yes (360/One/Series/Elite wired) | github.com/wiredopposite/OGX-Mini README |
| nxdk + libusbohci + xid_driver | homebrew SDK; user-space OHCI stack + XID driver (OpenXDK-derived) | per-title homebrew (userspace OHCI) | no GIP driver shipped; only XID | github.com/XboxDev/nxdk `lib/usb/libusbohci_xbox/xid_driver.c` |
| Cerbios BIOS | custom BIOS (modchip/TSOP). Official feature list has **no** USB-controller entry | BIOS (dash context only) | no (games use title XInput) | github.com/Cerbios/Cerbios-Xbox README v2.4.2 |
| xone / xpad (Linux) | Linux kernel drivers for GIP / XInput pads | Linux-on-Xbox (not native games) | yes (works on a Linux PC) | dlundqvist/xone; linux `drivers/input/joystick/xpad.c` |
| XBMC XBTF/ETM trainer | ring-0 title-patch loader, runs before title entry | per-title injection (the OG "plugin" substitute) | n/a (mechanism) | local `LAN_Stats/references/xbmc-trainer-format.md` (VERIFIED) |
| Darkone83 Xbox camera driver | documented OG USB class-driver **attach contract** in XAPILIB | per-title USB class driver (precedent) | n/a (mechanism) | github.com/Darkone83/Xbox-live-camera-research-project `RESEARCH.md` |
| xboxrecomp | static recompile; documents XInput-as-title-library and OHCI@0xFED00000 | reference (architecture) | n/a | github.com/Heromachine/xboxrecomp `src/input/README.md` |

Key distinction the user asked for:

- **External translators** (ogx360, OGX-Mini, Brooks/8bitdo): each presents itself to the
  console as a *genuine Xbox Input Device (XID)* — a Duke or Controller-S. They work today
  and are the only current projects that let a wired Xbox One pad control OG Xbox games
  *without touching the game*. They require active external hardware — explicitly what the
  user wants to avoid as the primary design. Relevant as a *fallback* and as a *test oracle*.
- **System USB class registration**: on OG this does NOT exist in the kernel (unlike the 360,
  where xw.xex registers into the kernel's persistent USB driver list). Registration on OG is
  per-title, at boot, via XInitDevices.
- **Per-title patching**: the only way to run new OG code against a retail game without a
  BIOS flash. Mechanism: an XBMC/Evox trainer (XBTF) hooks the kernel's call through XBE
  header +0x128, runs ring-0 code before the title's entry point, title-ID gated
  (VERIFIED, `xbmc-trainer-format.md`). This is where an injected GIP class driver would live.
- **Linux-on-Xbox**: xbox-linux + xpad/xone make an Xbox One pad work, but that's Linux, not
  native Halo 2. Not the milestone.

---

## 2. "all GIP high speed" is FALSE (input is full-speed)

VERIFIED citations:

- MS-GIPUSB "GIP Data Interrupt IN Endpoint Descriptor" (Table 11, §2.2.9.1.2):
  wMaxPacketSize = 0x0040 (64 bytes); field notes state bits D12..11 "MUST be zero for
  Full Speed devices"; bInterval "MUST be >= 4" (ms).
  https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-gipusb/e77f6af7-481d-4d86-b72a-848cb233e3d6
- MS-GIPUSB PDF: "USB GIP devices MUST respond to a request for the device_qualifier
  descriptor with a request error (STALL) to indicate that this is a Full-Speed (12 Mbps)
  device and not a High-Speed (480 Mbps) device …". Data Interface (interface #0) = one
  64-byte interrupt IN + one 64-byte interrupt OUT, class/subclass/protocol FF/47/D0.
  https://winprotocoldoc.z19.web.core.windows.net/MS-GIPUSB/%5BMS-GIPUSB%5D.pdf
- AmpJack's own transport is 64-byte interrupt, matching this exactly: `desktop/xwired.c:30`
  `#define PKT_LEN 64`, `:575` rejects non-interrupt endpoints, and `core/gip.c:22`
  `#define GIP_PKT_MAX_LENGTH 58` (fits a 64-byte full-speed interrupt transfer).
  (upstream commit b83cf6546e7d04c6013571d4641cb3e482b05e94).

INFERENCE (gap stated): the controller's *audio* interface (interface #1, isochronous, in
`core/gip.h:85`) is the only GIP feature that could near high-speed bandwidth, and it is
out of scope for input-only. The headset-in-jack exists on some pads and its audio path may
or may not enumerate at full speed — UNKNOWN, deferred.

Supporting empirical (INFERENCE, not reproduced here): ogx360_t4 and OGX-Mini read wired
Xbox One pads through full-speed-only host paths (MAX3421E "Full-/Low-Speed Host"
per Analog Devices datasheet; RP2040 Pico-PIO-USB is full-speed). Those projects listing
Xbox One/Series/Elite as wired input implies those pads enumerate full-speed in practice.

Where the confusion originates: a pad's device descriptor reports `bcdUSB == 2.00`, which
says "USB 2.0 feature set", NOT "480 Mbps". A full-speed device may validly report 2.00.
Real host evidence (this session, VERIFIED by executing `gip_fullspeed_check.py`): the host's
Intel BT (`8087:0aa7`) sits at speed=12 Mbps while its `version` = 2.00 — a bcdUSB-2.00
device at full speed. OHCI therefore sees any device that negotiates 12 Mbps regardless of
bcdUSB.

---

## 3. "no kernel USB" is TRUE (no kernel USB/XInput API)

VERIFIED citations:

- xboxrecomp `src/input/README.md`: "On the Xbox, XInputGetState and its siblings are not
  kernel exports. They are XDK library code linked into the title's XPP section, and they
  drive the USB host controller …". Its `src/main.c`: XAPI "reaches the controller by
  programming the MCPX's USB OHCI registers itself (look for 0xFED00000) … nothing in that
  path goes through a kernel export". (github.com/Heromachine/xboxrecomp)
- Darkone83 `RESEARCH.md` §4 layering (confirmed by decomp + FID symbol mining of
  retail `xapilib.lib`): App → XInitDevices/IUsbInit → IUsbDevice → USBD_* (enumeration +
  class-driver match) → HCD_*/OHCD_* → OHCI @ 0xFED00000; all linkable in
  `xapilib.lib`/`usbd.lib`/`ohcd.lib`/`usbhub.lib`.
- xboxdevwiki `USB`: two OHCI controllers in the MCPX; USB0 = the four front ports;
  "OHCI supports USB devices up to USB1.1 12Mbit/s"; USB1 not enabled in retail titles.
  https://xboxdevwiki.net/USB (oldid 7298)

Conclusion: the kernel has no general-purpose USB/OHCI/XInput export surface. Every title
brings its own USB stack. nxdk homebrew therefore ships its own OHCI driver
(libusbohci, "hacked together parts of an old Linux OHCI stack", XboxDev/nxdk README).

INFERENCE: the kernel/boot still recognizes XID gamepads for the OS/dashboard, but this is a
private kernel XID implementation, not an API titles can extend — it does not contradict
"no kernel USB API".

---

## 4. "no OG plugin/driver analogue" — corrected

TRUE part: OG Xbox has no kernel plugin loader. There is no DashLaunch, no `launch.ini`,
no runtime way to install a persistent kernel driver the way xw.xex loads on 360
(VERIFIED locally: 360 path is kernel 17559 + plugin slot; `docs/WIRED.md`). OG homebrew
runs as XBEs, and injection into a retail title is the XBMC trainer path (§1).

Corrected part — there IS a driver analogue. Darkone83 §5 (CONFIRMED from XInitDevices /
USBD_* decomp): a USB class driver is one entry in a table matched **by class/subclass
value**:
```
[0]=class, [1]=subclass, [+4]=Register fn, [+8]=Attach fn   // table @ 0x1b2774..0x1b2790
```
Boot: `XInitDevices → IUsbInit() → Register(entry) → Process() → HCD_EnumHardware()`.
Connect: `USBD_DeviceEnumStage0→…→6 → USBD_LoadClassDriver → USBD_FindClassDriver(match)
→ (*(+8))(IUsbDevice*)`; no match → status 0x80000400.

This is structurally identical to what AmpJack does on 360 with `XwMatchC` accepting
interface `FF/47/D0` (`docs/WIRED.md`): both register a class-subclass matched driver that
gets an AddDevice/Attach on a matching interface. A GIP class driver on OG would register
`{0xFF, 0x47, Register, Attach}` in the title's table.

Caveat (from the same research log's later correction): first-party camera code ultimately
bypassed the class-driver attach and claimed its device manually off the device tree — so
the framework exists and is linkable, but *whether Halo 2's own XInput enumerates GIP as a
new class* is a per-title integration question owned by workers 02/03, not proven here.

Difference that matters for the inject route: on 360 the driver is kernel-resident and
survives title switches; on OG a GIP class driver injected by XBTF has title-change
lifetime (re-run per launch, buffer persisted — see trainer contract §2.1 of
`xbmc-trainer-format.md`).

---

## 5. Per-model full-speed gate

All rows are INFERENCE-from-spec unless the descriptor has been directly captured, which it
has not (no pad at dispatch). "Full-speed input" = the GIP data interface conforms to
§2. The actual enumeration of a specific unit is UNKNOWN until measured.

| Model | GIP data (input) full-speed? | Audio interface (out of scope) | Gate for THIS milestone |
|---|---|---|---|
| Xbox One (2013, 0x02D1) | yes per MS-GIPUSB | isochronous; UNKNOWN if it forces HS | pass pending a real descriptor capture |
| Xbox One (2015, 3.5mm) | yes per MS-GIPUSB | UNKNOWN | pass pending capture |
| One S / One X (Bluetooth) | yes per MS-GIPUSB | UNKNOWN | pass pending capture |
| Elite / Elite 2 | yes per MS-GIPUSB | UNKNOWN | pass pending capture |
| Series (0x0B12) — AmpJack-verified on 360 | yes per MS-GIPUSB | UNKNOWN | pass pending capture |

Decisive gate (must be measured on the real console): does the specific pad enumerate and
stream input reports over a full-speed OHCI? Nothing in this report can close that without
hardware.

---

## 6. Risk register

| # | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| R1 | Specific pad won't enumerate at full speed (draws high-speed-only in practice) | Low (spec says FS) | Milestone blocked | Passive-cable descriptor capture on the real console (test T1) before any code |
| R2 | Title's USBD rejects a non-hub composite device (OG pad is a hub; modern pad isn't) | Medium | Input not seen by game | Verify on real OHCI; if blocked, emulate a minimal hub topology in the GIP driver's Attach (worker 02) |
| R3 | No kernel-resident driver ⇒ trainer must re-run and re-enumerate per title launch | High | Reconnect latency / state loss each launch | XBTF trainer persists buffer; re-entrant GIP start (gip_adopt/announce already in `core/gip.c`); boot-plugged pad must be re-offered |
| R4 | 64 MB RAM budget | Medium | Crash if driver/trainer too large | Worker 04's bounded memory; worker 05's object-map sizing (not guessed) |
| R5 | XID→GIP input mapping drops analog face buttons (A/B/X/Y pressure on OG) | Low | Minor fidelity loss | Map to the 8 analog-button byte array with full-scale 0xFF (worker 03) |
| R6 | Halo 2 title's XInput differs from generic XAPILIB; hook alone insufficient without a valid controller handle | High | GetState hook sees no device | Worker 03 must present a valid XInputOpen handle + poll path, not just GetState |
| R7 | Guide/menu vs Black/White (bumpers) mapping ambiguity | Low | Cosmetic | Map bumpers→Black/White; guide→Start long-press (chosen in worker 03) |
| R8 | Passive Xbox↔USB cable provides no 5V routing differences (VCC on pin 1) | Low | Pad unpowered | Standard passive cable carries VCC/D+/D-/GND (xboxdevwiki Xbox Input Devices wiring) |

---

## 7. Staged test protocol (real 64 MB Xbox)

Stages ordered so each is a cheap, decisive gate before spending effort on the next.

- **T0 (host, now):** capture the pad's descriptor with `lsusb -v` / worker 01's helper when
  the owner plugs it into a PC. Confirm GIP data interface = Full-Speed (12 Mbps), 64-byte
  interrupt IN/OUT, bInterval >= 4 ms. THIS closes R1 and is the single highest-value
  measurement. Must show `Device current bus speed: FullSpeed` for the specific PID.
- **T1 (real console, no code, passive cable):** plug the pad into a controller port through
  the passive adapter while the console boots a *diagnostic* XBE (e.g. an nxdk sample using
  libusbohci) that prints every connected device's descriptor + speed and any `FF/47/D0`
  interface. Answers: does the pad enumerate on real OHCI, and does the device tree show its
  interfaces. No permanent change — a diagnostic XBE run from a dashboard.
- **T2 (real console, injected driver, disabled-by-default):** load the GIP class driver via
  an XBTF trainer gated to Halo 2's title ID, matching `{0xFF,0x47,...}`; log Attach +
  a completed interrupt IN. Answers R2/R3. Still no game integration.
- **T3 (integration):** feed the parsed GIP state into the title's XInput snapshot
  (worker 03's shim); verify A/B/X/Y/Bumpers/triggers/sticks/Start/Back in-game. This is the
  milestone acceptance test.
- **T4 (post-milestone):** rumble (XInputSetState → GIP CMD_RUMBLE). Audio/wireless NOT here.

Minimal decisive acceptance: a wired Xbox One pad directly on the console (passive cable only,
no MCU) moves the Halo 2 menu/cursor and plays in-game with correct buttons. Anything short
of that is a partial, reported as such.

---

## 8. What xemu can and cannot prove

VERIFIED (xemu.app/docs/controller/): "USB passthru is not supported yet". xemu maps host
SDL gamepads/keyboard onto **emulated** Xbox controllers; it does not expose a host USB
device to the guest OHCI. (XQEMU, the predecessor, had `-device usb-host` passthru — but it
forwarded an XID hub/gamepad, and it is not the emulator in use.)

- xemu CAN prove: the title-side software path (GetState hook, GIP decode, XID state
  mapping) end to end, by feeding worker 03/04's shim a synthetic controller snapshot and
  running Halo 2 — validates the shim, not the USB transport.
- xemu CANNOT prove: that a real Xbox One pad enumerates at 12 Mbps on a real OHCI; that a
  non-hub GIP device is accepted by a title's USBD; any descriptor/timing behaviour of the
  real hardware. These need a 64 MB console (T0/T1).
- OHCI vs UHCI: the Xbox has OHCI (not UHCI), both host controllers in the MCPX; xemu
  emulates the guest OHCI MMIO (0xFED00000), so no UHCI instrumentation is relevant.

---

## 9. Deliverables and real outputs

Files (all under the owned folders):
- `ogxbox/research/alternatives/REPORT.md` — this document.
- `ogxbox/work/06-alternatives/gip_fullspeed_check.py` — host-only, read-only checker.
- `ogxbox/work/06-alternatives/gip_fullspeed_check.run.log` — captured real output.
- `ogxbox/work/06-alternatives/status.json` — machine-readable status.

Commands with real outputs:

1. `python3 gip_fullspeed_check.py` (run; log saved): live sysfs scan showed the host's
   BT device `8087:0aa7` at `speed=12` with `version 2.00` — a bcdUSB-2.00 device at full
   speed — and no `045e`/`2e95` device (consistent with "no pad at dispatch"). Synthetic
   GIP fixtures: conforming full-speed pad = CONFORMING; high-speed pad = NON-CONFORMING
   (fails the FS rule); 32-byte endpoint + 2 ms interval = NON-CONFORMING.
2. `sha256sum …/halo2-tu15-u803/default.xbe` =
   `21b207e7efdacaf6124a0822837f8be570766a42505057f7fd2d2ba8f409c4fd` — confirms the exact
   XBE the parent's XInput address clues (XInputOpen 0x413A12 / XInputGetState 0x413C4C)
   refer to; those FUNCTION addresses still need worker 03's exact-XBE verification (not
   verified here).
3. `git status` (repo root): clean except the untracked `ogxbox/`; upstream at b83cf65.

---

## 10. Completed vs unverified, next smallest test

Completed (this worker): independent survey; three claims verified/corrected with citations;
external-translator vs registration vs per-title vs Linux-on-Xbox distinction; per-model
full-speed gate; risk register; staged protocol; xemu scope; running host-only checker.

Unverified / not done: any real-hardware measurement (no pad, no console access this run);
no driver or game-shim code (owned by workers 02/03/04); no audio/other-game plans (out of
scope).

Next smallest test: plug the owner's Xbox One pad into a PC and capture its descriptor
(`lsusb -v`), confirming Full-Speed + 64-byte interrupt IN/OUT + FF/47/D0. That single
read-only capture closes R1 and de-risks the entire downstream build.
