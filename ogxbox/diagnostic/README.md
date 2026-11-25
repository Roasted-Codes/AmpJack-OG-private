# AmpJack USB Probe — plain-English instructions

This is a **diagnostic**, not a fix, and not a driver. It is an original-Xbox
program (an XBE) that runs the *same USB code the title links* and writes a log
file telling us exactly what the Xbox sees when you plug an Xbox One controller
in. It captures the one number the next step needs: the console-computed
`PNP_CLASS_ID` (and the descriptors) of a GIP Xbox One pad.

It does NOT flash anything, does not change your BIOS, and does not claim any
device that is not supposed to be claimed. A stock Xbox controller still works
with it running. The capture is **fail-closed**: it arms only after the program
confirms, byte-for-byte, that it is patching the exact function it built, in a
memory section the XBE itself proves is writable. If anything is off, it logs
`PINFAIL` and changes nothing.

## What you need

1. An original Xbox (any softmodded console that can launch an XBE from E:).
2. Any FTP client (FileZilla is fine) and the Xbox's IP address.
3. One stock Xbox controller (keep it plugged in the whole time).
4. An Xbox One controller and a **passive USB cable** (a normal charge/play or
   data cable, NOT a hub, NOT a powered port, NOT an adapter box).

## The steps

**Step 1 — copy the file to the Xbox (FTP).**

Copy this one file: `bin/default.xbe`

Put it on the Xbox at:  `E:\AmpJack-OG\default.xbe`

(If the folder `AmpJack-OG` does not exist, make it first.)

**Step 2 — launch it.**

From your dashboard or XBMC file browser, browse to `E:\AmpJack-OG\default.xbe`
and launch it like any other homebrew XBE. It does not need to be "installed"
and is never a flash.

**Step 3 — wait for ARMED, then plug in the Xbox One controller.**

The program is armed from the moment it logs a `SYNTH ... armed=1 ...` line.
Keep the one stock controller in port 1. Then plug the Xbox One controller into
any free controller port (2–4) using the passive cable, and wait at least
10 seconds.

**Step 4 — exit.**

Hold **BACK + START** on the stock controller for about one second, *after the
program has detected it* (the screen turns cyan once the stock pad has been found). The
program returns to the dashboard by itself (no power cycle needed).

**Step 5 — read the result.**

FTP back to `E:\AmpJack-OG\usb-probe.log` and open it. A `D:\usb-probe.log` fallback beside the XBE is
only opened when the `E:` open fails (when launched from `E:\AmpJack-OG` both
names are the same file, so the log reports `D fail` — that is expected). The first line of the log
says which path opened: `SYNTH log=E ok|fail D ok|fail`.

## What the log lines mean

- `SYNTH log=E ok|fail D ok|fail` — written first; tells you which log path
  opened. `E` is mapped by the program itself (`IoCreateSymbolicLink`), `D` is
  the launch directory and needs no mapping.
- `SYNTH pin=0x0f armed=1 ...` — the self-check: it found and pinned its own USB
  code and armed the capture. `armed=0`/`armcode=...` or a `PINFAIL` line means
  it refused to arm (fail-closed) and the log will only contain self-checks.
- `MATCH ... class=0xXXXX ...` — the measurement. One line per class-driver load.
  `class` is the console-computed PNP_CLASS_ID: the **high** two hex digits are
  the USB interface class and the **low** two are the Xbox-specific match byte.
  For the stock pad that is `class=0x5882` (class 0x58 = XID). For the Xbox One
  pad's GIP interface (USB class 0xFF, subclass 0x47) you are looking for a
  `class=0xff..` line — the low byte is exactly the value that was unknown.
  `find=0x00000000` on that line means no stock driver matched (expected for
  GIP); `vendor`/`product` are the VID/PID if the device descriptor exposes them.
  The MATCH line has no `port=` field: the console does not fill the port until
  after the class-driver load, so the physical port is read from STOCKPAD instead.
- `STOCKPAD ...` — an insertion edge on the *stock* pad surface. `insertions=`
  is a bitmask where bit N is XID port N. It is a self-check only; a `STOCKPAD`
  line by itself does NOT measure a GIP device.

## An important note about testing in xemu

xemu's emulated XID pad will produce a `MATCH ... class=0x5882 ...` line. That
validates that the capture path fires and records, but it is NOT a GIP
measurement — 0x5882 is the stock controller class, not a GIP FF/47 device.

## On-screen colour

The program shows a solid colour so a black screen is never mistaken for a crash:

- **red**    — the self-check refused to arm (`PINFAIL`): the capture is not running.
- **yellow** — armed, nothing enumerated yet.
- **cyan**   — armed; only devices with a stock driver seen so far (hubs, stock pad).
- **green**  — a device with NO stock driver was captured (`find=0x00000000`) —
  this is what the Xbox One pad should produce; read the `class=` value from the log.
- **blink**  — BACK + START is being held to exit.

If the graphics device cannot be created (unlikely on a devkit), it simply stays
log-only with no display. The log file is still the deliverable; read it by FTP.

## What this does NOT promise

This does not make the Xbox One controller work in Halo 2 yet. It only measures
what the console reports about the device, so the next step has the real
PNP_CLASS_ID instead of a guess. No plug-and-play is promised.

## If anything goes wrong

The program writes `E:\AmpJack-OG\usb-probe.log` and `D:\usb-probe.log`. It never
touches system files. Worst case, delete the `E:\AmpJack-OG` folder and reboot —
the console is exactly as it was before.
