# Worker 43 report — candidate, not cleared for physical test

## Scope and verdict

HOST QUALIFIED packaging candidate, GUEST UNTESTED. This is not READY for physical
installation and not a claim of modern-controller survival/control. The original
W32 ELF remains the packaging test vector; worker 42's debugger path is independent.
Only this owned directory was written. No integration/driver edits, guest/USB,
QMP/GDB, services, credentials, external builds, uploads or git changes were made.
Git remained main at b83cf6546e7d04c6013571d4641cb3e482b05e94, ogxbox/ untracked.

Deliverable: release-build/AmpJack43-u803-candidate.zip. Its allowlist contains exactly
seven members: the uniquely named .xbtf and .bin, README.txt, SHA256SUMS,
COPYING.GPL-3, NOTICES.txt and manifest.json. Only the first two are install files.
The archive was actually unpacked and both checker and CPU tests ran on those bytes.
An additional independent clean build in clean-rebuild-check/ reproduced both
install files byte-for-byte (cmp exit 0; audit.json records both comparisons).
Archive SHA256: 24bee5b09dbb2f39651c4ac49ac7969de81a0d4d8c376535f889bf298ada530b.
Separate checksum: release-build/ARCHIVE-SHA256SUMS.

## Frozen ABI and byte translation

ELF SHA256 7bbfdafaa91920269876aa54e02efe278b738c0298aeb7bd629b1aaf8a1a08b8;
layout SHA256 c1ecc50ad14a86246f516df080b96c50e348cefa5d5f779916c78164443858f6.
The actual ELF has cdecl entry at virtual offset 0, not an H2S2 header or stdcall
entry. Its entry ignores its argument. The true ogx_g_module is offset 14712
(0x3978), struct size 21132, host size 44. BSS begins 14704, ends 35896. Actual
.text is 13928 bytes, not the older loader report's core estimate. All 20 ELF
relocations are R_386_RELATIVE. No driver/module recompilation occurred.

AJ43 v1 is deliberately NOT H2S2-compatible. It is a matched disk-only 64-byte
envelope + exact original virtual image + 20 u32 relocation destinations. Removing
the envelope on load preserves every original ELF virtual offset, instruction,
initialized data byte and relative reference. The native C adapter, inside the
trainer, supplies the real module host and caller-balances the cdecl argument.
This avoids silently moving data or pretending the H2S2 host is ogx_mod_host.

Mapping (all byte-equal, verified in release-build/audit.json):
  ELF file 4096, VA 0        -> payload file 64,    runtime offset 0,     13928 bytes.
  ELF file 18024, VA 13928   -> payload file 13992, runtime offset 13928, 345 bytes.
  ELF file 18372, VA 14276   -> payload file 14340, runtime offset 14276, 428 bytes.
The virtual gap is zero. Relocation destinations/addends remain unchanged; native
loader adds the resident base. BSS is not on disk and is zeroed before host fill.
No complete game header, game executable, dumps or proprietary SDK files are shipped.
Minimal prologue byte signatures serve only refusal/rollback; header uses a digest.

## Native path and safety

bootstrap.S saves flags/all general registers, clears DF, calls PIC loader C with
EBP trainer base, restores registers/flags and returns with plain ret. The linked
bootstrap has zero dynamic relocations (readelf evidence in commands.log).
The single option defaults OFF and is bounds-checked; all unrelated-title gates
run before I/O/allocation. No persistent module pointer is written into trainer
memory, no tick/network/stats/Live/Yelo code, no eighth hook or singleton payload
path is added. Existing W32 XGetDeviceChanges stub remains the pump.

Native loader checks the full frozen 0x178-byte XBE header via SHA256, allowing
ONLY fields 0x128 and 0x158 to equal their exact disk OR decoded values:
  0x128: 0xA8D1FE75 or 0x002DA9DE
  0x158: 0x5B2CF6B6 or 0x0041B600
All other bytes are exact. Values are grounded in W31 accept_handoff/PARENT-ACCEPTED
and W33's successful current-boot journal, not guessed by masking those words.
Certificate TitleID is also checked. This selects pre-entry u803, before
XInitDevices; no late-main install path is supplied. Disk and decoded forms both
pass in the host fixture; retail->TU->unrelated persisted-trainer sequence is tested.

All seven full displaced spans and four 10-byte method guards are compared before
any title writes, then rechecked after file I/O. Required kernel import slots must
be resolved. Host preserves stock class table pointers, gamepad dtype identity
0x4127D8, AddComplete 0x416992 and RemoveComplete 0x4165C6. IRQL host fields contain
SLOT addresses 0x41B700 and 0x41B6FC, not their loaded function values. Cancel and
clock remain zero as in W33. Build validates ordinals from the read-only XBE.

Payload SHA256 is compiled into the trainer, checked over the exact file, and EOF
is probed (appended/oversize data refused). Header metadata is exact, all native
reads have fixed bounded lengths, relocations must equal the expected count and
destinations and fit initialized image, addends fit memory, allocation/base math
cannot wrap or overlap title/trainer/file storage. Host packer rejects incompatible
layout and extra/duplicate relocation inputs. Copied image, zeroing, each relocated
word and injected host receive readback checks before executing the untouched entry.

