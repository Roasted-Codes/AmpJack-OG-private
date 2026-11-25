# W63 — wake fix, rumble, on-console log (status: COMPLETE, host-only)

New ELF 3ddc05b8… (layout 850368f8…). Baseline rebuilt from the self-contained copy reproduced 7bbfdafa… exactly.
Pair: release/candidate/AmpJack63-u803-3ddc05b8.{xbtf,bin} + SHA256SUMS + manifest.json; archive release/AmpJack63-u803-test.zip.
Trainer options: [0] Enable AmpJack63, [1] Write log E:\Trainers\AmpJack63.log. Both default off.

## What changed (full diff: changes.diff; list: RESULT.json)
- Wake (W1, gipdrive.h `gdr_rx_announce`): every ANNOUNCE is counted (`announces`) before the len check. If the pad
  was already qualified on the wired fallback path, a fresh power-on is queued (new sequence), with ready=1,
  s_init_pending=1 and `rehandshakes++`. S-init follows on that power-on's successful TXDONE (existing path).
  Snapshot kept; no timers. Announces before qualification keep the old identify behaviour.
- Alternative cause: counters only. attach calls, remove calls, and the "previous generation still quiescing" refusal
  (AddComplete 0xC0000001). These are plain increments in the callbacks.
- Rumble: virtual XInputSetState stores wLeft|wRight (offset 66), sets dwStatus=SUCCESS and returns 997 (IO_PENDING).
  hEvent is recorded, never signalled. Caps now report both motors as 0xFFFF. The pump sends ONE frame
  `09 00 seq 09 00 0F 00 00 L R FF 00 FF` (L/R = speed>>9) only when the GIP queue, the OUT queue and the in-flight OUT
  are all idle and no S-init is pending, so the latest value wins. On a generation change it re-sends a nonzero value.
- Log (ogx_log.c/h): turned on by entry flags bit0, which the loader sets from XBTF option [1]. Lines are built in a
  2 KiB BSS buffer, on the title thread only. The file opens lazily in the pump at IRQL 0 (NtCreateFile through slot
  0x41b660, FILE_OVERWRITE_IF). Each write is followed by a flush, at an explicit offset, every >=1 s or when the
  buffer is >75 % full. Any negative NTSTATUS turns logging off for good. Cap is 512 KiB, then one LOGFULL line.
  With the flag clear there is zero file I/O. Hosted builds go through a 5-function-pointer fake struct.
- Loader: entry argument = flags. Six more resolved-slot checks: 41b660/190, 41b658/236, 41b6b0/198, 41b624/187,
  41b774/156, 41b65c/211 (all re-asserted with Pins._thunk_ordinal). Host struct is still 44 bytes with the same
  11 values. Gate, digest, relocation checks, rollback and fail-stop are unchanged.

## Tests (all offline, all pass)
1. `cd src/ogxbox/integration && bash build_pic.sh`: 20 R_386_RELATIVE relocations, no TEXTREL.
2. `bash tests/run63.sh`: test63 7/7 (clang -m32 ASan+UBSan). F6 regression, both modes 6/6 green.
   a: announce after qualification gives exactly one POWER, S-init only after its TXDONE, counters bumped; len!=28
      also triggers it; a failed power-on gives no S-init; before qualification it identifies as before.
   b: exact rumble bytes; N calls while busy give one frame with the last value; zero gives a zero frame;
      re-sent after a generation change; stale and native handles unchanged; caps 0xFFFF.
   c1 flag off: zero I/O. c2 open failure: off for good, transport unaffected.
   c3 GEN/ATT/QUAL/RX/REHS/TX/TXDONE/RUMBLE/XIOPEN/IN/CNT lines present.
   c4 no I/O at fake IRQL 2. c5 cap at 512 KiB, then LOGFULL, then nothing more.
3. `/usr/bin/python3 release.py --out release`: test_candidate.py 8/8 OK, both on the built tree and on the
   unpacked archive. Bases 0x1000000 and 0x83000000; adds test_08 (option [1] gives entry flags=1, no file I/O at entry).
Sizes: text 20059 / data 428 / bss 23420; payload 20636 B; RESIDENT_ALLOC 45056; FILE_ALLOC 24576;
trainer decoded 3808 B (limit 15193).

## NOT verified (needs the console run)
Real pad wake behaviour, real rumble and real file I/O are all unverified. Also unverified: whether the dark pad
really sends ANNOUNCE on its button; how Halo 2 treats SetState's return, caps and hEvent (call sites not checked);
the fs:[0x24] IRQL read and the KeTickCount slot on hardware. The BOOT line is not covered by the hosted tests.
The new hosted tests skip S0..S5 (the f6/lifecycle suite covers those).

## Log legend (`<tick_ms> TAG key=value…`)
BOOT tag flags installed_hooks install_failed rc | GEN gen attach remove refused (generation changed)
ATT state life in out failed gen (on change) | QUAL ready s_init_pending (wired qualification ran)
RX cmd opt seq len data=<=32 payload bytes (every non-input GIP frame; a 0x02 announce here = pad woke)
REHS n announces s_init_pending (W1 re-handshake fired) | TX cmd seq len | TXDONE cmd status len
IN first reports buttons (first input of a generation, then <=1/s) | GDC type gamepad ins rem (non-zero masks)
XIOPEN port kind result / XICLOSE kind handle | RUMBLE l r calls [hevent] (on change)
CNT lost_events gen_resyncs span_refused span_revalid tx_dropped unknown_cmds announces rehandshakes setstate
rumble_frames (every 5 s if changed) | LOGFULL bytes dropped
How to read it: announce RX + REHS + TXDONE 0x05 status 0, but the pad still dark → W1 is not enough.
GEN with refused>0 → the re-enumeration cause. No RUMBLE line at all → Halo never called SetState on the virtual pad.

Refusals: REFUSALS.md. Leftover: release-aborted-timeout/ (partial output from a tool timeout, unused).
