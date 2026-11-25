# AmpJack GIP Driver Probe — plain-English instructions

This is a **transport proof**, not a finished adapter. It is an original-Xbox
program (XBE) that runs the *same USB code the title links*, registers its own
driver for the Xbox One controller's GIP interface (class `0xFF81`, which the
stock table does not match), opens the controller's interrupt IN/OUT endpoints,
submits interrupt reads continuously, and writes a log of the raw packets plus
decoded gamepad state. On success it proves the hardest remaining step — that a
title-local class driver can actually claim the pad and see its bytes.

It does NOT flash anything, does not change your BIOS, and does not make the
controller playable yet. A stock controller still works while it runs.

## The steps

1. Copy `bin/default.xbe` to the Xbox at `E:\AmpJack-OG\default.xbe`.
2. Launch it from XBMC / your dashboard (it is a normal homebrew XBE).
3. Keep one stock controller in port 1. Plug the Xbox One controller into any
   free port with a passive USB cable. If it does not stream, press its Xbox
   button once — the program logs `WAITING pad` every 5 s until bytes arrive.
4. Nothing else to press: it exits to the dashboard by itself after 60 s
   (BACK + START on the stock pad exits sooner, if you want).
5. FTP back `E:\AmpJack-OG\gip-probe.log` (fallback `D:\gip-probe.log`) and read it.

## What the log lines mean

- `SYNTH log=E ok|fail D ok|fail` — which log path opened, written first.
- `GIPINIT pin=0x.. armed=.. armcode=.. fc_va=.. begin=.. end=.. wr=.. bytes=..`
  — the self-check. `armed=1` means it confirmed its own FindClassDriver code
  byte-for-byte (shape + class-table begin immediate + writable XPP section)
  and patched it. The line now also prints the first 16 bytes actually read at
  `fc_va` plus the live begin/end immediates, so a `PINFAIL` tells you exactly
  which check disagreed.
- `GIP_ATTACH dev=0x..` — OUR driver was selected for the 0xFF81 device and its
  Attach ran. This alone proves registration works. Attach then drives the
  rest from completions (stage-2 rewrite, worker14).
- `OPENCTRL hnd=0x..` — the default control pipe opened (fn 0x82), the first
  step of the enumeration our Attach must do itself for a 0xFF81 device.
- `CFG iface=0 ep_in=0x81 ep_out=0x01 mps_in=64 mps_out=64 int_in=4 int_out=4
  cfgval=1` — the config descriptor was fetched and parsed; the GIP interface
  and its interrupt IN/OUT were found (values are read from the descriptor,
  not hardcoded). The line is built from a structured ring event at drain time,
  so no field can be cut off (worker15 truncation fix).
- `OPEN in=0x.. out=0x.. in_hnd=.. out_hnd=.. out_flags=1,0,0` — the interrupt
  IN/OUT endpoint opens and their handles. `out_flags` are the OUT transfer
  FlagB0/FlagB1/Direction bytes (1,0,0 — copied from the stock XID output URB,
  verified against `XID_fSendDeviceReport` in xapilib; the IN URB uses 2,1,0).
- `CFGFAIL no_ff_iface` — no 0xFF interface in the descriptor; the driver stops
  (device stays claimed-idle, no crash).
- `STEPFAIL step=N status=0x..` — a config/open/control step failed; the run
  draws red and waits for auto-exit.
- `RX seq=N status=0x.. req=R id=I n=L .. ..` — one interrupt-IN completion.
  `status` is the TRUE URB header status (+0x04). `req` is the requested size
  (endpoint max-packet), `id` the request id, and `n`/`L` is the ACTUAL number
  of bytes the HCD accumulated into +0x14 at completion (a 0-byte completion
  stays 0, never forced to 64; a negative status publishes no RX at all). Raw
  RX hex is printed for the first 32 frames only (input can arrive ~125/s);
  every RX is still parsed for GIP state.
- `TXDONE seq=N status=0x.. req=R id=I len=L cmd=0x..` — an interrupt-OUT
  completion: `status` is the TRUE header status (+0x04), `req` the requested
  frame length, `len`/`L` the actual completed bytes, `cmd` the command byte of
  the frame just sent to the pad.
- `LIVE in_flight=0/1 tx_q=N rx=N tx=N inf=N outf=N` — `in_flight=1` means an
  IN request is actually pending (set only after a successful SubmitRequest
  return; an immediate rejection leaves it 0). `inf`/`outf` count immediate
  IN/OUT submit rejections.
