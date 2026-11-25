# +05-loader — ship a larger controller driver as an OG Xbox Halo 2 trainer

Owner: ogxbox/loader/ + ogxbox/work/05-loader/. Worker 5 of 6. Scope: LOADER and
build/toolchain feasibility only — not the USB transport (worker 02) and not the
GIP mapping shim (worker 04).

Labels: VERIFIED = observed source bytes or real execution on this host;
INFERENCE = my interpretation with the gap stated; UNKNOWN = missing hardware facts.
Repo revisions referenced: AmpJack upstream b83cf6546e7d04c6013571d4641cb3e482b05e94
(git rev-parse HEAD), LAN_Stats adfa3737b2b9d25e6d1736149198f94122b27fab,
OXDK b175c2c16446f0af33b75cb49a7140d6a2cab3b5.

## 1. The answer in one paragraph

There is already a proven, no-BIOS-flash route to ship a driver much bigger than
XBMC's ~15 KB trainer block: a two-stage loader. A small ~500-byte assembly bootstrap
lives inside the XBMC .xbtf; it reads a larger freestanding C module from
`\Device\Harddisk0\Partition1\Trainers\<name>.bin`, allocates memory with the kernel
service the game already imports, relocates a static-PIE image, and calls its entry.
This "stage-2 platform" is built, unit-tested and runtime-proven on a devkit xemu by
the LAN_Stats project (references/stage2-platform.md). I reproduced its build here and
measured that the entire portable AmpJack GIP core (+ wireless MT76 + the GIP EC crypto)
fits in a 78 KB module — ~0.12 % of the 64 MB title budget, well under the loader's
4 MiB cap. The only genuinely missing pieces are the OG USB transport ABI and the exact
Halo-2 XInput hook addresses (workers 02/03); nothing about the loader blocks them.

## 2. What I read (load contract + toolchain)

### 2.1 XBMC trainer container (the bootstrap's home), VERIFIED from source
- .xbtf is XBMC's "converted ETM" trainer. XBMC `CUtil::InstallTrainer` allocates
  `XBTF_HEAP_SIZE = 15360` bytes, copies a 167-byte loader, then the trainer data; the
  trainer data cap is 15193 decoded bytes (15360 - 167). LAN_Stats shipped their whole
  stats trainer (options, scoreboard, HDD/HTTP export) at 14996/15193 — 197 bytes free.
  Cites: LAN_Stats references/xbmc-trainer-format.md (VERIFIED against
  Rocky5/XBMC4Xbox Trainer.cpp/Util.cpp, commit 921f9fe9f86e, "generously donated by
  team xored").
- Runtime contract: XBMC patches the kernel's `call [0x00010128]` (XBE entry) to
  `call [0x8000000C]`, persists the buffer with `MmPersistContiguousMemory`, and the
  loader runs BEFORE the game entry in ring 0 with CR0.WP cleared and EBP=EDX=trainer
  base. Only a title-ID gate + the game's own TimeDateStamp check select the build. No
  BIOS flash, no kernel-resident patch beyond XBMC's own softmod machinery.
- Conclusion (INFERENCE, sound): a transport driver of ~10 KB would fit in the single
  .xbtf block only with difficulty; a real GIP driver (measured 78 KB) does not. The
  bootstrap must therefore be a stage-2 LOADER, not the driver itself.

### 2.2 The stage-2 load contract (H2S2 v1), VERIFIED
- File `E:\Trainers\<name>.bin` = flat image (header at offset 0) + packed u32
  R_386_RELATIVE offsets. 48-byte header: magic "H2S2", version 1, file_size,
  mem_size (< 4 MiB, loader-enforced), image_size, entry offset, reloc_off,
  reloc_count, build_id (CRC-32), reserved. Loader steps (opened with
  NtOpenFile/NtReadFile, alloc via `MmAllocateContiguousMemoryEx`, reloc, zero bss,
  call entry(&host)): LAN_Stats trainer/stage2/README + references/stage2-platform.md
  §3-§5.
- The bootstrap loader cost is tiny: 417 code + 16 tick-stub + 96 data bytes. A larger
  driver therefore costs the bootstrap almost nothing; all bulk goes in the disk payload.

### 2.3 Build toolchain, VERIFIED (reproduced here)
- LAN_Stats stage-2 uses OXDK's clang + ld.lld, i386 ELF, static PIE (not an XBE
  build): `clang -target i386-unknown-none-elf -march=pentium3 -Os -ffreestanding
  -nostdlib -fpie -fvisibility=hidden -mgeneral-regs-only`, `ld.lld -pie
  --no-dynamic-linker -z text -z norelro`, then a Python converter (mkmodule.py) turns
  the ELF into the flat module.
- OXDK itself (b175c2c1) ships the ORIGINAL XDK import libs/headers and the `oxdk` shell
  (`xbox/xdk/lib/xboxkrnl.lib` 89974 B, d3d8, xgraphics, xapi, xnet, xacteng, libc …)
  so a fully self-hosted .xbe is also buildable, but a stage-2 module deliberately does
  NOT need the XDK — it reuses the game's own resolved kernel imports.