After return: check actual seven E9 targets, displaced tails, installed_hooks=BF,
install_failed=0. The module installer has a current-site partial-write rollback
hole; this wrapper restores and verifies ALL seven owned sites on failed entry or
postcheck, including that partial site, before freeing resident memory/returning
stock. Three bounded restoration passes; permanent readback failure executes the
actual native cli/hlt loop, retaining reachable resident allocation and never
returning to stock. This is deliberate fail-stop, NOT successful stock recovery.
Cold owner-controlled recovery is a runtime gate. No hot-unload promise is made.

## Actual execution evidence

Command executed from clean new owned output:
  /usr/bin/python3 ogxbox/work/43-trainer-candidate/release.py --out /home/roasted/Desktop/Xbox/AmpJack-OG/ogxbox/work/43-trainer-candidate/release-build

Exit 0. Full real build output: release-build/build.log and commands.log.
Original CPU test output: release-build/cpu-tests.log.
Unpacked archive CPU output: release-build/unpacked/cpu-tests.log.
Each final run: Ran 7 tests ... OK. Nested cases cover 19 native clean refusals,
2 success bases, rollback, fail-stop, disk/decoded/relaunch and host negatives.
No tests were skipped. /usr/bin/python3 has Unicorn; Hermes venv python does not.
The fixture uses actual generated trainer code and emitted payload. Kernel/file
calls alone are SYNTHETIC stdcall surfaces, clearly labelled, not Xbox proof.
Module entry/transport_init/installer execute as the exact original machine code;
no production entry, installer, bootstrap or adapter is replaced with success.

Selected actual lines:
  RED reproduced: unadapted cdecl leaves argument, ignores H2S2 host, install_failed=1 hooks=0
  GREEN base=0x1000000 exact relocated image, host, 7 targets, hooks=BF failed=0; peak native=53248 resident=36864 stack_high_water=1044
  GREEN base=0x83000000 exact relocated image, host, 7 targets, hooks=BF failed=0; peak native=53248 resident=36864 stack_high_water=1044
  PASS actual installer current-site partial write: adapter restored and verified all seven before free/stock return
  PASS permanent restoration failure: native fail-stop, reachable allocation retained, no stock return
  PASS host rejection: stale manifest, incompatible layout, extra relocation, corrupt/truncated/oversize payload

At entry, observer compares entire relocated image, every required data relocation,
44-byte host, zero BSS and cdecl argument against independent W32 Module.image and
W33 site/target journal oracle. Before first host store it observes all BSS zero.
After return it checks registers, stack, flags, BF/0, every target and all title
bytes outside the seven 5-byte writes. Clean rejection compares the complete
synthetic title region, verifies no open handle or allocation remains, no trainer
mutation and resident canary intact. No gameplay/input behavior is inferred.

Negatives: disabled/malformed option, wrong title/TU/header/entry, original site or
method mismatch, already installed, missing/unresolved slot, missing file, corrupt,
oversize/appended, truncated, bad relocation, first/second allocation refusal,
read I/O failure, current-site partial write, permanent rollback failure; host
stale-manifest/layout/extra-relocation/payload corruption checks. The RED tests the
actual entry with a real H2SH host argument but without ogx_g_module.host injection;
it returns cdecl leaving the argument, and installer refuses with failed=1 hooks=0.

Development failures retained conceptually, not misrepresented as product proof:
initial bootstrap compile exposed a compiler-created pointer-bearing constant
aggregate relocation; volatile runtime ANSI_STRING construction removed it, with
strict no-relocation build check unchanged. Initial BSS observation fired on a
zeroing byte store rather than the first host-field dword store; correcting the
observer trigger retained the full zero-BSS assertion. No legacy suite was run or
fixed; legacy 11 (1 failure) and 22 (3 failures) claims remain untouched.

## Measured footprint (not the 4 MiB format cap)

  Exact module .text:                 13928 bytes
  Initialized virtual image:          14704 bytes
  BSS:                                21192 bytes
  ogx_module object (within BSS):      21132 bytes
  Image memory end:                   35896 bytes
  Resident kernel allocation:         36864 bytes (0x9000)
  Payload file:                       14848 bytes
  Trainer file:                        3717 bytes
  Decoded trainer:                     3700 bytes, limit 15193
  XBMC loader plus decoded data:       3867 bytes, within 15360-byte format heap
  Conservative XBMC page allocation:  16384 bytes (15360 rounded to pages)
  Short-lived file buffer allocation: 16384 bytes (0x4000)
  Simultaneous new native alloc peak: 53248 bytes (0xD000)
  New steady native residency:        36864 bytes
  Steady with XBMC page allocation:   53248 bytes
  Alloc peak incl XBMC pages:         69632 bytes
  Observed CPU stack high-water:       1044 bytes (borrowed caller stack)
  Alloc peak + observed stack use:    70676 bytes

File buffer is freed and file closed before module entry; resident remains title-
owned (not MmPersist). Peak is measured from synthetic allocator lifetime receipts,
not a guest retail-RAM measurement. File-system cache/handle/kernel metadata and
actual title pool headroom are NOT measured by this host fixture. No threads or
thread stacks are created. 4 MiB is not used as a budget.

## Open runtime gates

Ordinary XBMC4Gamers parsing/selection/default-OFF and disabled u803 launch;
ordinary enabled pre-entry launch including TU relaunch; read-only exact relocated
hooks/BF/0 in that boot; native enum/attach ordering; original pad port 1 preserved;
modern wired port 2 enumeration, control, sustained polling and reconnect/removal;
retail 64 MiB headroom and timing; ordinary cold launch; disabled/recovered stock
launch after failure/removal. W32's RAM install/attach does not close these gates.
No physical-test clearance, runtime lease or runtime automation is supplied here.