- `STATE buttons=.. lx=.. ly=.. rx=.. ry=.. lt=.. rt=.. A=.. B=.. X=.. Y=..
  Black=.. White=..` — a decoded GIP input frame, written directly (never
  truncated to the 64-byte packet buffer), covering every face/bumper analog
  byte, both triggers and all four sticks.
- `IDENTIFY seq=N 04 20 ss 00` — the driver queued an identify request to the
  pad (on announce, or as the wired-start fallback).
- `ACK seq=N 01 20 ss 09 ..` — the driver queued an acknowledgment for a pad
  frame that set the needs-ack bit (options & 0x10).
- `buttons=0x0010 lx=.. ly=.. rx=.. ry=.. lt=.. rt=..` — a decoded GIP input
  frame, printed only when the state changes. `buttons` uses the original Xbox
  bit layout; `lt`/`rt` are 0..255 triggers.
- `WAITING pad` — no packets seen yet; press the pad's Xbox button.
- `LIVE in_flight=0/1 tx_q=N rx=N tx=N` — printed every 1 s. `in_flight=1`
  means the interrupt-IN URB is currently pending (the pipe is armed);
  `in_flight` dropping to 0 with no further `rx` growth is the visible signature
  of the IN pipe stalling. `tx_q` is the depth of the OUT frame queue, `rx`/`tx`
  are the IN/OUT completion counters.
- `HEARTBEAT t=Ns` — printed every 30 s as a backstop so a hung run still shows
  how far it got.
- `GIPEXIT auto` — the 60 s auto-exit fired and it returned to the dashboard.

## The handshake (worker17)

Once the IN/OUT endpoints are open (S5), the no-announce wired path starts the
pad with the MINIMAL first-party sequence, serialized on actual completions:

1. the interrupt-IN URB is already armed at the endpoint max-packet (64 B);
2. power-on (`05 20 ss 01 00`) is sent once, as the only first frame;
3. after power-on's OUT completion is observed (successful status), S-init
   (`05 20 ss 0f 06 .. 55 53`) is sent exactly once — it forces a previously
   Bluetooth-paired pad back into USB mode.

No blind IDENTIFY before power, no LED, no rumble (those are out of scope for
this slice). The decoder's `gamepad` path is qualified from the fetched config
descriptor (0xFF/47/D0 interface with an interrupt IN+OUT pair) rather than by
an announce/identify transaction, so a following `20 00` input frame decodes
directly. The announce->identify path (full power/S-init/LED/rumble) is retained
only for pads that do announce; a pad frame with the needs-ack bit (options &
0x10) is still ACKed.

Every OUT frame goes through a single queue (`TXDONE` sends the next queued
frame). The OUT URB's TransferLength is always the exact frame length — never
the endpoint max-packet and never shared with the IN buffer — and its
FlagB0/FlagB1/Direction are the XID output values `1,0,0` (not the IN URB's
`2,1,0`). Each interrupt-IN completion snapshots the actual completed length
from +0x14 BEFORE resetting it back to the endpoint max-packet for the next
request, so the IN pipe keeps streaming at 64 B.

URB field correction (worker17, from the linked-XBE disassembly): the true
completion status is Hdr.Status (+0x04); the actual completed/accumulated byte
length is TransferLength (+0x14) at completion; +0x20 holds the original mapped
length (NOT a received byte count) and +0x24 is HCD linkage (NOT a status).
The previous code read +0x20 as the byte count and +0x24 as status, which is
why a short 8-byte status frame was logged as n=64 with status 0.

## On-screen colour

- **yellow** — armed, waiting for the device to enumerate.
- **cyan** — Attach fired (S0 ran), no decoded input yet.
- **green** — decoded GIP input frames seen (the full chain worked).
- **red** — the self-check refused to arm (`PINFAIL`) or an attach step failed
  (`STEPFAIL`) / the config had no GIP interface (`CFGFAIL`).

## Success vs failure

- **Success** looks like: `armed=1`, a `GIP_ATTACH`, then an `OPENCTRL`, a `CFG`
  line and a non-zero `in_hnd`/`out_hnd` in `OPEN`, then several `PACKET` lines
  and eventually `buttons=...` state lines.
- **Partial** (still useful): `armed=1` + `GIP_ATTACH` but a `STEPFAIL` / `CFGFAIL`
  or no `PACKET` lines — registration and the control/config chain got far
  enough to tell us exactly which step failed.

## What this does NOT promise

No playable input. This is stage 2 transport proof. The endpoint *numbers* are
now read from the fetched config descriptor rather than hardcoded (so 0x81/0x01
are confirmed by the pad itself in the `CFG` line); the still-unverified parts
are the OUT transfer flag/direction bytes and the control-pipe handle placement
— those resolve the first time a real pad enumerates.