## 3. Per-title XInput/USBD vs kernel-resident driver vs direct OHCI (route map)

VERIFIED from the u803 XBE evidence (LAN_Stats references/u803-addresses.json):
Halo 2 TU1.5's kernel-import table lives at VA 0x41B600 (153 slots). The 17 slots that
are VERIFIED are Mm*/Ke*/Ps*/Nt*/Hal/DbgPrint only — there is NO kernel USB service in
the game's import table. Three consequences for the driver transport:

1. Title-linked kernel USB thunks do not exist in this XBE. The driver cannot simply
   "call [Usbd thunk]" the way the stage-2 loader calls `[0x41B640]`
   (MmAllocateContiguousMemoryEx). This is the key OG-vs-360 difference: the 360
   AmpJack calls the 360 kernel's Usbd (xbox360/usbd.h); the OG title has no such import.
2. Kernel-resident class driver (Usbd/OHCI selected by the kernel) would enumerate the
   GIP device at boot, but adding one is a resident/kernel-patch route — reject as the
   default (mission: no BIOS flash; no firmware/real-Xbox changes this wave).
3. Direct OHCI from the module is available in principle: the module runs in ring 0,
   every Xbox page is executable, and MmAllocateContiguousMemoryEx returns cached RW
   pages the CPU may execute (stage2-platform.md §4 step 5). OHCI register/ED/TD layouts
   are available locally as Cxbx-Reloaded's OpenXDK headers
   (`OGH2_Server/reference/Cxbx-Reloaded/import/OpenXDK/include/xusb/host/ohci.h`). This
   is worker 02's route to derive; it needs the OHCI base (UNKNOWN — not measured this
   wave) and does not need any title import.

The practical split the loader facts support: the stage-2 module is the natural HOME for
whichever transport worker 02 selects (direct OHCI, or hooking Halo's own statically
linked XID/XInput code per worker 03). The loader itself only needs the file I/O + one
kernel allocation, all VERIFIED present.

## 4. Calling conventions, allocation, lifetime (for the module's code)

- i386 cdecl/stdcall; module entry and tick are stdcall (EBX/ESI/EDI/EBP preserved,
  DF cleared), VERIFIED ABI — stage2-platform.md §6.
- Kernel import calls go through the XBE's own slot: clang emits
  `call dword ptr [0x41B640]` (VERIFIED by my objdump below). Title code/data is an
  integer constant cast to a function pointer: `mov eax, imm; jmp eax`, position
  independent, no relocation (VERIFIED below).
- Static PIE means code reaches its data PC/EBX-relative; the ONLY load-time fixups are
  absolute pointers in .data (8 in my probe, all R_386_RELATIVE; mkmodule rejects any
  other type and any text relocation host-side — a bad link fails on the PC, not the box).
- Position/lifetime: the trainer buffer persists across title launches via
  MmPersistContiguousMemory (XBMC); the module is allocated once per XBE launch, never
  unloaded, and runs from the pre-main entry (before Halo sizes its pools) through the
  per-frame tick — so it can outlive title/main-menu transitions within a launch.

## 5. Compile/link evidence produced here (real outputs)

All built on this host with system clang 23.1.5 + ld.lld 23.1.5, GNU as 2.47. Full log:
ogxbox/work/05-loader/build.log.

Step 1 — DISABLED diagnostic container (inert, proves the container path only):
```
out/diag.bin: file 128 B, image 128 B, bss 0 B, mem 128 B, entry 0x30, relocs 0, build_id 81ff6048
```
Header bytes `48 32 53 32 01 00 00 00 …` = "H2S2", v1, size 0x80 — a valid, loadable,
do-nothing payload. It hooks nothing, does no USB I/O, writes no game memory.

Step 2 — call-convention encodings (objdump -d -Mintel thunk_demo.o):
```
ff 15 40 b6 41 00   call  DWORD PTR ds:0x41b640   ; kernel import slot
b8 83 b4 2d 00      mov   eax,0x2db483
ff e0               jmp   eax                     ; title absolute (PIC, no reloc)
```

Step 3 — core-size probe (real AmpJack core gip.c + dongle.c + mt76.c + sha256.c +
uECC.c linked against a SYNTHETIC stub transport, `--gc-sections` off = whole driver):
```
out/core_probe.bin: file 40576 B, image 40544 B, bss 37900 B, mem 78444 B, entry 0x30, relocs 8
 text 40405 | data 332 | bss 37900 | dec 78637   (size out/core_probe.elf)
```
Measured per-object (nm, from the map): text is dominated by gip.c's `dispatch`
(3750 B), `gip_rx` (1050 B), `gip_poll` (810 B); uECC P-256 sign/verify (~4-5 KB);
mt76.c's `process_wlan` (1448 B) + radio/firmware init (~3 KB). The single largest .bss
item is `process_wlan.frame` = 33792 B — the MT76 wireless RX frame buffer. A WIRED-only
driver drops mt76.c/dongle.c (and can gc out the uECC GIP-auth path via `no_auth`),
which removes essentially all of that 33 KB and the wireless radio code.

