AmpJack43 u803 — candidate — not cleared for physical test

This package is an opt-in XBMC4Gamers trainer plus a matched AmpJack payload.
It is a packaging test vector, NOT an approved physical-console installation.
Host i386 CPU tests are not evidence of Xbox enumeration, survival or control.
Do not install on physical hardware until the owning runtime gates are cleared.

The only eventual Xbox files (no overwrites):
  E:\Trainers\AmpJack43-u803-7bbfdafa.xbtf
  E:\Trainers\AmpJack43-u803-7bbfdafa.bin
Keep this exact pair together. No TrinityLive.bin, stats trainer, game-file edit,
flash, autoexec, persistent kernel driver or PC loader/input program is used.
Do not rename the payload. Trainer option is OFF by default. No disk writes are
performed by the trainer. No background thread or eighth hook is installed.

Supported path: XBMC4Gamers Games-list trainer loading, Halo 2 TU1.5 u803 only,
XBE SHA256 21b207e7efdacaf6124a0822837f8be570766a42505057f7fd2d2ba8f409c4fd.
Other builds/retail launcher are no-ops, including the initial disc launch on its
way to the TU relaunch. Use a legitimate existing u803 TU; this archive supplies
no update, game executable, firmware, XDK material or emulator configuration.

DEFERRED owner-operated runbook (not performed; not permission to physical-test):
1. Only after runtime lease release and separate clearance: verify SHA256SUMS.
   Confirm the XBMC4Gamers profile trainerpath is E:\Trainers. If it differs,
   do not silently substitute a directory: the payload path is deliberately
   fixed to E:\Trainers. Never overwrite existing files, even matching names.
2. Copy ONLY the two named files to that directory by the owner's normal method.
   Keep README, manifest, checksum and licensing files on the PC, not autoexec.
3. Keep an original Xbox pad in physical port 1. For the later enabled test,
   modern wired pad in port 2 through a passive data-capable cable/adapter.
   A charge-only lead will not work. Fixed virtual port index is 1 (front port 2);
   this is not a proven native physical-port derivation. Wireless is not qualified.
4. XBMC4Gamers default skin: Games -> select Halo 2 -> White/context menu ->
   Trainers (cheats) -> Update trainer list. Then Trainer settings -> select
   'AmpJack43 u803 CANDIDATE'. Selecting it deactivates a previous trainer.
   First leave 'Enable AmpJack43 candidate' UNTICKED -> OK.
5. Launch from the Games list, not the file manager (which skips trainer install).
   First observe ordinary disabled launch into u803 and original-pad control.
   Retail/no-TU is inert. Do not enable in a title already running.
6. Return to dashboard. Trainer settings -> tick the option -> OK. Launch Halo 2
   normally from Games, allowing the retail-to-TU relaunch. The trainer executes
   before decoded u803 entry 0x2DA9DE, not late main. Obtain the read-only hook,
   install-status, stock-pad and modern-pad evidence listed in HANDOFF.md.
7. A separate cold title/console launch is a later runtime gate. Do not use save
   states or debugger injection to substitute for ordinary dashboard launches.

Recovery: return to dashboard and untick the option, or deselect this trainer;
start a fresh title. Never try to disable hooks inside an already-running title.
After stock boot is verified, remove ONLY the two exactly named files above and
refresh the trainer list. Do not delete other trainers or change game files.
Any unrecoverable hook-restoration readback failure deliberately stops pre-entry
with resident memory retained rather than returning into dangling hooks. Such a
failure needs owner-controlled cold recovery, not a claim of safe hot unloading.

Provenance, exact rebuild/verify commands, open gates and measurements are in the
sibling HANDOFF.md and REPORT.md in the authored host work directory. GPL-3.0-or-
later terms and third-party attribution are in COPYING.GPL-3 and NOTICES.txt.