## 6. Memory estimate (from object/map files, not guesses)

- Full wireless-capable GIP core + crypto: ~78 KB loaded (40 KB text + ~0.4 KB data +
  37.9 KB bss). That is ~0.12 % of the 64 MB title budget, and 1/53 of the loader's
  4 MiB cap. The stage-2 loader itself adds ~0.6 KB inside the .xbtf.
- Wired-only (milestone) would be smaller: subtract the 33 KB wireless frame buffer
  (+ my synthetic 4 KB stub arena, not part of a real driver) and, if `no_auth` links
  without the EC sign path, another ~5 KB. Expected realistic wired driver ≤ ~40 KB.
- The 4 MiB `mem_size` cap and the 15193-byte .xbtf cap are both loader-enforced and
  neither binds for a driver this size. The real constraint to test later is retail
  RAM headroom when the module allocates before Halo sizes its pools
  (stage2-platform.md §6/§10 lists this as an open question; INFERENCE: 78 KB is safe,
  but it is not yet measured on a retail 64 MB box).

## 7. Title entry time vs USB init; boot-plugged re-enumeration

VERIFIED (stage2-platform.md §6/§8, xbmc-trainer-format §2): the module entry runs
pre-main on the XBE launch thread — kernel thunks resolved, CR0.WP cleared, XNet not
yet started. Halo's own XInput/XID init happens AFTER this, on the game's main thread;
the module's per-frame `tick` runs later (~58/s, inside `network_update`, WP set),
which is the safe time for transport work once the game's USB/XID stack is up.
INFERENCE (needs the hardware measurement of worker 01): a pad plugged at boot is
enumerated by the kernel's USB driver before the game starts; an Xbox One GIP device
would NOT be claimed by the XID class driver (wrong VID/PID/topology), so the game's
`XInputGetState` reports nothing. For the driver to see it, the module must either
talk to OHCI directly (reset/port-enumerate the device — direct-MMIO, no import needed)
or the title must be hooked to synthesize a controller slot (worker 03). Whether the
specific pad re-enumerates at full speed (12 Mbps) is UNKNOWN and is worker 01's gate.

## 8. What must wait for driver ABI / USB measurements (not loader)

1. The exact OG OHCI MMIO base + ED/TD/periodic-list layout and the confirmed full-speed
   descriptors of the specific pad (worker 01/02) — no guessed addresses.
2. The exact u803 XInputOpen/XInputGetState/GetCapabilities function VAs and prologue
   bytes for the exact XBE (SHA256 21b207e7…, VERIFIED present at
   ~/Desktop/Xbox/H2-Decomp/tu15-decomp/targets/halo2-tu15-u803/default.xbe); the old
   0x413A12 / 0x413C4C clues are NOT in u803-addresses.json and still need exact-XBE
   verification (worker 03).
3. A real platform layer (platform.h → OHCI) replacing stub_platform.c — NOT a stub.
4. A retail 64 MB real-hardware or bounded xemu memory test of the ~78 KB allocation.

## 9. Provenance / licensing (all local artifacts)

- AmpJack upstream is GPL-3.0-or-later (LICENSE); core/gip.c, dongle.c, mt76.c,
  sha256.c are GPL-2/3 with xone authorship noted in headers. Nothing proprietary is
  copied: my loader files are a clean-room re-statement of the LAN_Stats (also GPL-3.0)
  H2S2 ABI. No game assets, no XDK code, no Microsoft headers were redistributed or
  embedded. The 4.9 MB u803 XBE was never modified; it is only read for hash/match.

## 10. Files owned here

- ogxbox/loader/build.sh            builds (1) diag container, (2) objdump, (3) size probe
- ogxbox/loader/{h2s2.h, link.ld, crt0.c, diag_main.c, mkmodule.py}
- ogxbox/loader/{stub_libc.c, stub_platform.c, stub_div64.c, core_probe_main.c, thunk_demo.c}
- ogxbox/loader/freestanding/{string.h, stdlib.h, stdio.h}
- ogxbox/loader/out/{diag.bin, core_probe.bin, *.map, thunk_demo.txt, core_probe.nm}
- ogxbox/work/05-loader/{status.json, build.log}

Reproduce: `cd ogxbox/loader && bash build.sh` (needs clang + ld.lld + binutils + python3).

## 11. Completed vs unverified

Completed (all VERIFIED on this host): the two-stage loader/container design; the XBMC
.xbtf contract and its 15193-byte limit; the stage-2 H2S2 load contract and module
format; the i386 PIC/kernel-thunk calling-convention encodings; a buildable inert
diagnostic container (128 B) and a measured 78 KB full-core size probe; the route map
(per-title vs kernel-resident vs direct OHCI) pinned to the u803 import-table evidence.

Unverified (deferred, each named): real OHCI transport ABI and base address; exact
u803 XInput hook bytes; real-controller full-speed enumeration (worker 01); retail-RAM
allocation timing. The next smallest test is a bounded xemu (not emulator-owned this
wave) or real-hardware launch of diag.bin through the XBMC trainer path to confirm the
stage-2 loader loads a 128-byte module and returns — with owner authorization.
